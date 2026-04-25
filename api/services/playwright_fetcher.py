"""Headless browser fallback for JavaScript-rendered sites.

Our primary crawler uses `httpx` + BeautifulSoup, which is fast and cheap but
blind to client-side rendering. A React/Vue/Angular SPA typically ships an
almost-empty `<body>` with a `<div id="root"></div>` placeholder; the real
content only appears after the JS bundle executes.

This service is the escape hatch:
1. `fetch_rendered(url)` launches a headless Chromium, waits for `domcontentloaded`
   plus a short settle window, returns the resulting HTML (post-JS).
2. `looks_like_spa(html)` heuristically detects a shell so the crawler knows
   when to pay the Playwright cost (≈ 1s startup + 1-3s per page).

Gated by `PLAYWRIGHT_ENABLED=true` in the env. When disabled (default in
dev), nothing changes — the crawler keeps its current behaviour.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

_PLAYWRIGHT_TIMEOUT_MS = 15_000  # per-page hard cap
_SETTLE_DELAY_MS = 800           # time to let late renders finish
_VIEWPORT = {"width": 1280, "height": 900}
_USER_AGENT = (
    "Mozilla/5.0 (compatible; AuditBureauBot/0.1; +https://audit-bureau.local)"
)

# Import is deliberately lazy: the module can still be imported in envs where
# playwright isn't installed (e.g. unit tests that don't touch the crawler).
_PLAYWRIGHT_AVAILABLE: Optional[bool] = None


def is_enabled() -> bool:
    """`PLAYWRIGHT_ENABLED=true|1|yes` gates the whole subsystem."""
    raw = (os.getenv("PLAYWRIGHT_ENABLED", "") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _check_available() -> bool:
    global _PLAYWRIGHT_AVAILABLE
    if _PLAYWRIGHT_AVAILABLE is not None:
        return _PLAYWRIGHT_AVAILABLE
    try:
        import playwright.sync_api  # noqa: F401
        _PLAYWRIGHT_AVAILABLE = True
    except ImportError:
        _PLAYWRIGHT_AVAILABLE = False
        logger.info("Playwright not installed — JS fallback disabled")
    return _PLAYWRIGHT_AVAILABLE


def fetch_rendered(url: str) -> Optional[str]:
    """Render `url` in headless Chromium and return the DOM HTML.

    Returns None on any failure (timeout, browser launch, nav error) so the
    caller can keep the plain-HTTP result.
    """
    if not is_enabled() or not _check_available():
        return None

    # Local import so module load stays cheap when the feature is off.
    from playwright.sync_api import Error as PWError
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    user_agent=_USER_AGENT,
                    viewport=_VIEWPORT,
                    java_script_enabled=True,
                    ignore_https_errors=True,
                )
                page = context.new_page()
                page.set_default_timeout(_PLAYWRIGHT_TIMEOUT_MS)
                try:
                    page.goto(url, wait_until="domcontentloaded")
                except PWTimeout:
                    logger.warning("Playwright domcontentloaded timeout on %s", url)
                    return None
                # Let post-hydration scripts settle a bit
                try:
                    page.wait_for_timeout(_SETTLE_DELAY_MS)
                except PWError:
                    pass
                try:
                    html = page.content()
                except PWError as e:
                    logger.warning("Playwright page.content() failed on %s: %s", url, e)
                    return None
                return html
            finally:
                browser.close()
    except Exception as e:
        logger.warning("Playwright fetch failed on %s: %s", url, e)
        return None


# ---------------------------------------------------------------------------
# Heuristics


_TEXT_STRIPPER = re.compile(
    r"<script[\s\S]*?</script>|<style[\s\S]*?</style>|<[^>]+>", re.IGNORECASE
)
_SPA_HINTS = (
    '<div id="root"',
    "<div id='root'",
    '<div id="app"',
    "<div id='app'",
    '<div id="__next"',
    'data-reactroot',
    'ng-version=',
    'data-v-app',
)


def looks_like_spa(html: str) -> bool:
    """Heuristic: is this page mostly a JS shell waiting to render?

    Returns True when the visible text is short *and* the markup contains
    classic SPA anchor points. Tuned to be conservative — a normal HTML
    article with 150 words of text won't match.
    """
    if not html:
        return False
    # Visible text after stripping tags, scripts, styles
    text = _TEXT_STRIPPER.sub("", html)
    text = re.sub(r"\s+", " ", text).strip()
    visible_len = len(text)

    has_hint = any(hint in html for hint in _SPA_HINTS)
    if visible_len < 200 and has_hint:
        return True
    # Extreme case: absolutely empty body with a script-heavy shell.
    if visible_len < 60 and ("<script" in html or "</script>" in html):
        return True
    return False
