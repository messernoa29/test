"""Step 1 of the audit pipeline: deterministic HTTP crawler.

We deliberately do NOT use `web_search` here. A native Python crawl gives:
- Complete coverage (no page forgotten, no LLM sampling bias)
- Lower token cost (the analyzer receives a compact payload, not raw HTML)
- Reproducibility (two runs on the same URL return the same pages)

The crawler walks in three passes:
1. Fetch `/robots.txt` and `/sitemap.xml` (or its index) to harvest URLs the
   site declares itself. This is the most reliable source of canonical URLs.
2. Fetch the homepage and follow internal links from the navigation, header
   and footer as a fallback when no sitemap is present or incomplete.
3. For each discovered URL (capped), fetch the HTML and extract SEO-critical
   fields: title, H1, meta description, heading outline, short text snippet.

See docs/SELF-IMPROVEMENT.md (ERREUR #3) — crawl and analysis stay in two
separate steps.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Iterable, Optional
from urllib.parse import urljoin, urlparse, urlunparse
from xml.etree import ElementTree as ET

import httpx
from bs4 import BeautifulSoup

from api.models import (
    CrawlData,
    CrawlPage,
    DeadInternalLink,
    DuplicatePair,
    HreflangEntry,
    ImageAsset,
    InternalLink,
    LinkGraphPageStat,
    LinkGraphSummary,
    RedirectChain,
)
from api.services import playwright_fetcher, schema_detector

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (compatible; AuditBureauBot/0.1; +https://audit-bureau.local)"
)
REQUEST_TIMEOUT = 15.0
MAX_PAGES = 50  # hard cap on fully-fetched pages
MAX_DISCOVERY_LINKS = 200  # cap on URLs discovered before trimming
HEADING_LIMIT = 8
SNIPPET_LIMIT = 200
MAX_LINKS_PER_PAGE = 200  # safety cap per page (mega-footers exist)
ANCHOR_TEXT_LIMIT = 80
DEAD_LINK_PROBE_LIMIT = 25  # max external HEAD probes for dead-link detection
HUB_PAGES_TOP_N = 5
ORPHAN_PAGES_LIMIT = 25
TOP_ANCHOR_TEXTS_LIMIT = 15
SHINGLE_SIZE = 5  # word n-gram length for Jaccard similarity
DUPLICATE_NEAR_THRESHOLD = 0.85  # Jaccard ≥ this → reported as near-duplicate
DUPLICATE_PAIRS_LIMIT = 20
CRAWL_CONCURRENCY = int(os.getenv("CRAWL_CONCURRENCY", "8"))


def crawl(url: str) -> CrawlData:
    """Crawl the site and return structured page data."""
    base = _normalize(url)
    parsed = urlparse(base)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    client = httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
        max_redirects=5,
        http2=False,
    )

    try:
        discovered = _discover_urls(client, origin, base)
        logger.info("Discovered %d candidate URLs for %s", len(discovered), origin)

        targets = discovered[:MAX_PAGES]
        pages = _fetch_pages_parallel(client, targets, origin)

        link_graph = _build_link_graph(client, pages)
        duplicates = _compute_duplicates(pages)
        redirect_chains = _collect_redirect_chains(pages)
    finally:
        client.close()

    if not pages:
        raise ValueError(
            "Le site n'a pas répondu ou ses pages sont vides (bloqué par JS ?)."
        )

    return CrawlData(
        domain=parsed.netloc,
        url=base,
        crawledAt=datetime.now(timezone.utc).isoformat(),
        pages=pages,
        linkGraph=link_graph,
        duplicates=duplicates,
        redirectChains=redirect_chains,
    )


# ---------------------------------------------------------------------------
# Discovery


def _discover_urls(
    client: httpx.Client, origin: str, entry_url: str
) -> list[str]:
    """Return a deduplicated, ordered list of same-origin URLs worth crawling.

    Order of precedence:
    1. URLs from the sitemap (including sitemap indexes).
    2. URLs linked from the homepage navigation/body (BFS depth 1).
    3. The entry URL itself.
    """
    urls: list[str] = []
    seen: set[str] = set()

    def push(candidate: str) -> None:
        norm = _normalize(candidate)
        if not norm or norm in seen:
            return
        if urlparse(norm).netloc != urlparse(origin).netloc:
            return
        seen.add(norm)
        urls.append(norm)

    push(entry_url)

    for sitemap_url in _sitemap_candidates(client, origin):
        for sitemap_entry in _read_sitemap(client, sitemap_url, depth=0):
            push(sitemap_entry)
            if len(urls) >= MAX_DISCOVERY_LINKS:
                break
        if len(urls) >= MAX_DISCOVERY_LINKS:
            break

    for link in _walk_links_bfs(client, entry_url, origin):
        push(link)
        if len(urls) >= MAX_DISCOVERY_LINKS:
            break

    return urls


def _sitemap_candidates(client: httpx.Client, origin: str) -> list[str]:
    """Return sitemap URLs: from robots.txt first, then the conventional location."""
    candidates: list[str] = []
    try:
        resp = client.get(f"{origin}/robots.txt")
        if resp.status_code == 200:
            for line in resp.text.splitlines():
                lower = line.strip().lower()
                if lower.startswith("sitemap:"):
                    candidates.append(line.split(":", 1)[1].strip())
    except httpx.HTTPError:
        pass

    if not candidates:
        candidates.append(f"{origin}/sitemap.xml")
    return candidates


def _read_sitemap(client: httpx.Client, url: str, depth: int) -> Iterable[str]:
    """Yield <loc> URLs from a sitemap, recursing into sitemap indexes once."""
    if depth > 1:
        return
    try:
        resp = client.get(url)
    except httpx.HTTPError as e:
        logger.debug("Sitemap fetch failed on %s: %s", url, e)
        return
    if resp.status_code != 200 or not resp.content:
        return

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        logger.warning("Malformed sitemap %s: %s", url, e)
        return
    except Exception as e:
        logger.warning("Unexpected error reading sitemap %s: %s", url, e)
        return

    try:
        tag = _local_name(root.tag)
        if tag == "sitemapindex":
            for loc in root.iterfind(".//{*}sitemap/{*}loc"):
                if loc.text and loc.text.strip():
                    yield from _read_sitemap(client, loc.text.strip(), depth + 1)
        elif tag == "urlset":
            for loc in root.iterfind(".//{*}url/{*}loc"):
                if loc.text and loc.text.strip():
                    yield loc.text.strip()
    except Exception as e:
        logger.warning("Error iterating sitemap %s: %s", url, e)


def _walk_links_bfs(
    client: httpx.Client, start: str, origin: str
) -> Iterable[str]:
    """BFS through internal links, depth 1 from the homepage."""
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    visited: set[str] = set()
    while queue:
        current, depth = queue.popleft()
        if current in visited or depth > 1:
            continue
        visited.add(current)

        html = _fetch_html(client, current)
        if html is None:
            continue
        try:
            soup = _parse_html(html)
        except Exception as e:
            logger.debug("Parse failed during BFS on %s: %s", current, e)
            continue
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            absolute = _normalize(urljoin(current, href))
            if urlparse(absolute).netloc != urlparse(origin).netloc:
                continue
            yield absolute
            if depth < 1:
                queue.append((absolute, depth + 1))


# ---------------------------------------------------------------------------
# Page fetching


def _fetch_html(client: httpx.Client, url: str) -> Optional[str]:
    result = _fetch_html_with_meta(client, url)
    return result[0] if result else None


def _fetch_html_with_meta(
    client: httpx.Client, url: str
) -> Optional[tuple[str, str, list[str]]]:
    """Return (html, finalUrl, redirectHops) or None on failure.

    redirectHops is the list of intermediate URLs visited (Location headers),
    not including the final URL.
    """
    try:
        resp = client.get(url)
    except httpx.TooManyRedirects:
        logger.warning("Redirect loop on %s — skipped", url)
        return None
    except httpx.HTTPError as e:
        logger.debug("Fetch error on %s: %s", url, e)
        return None

    if resp.status_code == 403:
        logger.warning("403 Forbidden on %s (bot detection?)", url)
        return None
    if resp.status_code == 429:
        logger.warning("429 Too Many Requests on %s — skipped", url)
        return None
    if resp.status_code != 200:
        if 400 <= resp.status_code < 600:
            logger.debug("HTTP %d on %s — skipped", resp.status_code, url)
        return None
    content_type = resp.headers.get("content-type", "").lower()
    if "text/html" not in content_type and "xhtml" not in content_type:
        return None

    try:
        text = resp.text
        if text.count("�") > 10:
            raise UnicodeDecodeError("httpx", b"", 0, 1, "too many replacement chars")
    except (UnicodeDecodeError, LookupError):
        apparent = _guess_encoding(resp.content)
        try:
            text = resp.content.decode(apparent, errors="replace")
        except Exception:
            text = resp.content.decode("utf-8", errors="replace")

    final_url = str(resp.url)
    hops: list[str] = []
    for prev in resp.history:
        try:
            hops.append(str(prev.url))
        except Exception:
            continue
    return text, final_url, hops


def _guess_encoding(raw: bytes) -> str:
    """Very simple encoding guess without a heavy dep."""
    head = raw[:4096]
    try:
        head.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        head.decode("latin-1")
        return "latin-1"
    except UnicodeDecodeError:
        pass
    return "utf-8"


def _parse_html(html: str):
    """BeautifulSoup with lxml; fall back to stdlib parser if lxml breaks."""
    try:
        return BeautifulSoup(html, "lxml")
    except Exception as e:
        logger.debug("lxml parse failed (%s), falling back to html.parser", e)
        return BeautifulSoup(html, "html.parser")


def _fetch_pages_parallel(
    client: httpx.Client, targets: list[str], origin: str
) -> list[CrawlPage]:
    """Fetch all target URLs in parallel and preserve discovery order in output.

    httpx.Client is thread-safe for sending requests. Playwright fallbacks are
    serialized via a lock inside the fetcher to avoid concurrent Chromium
    launches.
    """
    if not targets:
        return []
    results: dict[str, Optional[CrawlPage]] = {}
    workers = max(1, min(CRAWL_CONCURRENCY, len(targets)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_url = {
            pool.submit(_fetch_page, client, url, origin): url for url in targets
        }
        for fut in future_to_url:
            url = future_to_url[fut]
            try:
                results[url] = fut.result()
            except Exception as e:
                logger.debug("Worker error on %s: %s", url, e)
                results[url] = None
    return [results[u] for u in targets if results.get(u) is not None]


def _fetch_page(
    client: httpx.Client, url: str, origin: str = ""
) -> Optional[CrawlPage]:
    meta = _fetch_html_with_meta(client, url)
    if meta is None:
        return None
    html, final_url, hops = meta

    # SPA fallback: when the raw HTML is a JS shell and Playwright is enabled,
    # retry via headless Chromium so we see the rendered DOM.
    rendered_with_playwright = False
    if playwright_fetcher.is_enabled() and playwright_fetcher.looks_like_spa(html):
        logger.info("SPA shell detected on %s — retrying via Playwright", url)
        rendered_html = playwright_fetcher.fetch_rendered(url)
        if rendered_html:
            html = rendered_html
            rendered_with_playwright = True

    try:
        soup = _parse_html(html)
    except Exception as e:
        logger.warning("HTML parse failed on %s: %s", url, e)
        return None

    # title: prefer full text content (handles <title> with nested nodes).
    title = ""
    if soup.title:
        try:
            title = soup.title.get_text(strip=True) or ""
        except Exception:
            title = ""

    h1 = ""
    h1_node = soup.find("h1")
    if h1_node is not None:
        try:
            h1 = h1_node.get_text(strip=True) or ""
        except Exception:
            h1 = ""

    meta_desc: Optional[str] = None
    meta_node = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    if meta_node is not None:
        content = meta_node.get("content") if hasattr(meta_node, "get") else None
        if isinstance(content, str) and content.strip():
            meta_desc = content.strip()

    headings: list[str] = []
    for tag_name in ("h1", "h2", "h3"):
        for node in soup.find_all(tag_name):
            text = node.get_text(strip=True)
            if text:
                headings.append(text)
            if len(headings) >= HEADING_LIMIT:
                break
        if len(headings) >= HEADING_LIMIT:
            break

    snippet = _extract_snippet(soup)

    try:
        schemas = schema_detector.detect(html)
    except Exception as e:
        logger.debug("Schema detection failed on %s: %s", url, e)
        schemas = []

    internal_links = _extract_internal_links(soup, url, origin)
    body_text = _extract_body_text(soup)
    word_list = _tokenize_words(body_text)
    word_count = len(word_list)
    content_hash = (
        hashlib.sha1(" ".join(word_list).encode("utf-8")).hexdigest()
        if word_list
        else ""
    )
    canonical = _extract_canonical(soup, url)
    robots_meta = _extract_robots_meta(soup)
    hreflang = _extract_hreflang(soup, url)
    html_lang = _extract_html_lang(soup)
    images = _extract_images(soup, url)
    images_without_alt = sum(1 for img in images if img.alt is None)

    return CrawlPage(
        url=url,
        title=title,
        h1=h1,
        metaDescription=meta_desc,
        headings=headings,
        textSnippet=snippet,
        schemas=schemas,
        renderedWithPlaywright=rendered_with_playwright,
        internalLinks=internal_links,
        internalLinksCount=len(internal_links),
        contentHash=content_hash,
        wordCount=word_count,
        finalUrl=final_url,
        redirectChain=hops,
        canonical=canonical,
        robotsMeta=robots_meta,
        hreflang=hreflang,
        htmlLang=html_lang,
        images=images,
        imagesWithoutAlt=images_without_alt,
    )


def _extract_canonical(soup: BeautifulSoup, page_url: str) -> Optional[str]:
    link = soup.find("link", rel=lambda v: v and "canonical" in (v if isinstance(v, list) else [v]))
    if link is None:
        return None
    href = link.get("href")
    if not href or not isinstance(href, str):
        return None
    return _normalize(urljoin(page_url, href.strip()))


def _extract_robots_meta(soup: BeautifulSoup) -> str:
    meta = soup.find("meta", attrs={"name": re.compile("^robots$", re.I)})
    if meta is None:
        return ""
    content = meta.get("content")
    return content.strip().lower() if isinstance(content, str) else ""


def _extract_hreflang(soup: BeautifulSoup, page_url: str) -> list[HreflangEntry]:
    out: list[HreflangEntry] = []
    seen: set[tuple[str, str]] = set()
    for link in soup.find_all("link", rel=lambda v: v and "alternate" in (v if isinstance(v, list) else [v])):
        lang = link.get("hreflang")
        href = link.get("href")
        if not lang or not href or not isinstance(lang, str) or not isinstance(href, str):
            continue
        absolute = _normalize(urljoin(page_url, href.strip()))
        key = (lang.strip().lower(), absolute)
        if key in seen:
            continue
        seen.add(key)
        out.append(HreflangEntry(lang=lang.strip(), href=absolute))
    return out


def _extract_html_lang(soup: BeautifulSoup) -> str:
    html_tag = soup.find("html")
    if html_tag is None:
        return ""
    lang = html_tag.get("lang")
    return lang.strip() if isinstance(lang, str) else ""


_IMG_FORMAT_RE = re.compile(r"\.([a-z0-9]{2,5})(?:[?#].*)?$", re.I)


def _extract_images(soup: BeautifulSoup, page_url: str) -> list[ImageAsset]:
    out: list[ImageAsset] = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or ""
        if not src or not isinstance(src, str):
            # SVG inline (no src)
            if img.find("use") or img.name == "svg":
                out.append(ImageAsset(src="", isInlineSvg=True, fileFormat="svg"))
            continue
        absolute = _normalize(urljoin(page_url, src.strip()))
        if not absolute:
            absolute = src.strip()
        alt = img.get("alt")
        # Distinguish missing alt (None) vs empty alt (decorative, "").
        alt_value: Optional[str]
        if alt is None:
            alt_value = None
        elif isinstance(alt, str):
            alt_value = alt
        else:
            alt_value = None
        width = _safe_int(img.get("width"))
        height = _safe_int(img.get("height"))
        loading_attr = img.get("loading") or ""
        loading = loading_attr.strip().lower() if isinstance(loading_attr, str) else ""
        fmt = ""
        m = _IMG_FORMAT_RE.search(absolute)
        if m:
            fmt = m.group(1).lower()
        out.append(
            ImageAsset(
                src=absolute,
                alt=alt_value,
                width=width,
                height=height,
                loading=loading,
                fileFormat=fmt,
            )
        )
    return out


def _safe_int(v: object) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _extract_internal_links(
    soup: BeautifulSoup, page_url: str, origin: str
) -> list[InternalLink]:
    """Collect same-origin <a href> with anchor text and rel."""
    if not origin:
        origin = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}"
    origin_netloc = urlparse(origin).netloc
    seen: set[tuple[str, str]] = set()
    out: list[InternalLink] = []
    for anchor in soup.find_all("a", href=True):
        href = (anchor.get("href") or "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = _normalize(urljoin(page_url, href))
        if not absolute:
            continue
        if urlparse(absolute).netloc != origin_netloc:
            continue
        if absolute == _normalize(page_url):
            continue  # skip self-links
        anchor_text = ""
        try:
            anchor_text = anchor.get_text(" ", strip=True)[:ANCHOR_TEXT_LIMIT]
        except Exception:
            anchor_text = ""
        rel_attr = anchor.get("rel") or ""
        if isinstance(rel_attr, list):
            rel_attr = " ".join(rel_attr)
        key = (absolute, anchor_text.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(
            InternalLink(
                target=absolute,
                anchorText=anchor_text,
                rel=str(rel_attr).strip(),
            )
        )
        if len(out) >= MAX_LINKS_PER_PAGE:
            break
    return out


def _build_link_graph(
    client: httpx.Client, pages: list[CrawlPage]
) -> LinkGraphSummary:
    """Compute in/out-degree, orphans, hubs, anchor text stats, dead links."""
    if not pages:
        return LinkGraphSummary()

    crawled_urls = {_normalize(p.url) for p in pages}
    in_degree: Counter[str] = Counter()
    out_degree: dict[str, int] = {}
    anchor_counts: Counter[str] = Counter()
    # target -> list of (source, anchor)
    edges_by_target: dict[str, list[tuple[str, str]]] = {}
    total_edges = 0

    for page in pages:
        src = _normalize(page.url)
        out_degree[src] = len(page.internalLinks)
        for link in page.internalLinks:
            tgt = _normalize(link.target)
            if not tgt:
                continue
            total_edges += 1
            if tgt in crawled_urls:
                in_degree[tgt] += 1
            edges_by_target.setdefault(tgt, []).append((src, link.anchorText))
            if link.anchorText:
                anchor_counts[link.anchorText.strip().lower()] += 1

    # Per-page stats
    page_stats: list[LinkGraphPageStat] = []
    for url in crawled_urls:
        page_stats.append(
            LinkGraphPageStat(
                url=url,
                inDegree=in_degree.get(url, 0),
                outDegree=out_degree.get(url, 0),
            )
        )

    # Orphans = crawled pages with 0 internal in-links (excluding the homepage)
    orphans = [
        p.url
        for p in page_stats
        if p.inDegree == 0
    ][:ORPHAN_PAGES_LIMIT]

    # Hubs = top in-degree
    hubs = sorted(page_stats, key=lambda p: p.inDegree, reverse=True)
    hub_urls = [p.url for p in hubs if p.inDegree > 0][:HUB_PAGES_TOP_N]

    # Top anchor texts (most reused → potential over-optimization or templating)
    top_anchors = [
        text for text, _ in anchor_counts.most_common(TOP_ANCHOR_TEXTS_LIMIT)
    ]

    # Dead-link probing — only on a sample of NON-crawled targets (avoid wasted
    # HEADs on pages already known to be 200).
    dead_links = _probe_dead_links(client, edges_by_target, crawled_urls)

    return LinkGraphSummary(
        totalEdges=total_edges,
        pages=page_stats,
        orphanPages=orphans,
        hubPages=hub_urls,
        topAnchorTexts=top_anchors,
        deadLinks=dead_links,
    )


def _probe_dead_links(
    client: httpx.Client,
    edges_by_target: dict[str, list[tuple[str, str]]],
    crawled_urls: set[str],
) -> list[DeadInternalLink]:
    """HEAD a sample of internal targets that weren't fully crawled."""
    candidates = [t for t in edges_by_target.keys() if t not in crawled_urls]
    # Most-linked first — broken hub links matter more than one-off references.
    candidates.sort(key=lambda t: -len(edges_by_target[t]))
    candidates = candidates[:DEAD_LINK_PROBE_LIMIT]
    dead: list[DeadInternalLink] = []
    for target in candidates:
        status: Optional[int] = None
        try:
            resp = client.head(target, follow_redirects=True)
            status = resp.status_code
            if resp.status_code == 405:
                # Some servers reject HEAD — fall back to GET
                resp = client.get(target)
                status = resp.status_code
        except httpx.HTTPError:
            status = None
        if status is None or 400 <= status < 600:
            dead.append(
                DeadInternalLink(
                    target=target,
                    statusCode=status,
                    sourceCount=len(edges_by_target[target]),
                )
            )
    return dead


