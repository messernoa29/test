"""SEO Tracker.

Tracks the position of a domain on a list of keywords using DuckDuckGo's HTML
endpoint (no API key required). Each campaign keeps the full reading history
per keyword so the UI can plot trends.

Limitations:
- DuckDuckGo is not Google. Use it for trend signals, not absolute positions.
- For Google rankings, plug a SerpAPI / DataForSEO key in the future and add a
  conditional engine selector here.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from api.models import KeywordReading, SeoCampaign, TrackedKeyword
from api.services.store import get_store

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
DDG_HTML = "https://html.duckduckgo.com/html/"
TIMEOUT_S = 20.0
MAX_POSITION = 100
SLEEP_BETWEEN_QUERIES = 1.0  # be polite, avoid bans


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_domain(domain: str) -> str:
    d = domain.strip().lower()
    if "://" in d:
        d = urlparse(d).netloc or d
    return d.removeprefix("www.")


def _normalize_keywords(raw: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for k in raw:
        cleaned = (k or "").strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned[:120])
    return out


def create_campaign(
    domain: str, keywords: list[str], locale: str = "fr-FR"
) -> SeoCampaign:
    domain_norm = _normalize_domain(domain)
    if not domain_norm:
        raise ValueError("Domaine invalide.")
    kw_clean = _normalize_keywords(keywords)
    if not kw_clean:
        raise ValueError("Aucun mot-clé valide.")

    campaign = SeoCampaign(
        id=uuid.uuid4().hex,
        domain=domain_norm,
        locale=locale,
        createdAt=_now_iso(),
        updatedAt=_now_iso(),
        keywords=[TrackedKeyword(keyword=k) for k in kw_clean],
    )
    get_store().save_seo(campaign)
    return campaign


def add_keywords(campaign_id: str, keywords: list[str]) -> SeoCampaign:
    store = get_store()
    campaign = store.get_seo(campaign_id)
    if campaign is None:
        raise ValueError("Campagne introuvable.")

    existing = {tk.keyword.lower() for tk in campaign.keywords}
    additions = [
        TrackedKeyword(keyword=k)
        for k in _normalize_keywords(keywords)
        if k.lower() not in existing
    ]
    if not additions:
        return campaign
    updated = campaign.model_copy(
        update={
            "keywords": list(campaign.keywords) + additions,
            "updatedAt": _now_iso(),
        }
    )
    store.save_seo(updated)
    return updated


def run_check(campaign_id: str) -> SeoCampaign:
    store = get_store()
    campaign = store.get_seo(campaign_id)
    if campaign is None:
        raise ValueError("Campagne introuvable.")

    new_keywords: list[TrackedKeyword] = []
    with httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept-Language": campaign.locale},
        timeout=TIMEOUT_S,
        follow_redirects=True,
    ) as client:
        for tk in campaign.keywords:
            reading = _check_one(client, campaign.domain, tk.keyword, campaign.locale)
            history = list(tk.history) + [reading]
            # Cap history to ~120 readings.
            if len(history) > 120:
                history = history[-120:]
            new_keywords.append(
                TrackedKeyword(keyword=tk.keyword, history=history)
            )
            time.sleep(SLEEP_BETWEEN_QUERIES)

    updated = campaign.model_copy(
        update={
            "keywords": new_keywords,
            "updatedAt": _now_iso(),
        }
    )
    store.save_seo(updated)
    return updated


def _check_one(
    client: httpx.Client, domain: str, keyword: str, locale: str
) -> KeywordReading:
    region = _ddg_region(locale)
    payload = {"q": keyword, "kl": region, "kp": "-2"}
    try:
        resp = client.post(DDG_HTML, data=payload)
    except httpx.HTTPError as e:
        logger.warning("DDG fetch failed (%s): %s", keyword, e)
        return KeywordReading(
            keyword=keyword, checkedAt=_now_iso(), position=None,
        )

    if resp.status_code != 200:
        logger.warning("DDG HTTP %d on %s", resp.status_code, keyword)
        return KeywordReading(
            keyword=keyword, checkedAt=_now_iso(), position=None,
        )

    position, ranked_url = _find_position(resp.text, domain)
    return KeywordReading(
        keyword=keyword,
        checkedAt=_now_iso(),
        position=position,
        url=ranked_url,
    )


def _find_position(html: str, domain: str) -> tuple[Optional[int], Optional[str]]:
    soup = BeautifulSoup(html, "html.parser")
    target = domain.lower()
    rank = 0
    for anchor in soup.select("a.result__a"):
        href = anchor.get("href", "")
        resolved = _resolve_ddg_url(href)
        if not resolved:
            continue
        rank += 1
        if rank > MAX_POSITION:
            break
        host = urlparse(resolved).netloc.lower().removeprefix("www.")
        if host == target or host.endswith("." + target):
            return rank, resolved
    return None, None


_DDG_REDIRECT = re.compile(r"^/?l/?\?")


def _resolve_ddg_url(href: str) -> Optional[str]:
    if not href:
        return None
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    # DDG wraps results behind /l/?uddg=<encoded>
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        qs = parse_qs(parsed.query)
        target = qs.get("uddg", [None])[0]
        if target:
            return unquote(target)
    if parsed.scheme in ("http", "https"):
        return href
    return None


def _ddg_region(locale: str) -> str:
    """Map ISO locale (fr-FR) to a DuckDuckGo region code (fr-fr)."""
    parts = locale.split("-")
    if len(parts) == 2:
        return f"{parts[0].lower()}-{parts[1].lower()}"
    return "wt-wt"  # worldwide


def domain_id(domain: str) -> str:
    return hashlib.md5(_normalize_domain(domain).encode("utf-8")).hexdigest()
