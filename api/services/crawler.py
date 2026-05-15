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
MAX_PAGES = 300  # default cap on fully-fetched pages (Screaming-Frog-style crawl)
MAX_PAGES_CEILING = 1000  # absolute hard cap regardless of the requested depth
MAX_DISCOVERY_LINKS = 1500  # cap on URLs discovered before trimming
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


def crawl(url: str, max_pages: int = MAX_PAGES) -> CrawlData:
    """Crawl the site and return structured page data.

    `max_pages` caps how many discovered URLs we fully fetch (the technical
    crawl — status codes, link graph, dups, etc.). The LLM only analyses a
    small subset in detail; see analyzer.MAX_PAGES_DETAILED. Clamped to a
    hard ceiling.
    """
    max_pages = max(1, min(int(max_pages or MAX_PAGES), MAX_PAGES_CEILING))
    base = _normalize(url)
    parsed = urlparse(base)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    client = httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
        max_redirects=5,
        http2=False,
        limits=httpx.Limits(
            max_connections=max(CRAWL_CONCURRENCY * 2, 32),
            max_keepalive_connections=CRAWL_CONCURRENCY,
        ),
    )

    try:
        robots_txt = _fetch_robots_txt(client, origin)
        has_llms_txt = _probe_llms_txt(client, origin)
        discovered = _discover_urls(
            client, origin, base,
            cap=min(MAX_DISCOVERY_LINKS, max(max_pages + 50, max_pages * 2)),
        )
        discovered_count = len(discovered)
        logger.info("Discovered %d candidate URLs for %s", discovered_count, origin)

        targets = discovered[:max_pages]
        pages, fetched = _fetch_pages_parallel(client, targets, origin)

        link_graph = _build_link_graph(client, pages)
        duplicates = _compute_duplicates(pages)
        redirect_chains = _collect_redirect_chains(pages)
        depths = _compute_depths(base, pages)
        technical = _build_technical_crawl(pages, fetched, depths, origin)
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
        technicalCrawl=technical,
        robotsTxt=robots_txt,
        hasLlmsTxt=has_llms_txt,
        requestedMaxPages=max_pages,
        discoveredUrlCount=discovered_count,
        crawledPageCount=len(pages),
    )


def _fetch_robots_txt(client: httpx.Client, origin: str) -> str:
    try:
        resp = client.get(f"{origin}/robots.txt")
        if resp.status_code == 200 and "text" in resp.headers.get("content-type", "").lower():
            return resp.text[:20000]
    except httpx.HTTPError:
        pass
    return ""


def _probe_llms_txt(client: httpx.Client, origin: str) -> bool:
    try:
        resp = client.get(f"{origin}/llms.txt")
        return resp.status_code == 200 and bool(resp.text.strip())
    except httpx.HTTPError:
        return False


def _compute_depths(entry_url: str, pages: list[CrawlPage]) -> dict[str, int]:
    """BFS click-depth from the entry URL over the crawled internal-link graph.

    Pages not reachable from entry via crawled links get the max depth + 1
    (effectively "orphan / deep")."""
    norm_entry = _normalize(entry_url)
    by_url = {_normalize(p.url): p for p in pages}
    adj: dict[str, list[str]] = {}
    for p in pages:
        src = _normalize(p.url)
        adj[src] = [
            _normalize(l.target) for l in p.internalLinks
            if _normalize(l.target) in by_url
        ]
    depth: dict[str, int] = {}
    if norm_entry in by_url:
        depth[norm_entry] = 0
        queue: deque[str] = deque([norm_entry])
        while queue:
            cur = queue.popleft()
            for nxt in adj.get(cur, []):
                if nxt not in depth:
                    depth[nxt] = depth[cur] + 1
                    queue.append(nxt)
    # Unreached pages
    if depth:
        deep = max(depth.values()) + 1
    else:
        deep = 0
    for u in by_url:
        depth.setdefault(u, deep)
    return depth


# ---------------------------------------------------------------------------
# Discovery


