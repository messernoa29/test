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

import logging
import re
from collections import deque
from datetime import datetime, timezone
from typing import Iterable, Optional
from urllib.parse import urljoin, urlparse, urlunparse
from xml.etree import ElementTree as ET

import httpx
from bs4 import BeautifulSoup

from api.models import CrawlData, CrawlPage
from api.services import playwright_fetcher, schema_detector

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (compatible; AuditBureauBot/0.1; +https://audit-bureau.local)"
)
REQUEST_TIMEOUT = 15.0
MAX_PAGES = 25  # hard cap on fully-fetched pages
MAX_DISCOVERY_LINKS = 120  # cap on URLs discovered before trimming
HEADING_LIMIT = 8
SNIPPET_LIMIT = 200


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

        pages: list[CrawlPage] = []
        for target in discovered[:MAX_PAGES]:
            page = _fetch_page(client, target)
            if page is not None:
                pages.append(page)
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

    # httpx picks encoding from the Content-Type header; fall back to the
    # document's apparent encoding when headers are unreliable.
    try:
        text = resp.text
        # Heuristic: a glut of replacement chars signals a mismatch
        if text.count("�") > 10:
            raise UnicodeDecodeError("httpx", b"", 0, 1, "too many replacement chars")
    except (UnicodeDecodeError, LookupError):
        apparent = _guess_encoding(resp.content)
        try:
            text = resp.content.decode(apparent, errors="replace")
        except Exception:
            text = resp.content.decode("utf-8", errors="replace")
    return text


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


def _fetch_page(client: httpx.Client, url: str) -> Optional[CrawlPage]:
    html = _fetch_html(client, url)
    if html is None:
        return None

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

    return CrawlPage(
        url=url,
        title=title,
        h1=h1,
        metaDescription=meta_desc,
        headings=headings,
        textSnippet=snippet,
        schemas=schemas,
        renderedWithPlaywright=rendered_with_playwright,
    )


def _extract_snippet(soup: BeautifulSoup) -> str:
    """First ~200 chars of main content text, with scripts/styles stripped."""
    for bad in soup(["script", "style", "noscript", "nav", "footer"]):
        bad.decompose()
    main = soup.find("main") or soup.body or soup
    text = re.sub(r"\s+", " ", main.get_text(" ", strip=True))
    return text[:SNIPPET_LIMIT]


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
