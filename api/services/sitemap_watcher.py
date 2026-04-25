"""Sitemap watcher.

Each watch is keyed by the site's domain (md5 of domain) so re-watching the
same site updates the existing row instead of creating duplicates. Each refresh
fetches the sitemap, diffs against the previous snapshot, and stores the new
state.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import httpx

from api.models import SitemapDiff, SitemapWatch
from api.services.crawler import USER_AGENT
from api.services.store import get_store

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _watch_id(domain: str) -> str:
    return hashlib.md5(domain.lower().encode("utf-8")).hexdigest()


def watch_site(url: str) -> SitemapWatch:
    """Create the watch row if missing, then refresh it. Returns latest state."""
    parsed = urlparse(url)
    if not parsed.netloc:
        raise ValueError("URL invalide.")
    domain = parsed.netloc.lower()
    store = get_store()
    watch_id = _watch_id(domain)
    existing = store.get_sitemap(watch_id)
    if existing is None:
        existing = SitemapWatch(
            id=watch_id,
            domain=domain,
            sitemapUrl=f"{parsed.scheme}://{parsed.netloc}/sitemap.xml",
            createdAt=_now_iso(),
            updatedAt=_now_iso(),
        )
        store.save_sitemap(existing)
    return refresh_watch(existing)


def refresh_watch(watch: SitemapWatch) -> SitemapWatch:
    store = get_store()
    sitemap_url, urls = _fetch_sitemap_urls(watch.sitemapUrl, watch.domain)

    previous = list(watch.snapshotUrls)
    previous_set = set(previous)
    current_set = set(urls)
    added = sorted(current_set - previous_set)
    removed = sorted(previous_set - current_set)

    diff = SitemapDiff(
        domain=watch.domain,
        sitemapUrl=sitemap_url,
        fetchedAt=_now_iso(),
        previousFetchedAt=watch.updatedAt if previous else None,
        currentCount=len(current_set),
        previousCount=len(previous_set),
        added=added,
        removed=removed,
        unchanged=len(current_set & previous_set),
    )

    updated = watch.model_copy(
        update={
            "sitemapUrl": sitemap_url,
            "updatedAt": diff.fetchedAt,
            "snapshotUrls": sorted(current_set),
            "lastDiff": diff,
        }
    )
    store.save_sitemap(updated)
    return updated


def _fetch_sitemap_urls(default_sitemap: str, domain: str) -> tuple[str, list[str]]:
    """Resolve the active sitemap URL (via robots.txt) and return the URL list."""
    client = httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
        max_redirects=5,
    )
    try:
        origin = f"https://{domain}"
        sitemap_urls = _candidates_from_robots(client, origin) or [default_sitemap]
        urls: list[str] = []
        seen: set[str] = set()
        first_url = sitemap_urls[0]
        for sm in sitemap_urls:
            for loc in _read_sitemap(client, sm, depth=0):
                if loc not in seen:
                    seen.add(loc)
                    urls.append(loc)
                if len(urls) >= 5000:
                    break
            if len(urls) >= 5000:
                break
        if not urls:
            raise ValueError(
                "Aucune URL trouvée dans le sitemap (sitemap vide ou inaccessible)."
            )
        return first_url, urls
    finally:
        client.close()


def _candidates_from_robots(client: httpx.Client, origin: str) -> list[str]:
    out: list[str] = []
    try:
        resp = client.get(f"{origin}/robots.txt")
        if resp.status_code == 200:
            for line in resp.text.splitlines():
                lower = line.strip().lower()
                if lower.startswith("sitemap:"):
                    out.append(line.split(":", 1)[1].strip())
    except httpx.HTTPError:
        pass
    return out


def _read_sitemap(client: httpx.Client, url: str, depth: int) -> Iterable[str]:
    if depth > 2:
        return
    try:
        resp = client.get(url)
    except httpx.HTTPError as e:
        logger.debug("sitemap fetch failed %s: %s", url, e)
        return
    if resp.status_code != 200 or not resp.content:
        return

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError:
        return

    tag = root.tag.split("}", 1)[1] if "}" in root.tag else root.tag
    if tag == "sitemapindex":
        for loc in root.iterfind(".//{*}sitemap/{*}loc"):
            if loc.text:
                yield from _read_sitemap(client, loc.text.strip(), depth + 1)
    elif tag == "urlset":
        for loc in root.iterfind(".//{*}url/{*}loc"):
            if loc.text:
                yield loc.text.strip()