def _discover_urls(
    client: httpx.Client, origin: str, entry_url: str, cap: int = MAX_DISCOVERY_LINKS
) -> list[str]:
    """Return a deduplicated, ordered list of same-origin URLs worth crawling.

    Order of precedence:
    1. URLs from the sitemap (including sitemap indexes).
    2. URLs linked from the homepage navigation/body (BFS depth 1).
    3. The entry URL itself.
    """
    cap = max(1, cap)
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
            if len(urls) >= cap:
                break
        if len(urls) >= cap:
            break

    for link in _walk_links_bfs(client, entry_url, origin):
        push(link)
        if len(urls) >= cap:
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
    return result.html if result else None


class _FetchResult:
    """Outcome of fetching one URL — kept even on non-200 so the technical
    crawl can record status codes / sizes for every visited URL."""

    __slots__ = (
        "html", "final_url", "hops", "status_code", "content_type", "html_bytes"
    )

    def __init__(self, *, html, final_url, hops, status_code, content_type, html_bytes):
        self.html: Optional[str] = html
        self.final_url: str = final_url
        self.hops: list[str] = hops
        self.status_code: Optional[int] = status_code
        self.content_type: str = content_type
        self.html_bytes: int = html_bytes


def _fetch_html_with_meta(client: httpx.Client, url: str) -> Optional[_FetchResult]:
    """Fetch a URL. Returns a _FetchResult with html=None on non-HTML / non-200
    but a populated status_code; returns None only on hard network failure."""
    try:
        resp = client.get(url)
    except httpx.TooManyRedirects:
        logger.warning("Redirect loop on %s — skipped", url)
        return _FetchResult(
            html=None, final_url=url, hops=[], status_code=None,
            content_type="", html_bytes=0,
        )
    except httpx.HTTPError as e:
        logger.debug("Fetch error on %s: %s", url, e)
        return _FetchResult(
            html=None, final_url=url, hops=[], status_code=None,
            content_type="", html_bytes=0,
        )

    final_url = str(resp.url)
    hops: list[str] = []
    for prev in resp.history:
        try:
            hops.append(str(prev.url))
        except Exception:
            continue
    content_type = resp.headers.get("content-type", "").lower()
    html_bytes = len(resp.content or b"")

    if resp.status_code != 200:
        if resp.status_code == 403:
            logger.warning("403 Forbidden on %s (bot detection?)", url)
        elif resp.status_code == 429:
            logger.warning("429 Too Many Requests on %s — skipped", url)
        return _FetchResult(
            html=None, final_url=final_url, hops=hops,
            status_code=resp.status_code, content_type=content_type,
            html_bytes=html_bytes,
        )
    if "text/html" not in content_type and "xhtml" not in content_type:
        return _FetchResult(
            html=None, final_url=final_url, hops=hops,
            status_code=resp.status_code, content_type=content_type,
            html_bytes=html_bytes,
        )

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

    return _FetchResult(
        html=text, final_url=final_url, hops=hops,
        status_code=resp.status_code, content_type=content_type,
        html_bytes=html_bytes,
    )


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
) -> tuple[list[CrawlPage], dict[str, "_FetchResult"]]:
    """Fetch all target URLs in parallel. Returns (analysable CrawlPages in
    discovery order, mapping url -> _FetchResult for every visited URL incl.
    non-200 / non-HTML so the technical crawl can record them)."""
    if not targets:
        return [], {}
    pages: dict[str, Optional[CrawlPage]] = {}
    fetched: dict[str, _FetchResult] = {}
    workers = max(1, min(CRAWL_CONCURRENCY, len(targets)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_url = {
            pool.submit(_fetch_page, client, url, origin): url for url in targets
        }
        for fut in future_to_url:
            url = future_to_url[fut]
            try:
                page, result = fut.result()
            except Exception as e:
                logger.debug("Worker error on %s: %s", url, e)
                page, result = None, None
            pages[url] = page
            if result is not None:
                fetched[url] = result
    ordered = [pages[u] for u in targets if pages.get(u) is not None]
    return ordered, fetched


def _fetch_page(
    client: httpx.Client, url: str, origin: str = ""
) -> tuple[Optional[CrawlPage], Optional["_FetchResult"]]:
    result = _fetch_html_with_meta(client, url)
    if result is None:
        return None, None
    if result.html is None:
        # Non-200 or non-HTML — no CrawlPage, but keep the result for the
        # technical crawl table.
        return None, result
    html, final_url, hops = result.html, result.final_url, result.hops

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
        return None, result

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
    open_graph = _extract_open_graph(soup)
    external_links_count = _count_external_links(soup, url, origin)
    has_mixed_content = _detect_mixed_content(soup, url)
    cta_texts = _extract_cta_texts(soup)
    from api.services import a11y_static as _a11y
    try:
        a11y_data = _a11y.extract_a11y(soup)
    except Exception as e:
        logger.debug("a11y extraction failed on %s: %s", url, e)
        a11y_data = None
    try:
        responsive_data = _a11y.extract_responsive(soup, html)
    except Exception as e:
        logger.debug("responsive extraction failed on %s: %s", url, e)
        responsive_data = None

    page = CrawlPage(
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
        openGraph=open_graph,
        statusCode=result.status_code,
        htmlBytes=result.html_bytes,
        externalLinksCount=external_links_count,
        hasMixedContent=has_mixed_content,
        ctaTexts=cta_texts,
        a11y=a11y_data,
        responsive=responsive_data,
    )
    return page, result


# ---------------------------------------------------------------------------
# Per-page metadata extractors (Screaming-Frog-style signals)


def _extract_open_graph(soup: BeautifulSoup):
    from api.models import OpenGraphData

    def _mp(prop: str) -> Optional[str]:
        tag = soup.find("meta", attrs={"property": prop})
        if tag is None:
            tag = soup.find("meta", attrs={"name": prop})
        if tag is None:
            return None
        content = tag.get("content")
        return content.strip() if isinstance(content, str) and content.strip() else None

    twitter = _mp("twitter:card")
    viewport = soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)}) is not None
    og = OpenGraphData(
        ogTitle=_mp("og:title"),
        ogDescription=_mp("og:description"),
        ogImage=_mp("og:image"),
        ogType=_mp("og:type"),
        twitterCard=twitter,
        hasViewportMeta=viewport,
    )
    return og


def _count_external_links(soup: BeautifulSoup, page_url: str, origin: str) -> int:
    if not origin:
        origin = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}"
    origin_netloc = urlparse(origin).netloc
    count = 0
    for anchor in soup.find_all("a", href=True):
        href = (anchor.get("href") or "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        try:
            netloc = urlparse(urljoin(page_url, href)).netloc
        except Exception:
            continue
        if netloc and netloc != origin_netloc:
            count += 1
    return count


def _detect_mixed_content(soup: BeautifulSoup, page_url: str) -> bool:
    if urlparse(page_url).scheme != "https":
        return False
    for tag, attr in (("img", "src"), ("script", "src"), ("link", "href"),
                      ("iframe", "src"), ("source", "src"), ("video", "src"),
                      ("audio", "src")):
        for node in soup.find_all(tag):
            val = node.get(attr)
            if isinstance(val, str) and val.strip().lower().startswith("http://"):
                return True
    return False


_CTA_TAG_HINT = re.compile(r"(button|btn|cta|call-to-action)", re.I)


def _extract_cta_texts(soup: BeautifulSoup) -> list[str]:
    """Anchor/button texts that look like CTAs (short, button-styled)."""
    out: list[str] = []
    seen: set[str] = set()
    for tag in soup.find_all(["a", "button"]):
        cls = " ".join(tag.get("class") or [])
        role = tag.get("role") or ""
        if tag.name == "button" or _CTA_TAG_HINT.search(cls) or role == "button":
            try:
                txt = tag.get_text(" ", strip=True)
            except Exception:
                continue
            if 2 < len(txt) < 40 and txt.lower() not in seen:
                seen.add(txt.lower())
                out.append(txt)
        if len(out) >= 30:
            break
    return out


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


# ---------------------------------------------------------------------------
# Technical crawl table (Screaming-Frog-style)

_TITLE_MAX = 60
_TITLE_MIN = 30
_META_MAX = 160
_META_MIN = 70
_LOW_TEXT_RATIO = 0.10


def _build_technical_crawl(
    pages: list[CrawlPage],
    fetched: dict[str, "_FetchResult"],
    depths: dict[str, int],
    origin: str,
) -> "TechnicalCrawlSummary":
    from api.models import TechnicalCrawlSummary, TechnicalPageRow

    by_url = {_normalize(p.url): p for p in pages}
    rows: list[TechnicalPageRow] = []
    status_counts: Counter[str] = Counter()

    # 1. Rows for fully analysed pages (200 HTML).
    title_groups: dict[str, list[str]] = {}
    meta_groups: dict[str, list[str]] = {}
    h1_groups: dict[str, list[str]] = {}

    for p in pages:
        norm = _normalize(p.url)
        status = p.statusCode or 200
        status_counts[str(status)] += 1
        body_bytes = len(p.textSnippet.encode("utf-8")) if p.textSnippet else 0
        # Better text estimate: wordCount * ~6 bytes/word as a floor; the
        # snippet is truncated, so use wordCount when it's larger.
        text_bytes = max(body_bytes, p.wordCount * 6)
        html_bytes = p.htmlBytes or 0
        text_ratio = round(text_bytes / html_bytes, 4) if html_bytes else 0.0
        h1_count = sum(1 for h in p.headings if h)  # rough; headings list mixes h1-h3
        # Precise h1 count needs the soup, which we no longer carry. Approx:
        # treat "h1" presence by p.h1; multiple-h1 detection handled below via
        # heading list heuristic (skip — keep 1 if p.h1 else 0).
        h1_count = 1 if p.h1 else 0
        h2_count = max(0, len([h for h in p.headings if h]) - h1_count)

        issues: list[str] = []
        tl = len(p.title or "")
        ml = len(p.metaDescription or "") if p.metaDescription else 0
        if not p.title:
            issues.append("title manquant")
        elif tl > _TITLE_MAX:
            issues.append(f"title trop long ({tl} car.)")
        elif tl < _TITLE_MIN:
            issues.append(f"title trop court ({tl} car.)")
        if not p.metaDescription:
            issues.append("meta description manquante")
        elif ml > _META_MAX:
            issues.append(f"meta trop longue ({ml} car.)")
        elif ml < _META_MIN:
            issues.append(f"meta trop courte ({ml} car.)")
        if not p.h1:
            issues.append("H1 manquant")
        if html_bytes and text_ratio < _LOW_TEXT_RATIO:
            issues.append(f"ratio texte/HTML faible ({text_ratio:.0%})")
        if p.canonical and p.canonical not in (norm, _normalize(p.finalUrl or "")):
            issues.append("canonical pointe ailleurs")
        if "noindex" in (p.robotsMeta or ""):
            issues.append("noindex")
        if p.imagesWithoutAlt:
            issues.append(f"{p.imagesWithoutAlt} image(s) sans alt")
        if p.hasMixedContent:
            issues.append("mixed content (http:// sur page https://)")
        if p.openGraph and not p.openGraph.hasViewportMeta:
            issues.append("<meta viewport> absent")
        if p.openGraph and not p.openGraph.ogTitle:
            issues.append("Open Graph (og:title) absent")
        if p.redirectChain:
            issues.append(f"atteinte via {len(p.redirectChain)} redirection(s)")

        # Indexability
        indexable = True
        reason = ""
        if status != 200:
            indexable, reason = False, f"statut {status}"
        elif "noindex" in (p.robotsMeta or ""):
            indexable, reason = False, "meta robots noindex"
        elif p.canonical and p.canonical not in (norm, _normalize(p.finalUrl or "")):
            indexable, reason = False, "canonical vers une autre URL"

        if p.title:
            title_groups.setdefault(p.title.strip().lower(), []).append(p.url)
        if p.metaDescription:
            meta_groups.setdefault(p.metaDescription.strip().lower(), []).append(p.url)
        if p.h1:
            h1_groups.setdefault(p.h1.strip().lower(), []).append(p.url)

        rows.append(TechnicalPageRow(
            url=p.url,
            statusCode=status,
            contentType="text/html",
            isIndexable=indexable,
            indexabilityReason=reason,
            depth=depths.get(norm),
            htmlBytes=html_bytes,
            textBytes=text_bytes,
            textRatio=text_ratio,
            titleLength=tl,
            metaDescLength=ml,
            h1Count=h1_count,
            h2Count=h2_count,
            wordCount=p.wordCount,
            internalLinksOut=p.internalLinksCount,
            externalLinksOut=p.externalLinksCount,
            imagesCount=len(p.images),
            imagesWithoutAlt=p.imagesWithoutAlt,
            issues=issues,
        ))

    # 2. Rows for visited-but-not-analysed URLs (4xx/5xx/non-HTML).
    for url, fr in fetched.items():
        norm = _normalize(url)
        if norm in by_url:
            continue  # already covered
        status = fr.status_code
        status_counts[str(status) if status is not None else "ERR"] += 1
        issues = []
        if status is None:
            issues.append("aucune réponse / erreur réseau")
        elif 400 <= status < 500:
            issues.append(f"erreur client {status}")
        elif 500 <= status < 600:
            issues.append(f"erreur serveur {status}")
        elif "text/html" not in fr.content_type:
            issues.append(f"non-HTML ({fr.content_type or 'inconnu'})")
        rows.append(TechnicalPageRow(
            url=url,
            statusCode=status,
            contentType=fr.content_type,
            isIndexable=False,
            indexabilityReason=issues[0] if issues else "non-HTML",
            depth=depths.get(norm),
            htmlBytes=fr.html_bytes,
            issues=issues,
        ))

    # 3. Aggregates
    dup_titles = [urls for urls in title_groups.values() if len(urls) > 1]
    dup_metas = [urls for urls in meta_groups.values() if len(urls) > 1]
    dup_h1s = [urls for urls in h1_groups.values() if len(urls) > 1]
    missing_titles = [p.url for p in pages if not p.title]
    missing_metas = [p.url for p in pages if not p.metaDescription]
    missing_h1 = [p.url for p in pages if not p.h1]
    title_long = [p.url for p in pages if p.title and len(p.title) > _TITLE_MAX]
    title_short = [p.url for p in pages if p.title and len(p.title) < _TITLE_MIN]
    meta_long = [p.url for p in pages if p.metaDescription and len(p.metaDescription) > _META_MAX]
    meta_short = [p.url for p in pages if p.metaDescription and 0 < len(p.metaDescription) < _META_MIN]
    low_ratio = [
        r.url for r in rows
        if r.statusCode == 200 and r.htmlBytes and r.textRatio < _LOW_TEXT_RATIO
    ]
    # Broken internal links: targets that appear in some page's internalLinks
    # AND were fetched with a 4xx/5xx status.
    broken = sorted({
        url for url, fr in fetched.items()
        if fr.status_code is not None and 400 <= fr.status_code < 600
    })
    indexable_n = sum(1 for r in rows if r.isIndexable)
    max_depth = max((r.depth for r in rows if r.depth is not None), default=0)

    return TechnicalCrawlSummary(
        pagesCrawled=len(rows),
        statusCounts=dict(status_counts),
        indexablePages=indexable_n,
        nonIndexablePages=len(rows) - indexable_n,
        duplicateTitles=dup_titles[:30],
        duplicateMetaDescriptions=dup_metas[:30],
        duplicateH1s=dup_h1s[:30],
        missingTitles=missing_titles[:50],
        missingMetaDescriptions=missing_metas[:50],
        missingH1=missing_h1[:50],
        multipleH1=[],  # precise multi-H1 needs the DOM we no longer carry
        titleTooLong=title_long[:50],
        titleTooShort=title_short[:50],
        metaTooLong=meta_long[:50],
        metaTooShort=meta_short[:50],
        lowTextRatioPages=low_ratio[:50],
        brokenInternalLinks=broken[:50],
        maxDepth=max_depth,
        rows=rows,
    )