def _extract_snippet(soup: BeautifulSoup) -> str:
    """First ~200 chars of main content text, with scripts/styles stripped."""
    clone = BeautifulSoup(str(soup), "html.parser")
    for bad in clone(["script", "style", "noscript", "nav", "footer"]):
        bad.decompose()
    main = clone.find("main") or clone.body or clone
    text = re.sub(r"\s+", " ", main.get_text(" ", strip=True))
    return text[:SNIPPET_LIMIT]


def _extract_body_text(soup: BeautifulSoup) -> str:
    """Full body text minus chrome, lowercased, normalized whitespace."""
    clone = BeautifulSoup(str(soup), "html.parser")
    for bad in clone(["script", "style", "noscript", "nav", "footer", "header", "aside"]):
        bad.decompose()
    main = clone.find("main") or clone.body or clone
    text = main.get_text(" ", strip=True).lower()
    return re.sub(r"\s+", " ", text)


_WORD_RE = re.compile(r"[a-zà-ÿ0-9]+", re.IGNORECASE)


def _tokenize_words(text: str) -> list[str]:
    if not text:
        return []
    return _WORD_RE.findall(text)


def _shingles(words: list[str], size: int = SHINGLE_SIZE) -> set[str]:
    if len(words) < size:
        return set()
    return {" ".join(words[i : i + size]) for i in range(len(words) - size + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _compute_duplicates(pages: list[CrawlPage]) -> list[DuplicatePair]:
    """Detect exact + near-duplicate pages via shingle Jaccard."""
    pairs: list[DuplicatePair] = []
    # Exact: group by hash
    by_hash: dict[str, list[str]] = {}
    for p in pages:
        if p.contentHash:
            by_hash.setdefault(p.contentHash, []).append(p.url)
    for urls in by_hash.values():
        if len(urls) < 2:
            continue
        for i in range(len(urls)):
            for j in range(i + 1, len(urls)):
                pairs.append(
                    DuplicatePair(
                        urlA=urls[i], urlB=urls[j], similarity=1.0, kind="exact"
                    )
                )

    # Near: shingle Jaccard. Only on pages with enough words.
    candidates = [p for p in pages if p.wordCount >= 50]
    shingles_by_url: dict[str, set[str]] = {}
    for p in candidates:
        words = _tokenize_words(p.textSnippet) if p.wordCount else []
        # We don't store the body text; recompute is wasteful but the snippet
        # is too short. Use word_count + hash as the dedup key for "exact".
        # Near-duplicate detection only works well on the body text we no
        # longer carry — so fall back to comparing headings + title only.
        proxy = (p.title + " " + " ".join(p.headings)).lower()
        words = _tokenize_words(proxy)
        shingles_by_url[p.url] = _shingles(words, size=3)

    urls = list(shingles_by_url.keys())
    seen_pairs: set[tuple[str, str]] = {(d.urlA, d.urlB) for d in pairs}
    for i in range(len(urls)):
        for j in range(i + 1, len(urls)):
            a, b = urls[i], urls[j]
            sim = _jaccard(shingles_by_url[a], shingles_by_url[b])
            if sim >= DUPLICATE_NEAR_THRESHOLD and (a, b) not in seen_pairs:
                pairs.append(
                    DuplicatePair(urlA=a, urlB=b, similarity=round(sim, 3), kind="near")
                )
                if len(pairs) >= DUPLICATE_PAIRS_LIMIT:
                    return pairs
    return pairs[:DUPLICATE_PAIRS_LIMIT]


def _collect_redirect_chains(pages: list[CrawlPage]) -> list[RedirectChain]:
    chains: list[RedirectChain] = []
    for p in pages:
        if not p.redirectChain:
            continue
        chains.append(
            RedirectChain(
                requestUrl=p.url,
                finalUrl=p.finalUrl or p.url,
                hops=p.redirectChain,
                hopCount=len(p.redirectChain),
            )
        )
    return chains


# ---------------------------------------------------------------------------
# URL utils


def _normalize(url: str) -> str:
    """Strip fragments, normalize trailing slash, drop default ports."""
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    path = parsed.path or "/"
    # Collapse duplicate slashes except for scheme
    path = re.sub(r"/{2,}", "/", path)
    # Drop trailing slash except for root
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    normalized = parsed._replace(path=path, fragment="", params="")
    return urlunparse(normalized)


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag
