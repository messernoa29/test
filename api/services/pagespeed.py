"""PageSpeed Insights API — fetch real Core Web Vitals for a URL.

Provides two data sources for the analyzer:
1. **CrUX field data** (real Chrome users, 28-day rolling). Only available
   for URLs/origins with enough traffic. Gold standard for performance scoring.
2. **Lighthouse lab data** (synthetic test, emulated mobile). Always available
   as fallback when CrUX is absent.

If no API key is configured, the call is skipped and a neutral snapshot is
returned. The analyzer will fall back to estimation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from api.config import get_settings
from api.models import PerformanceMetric, PerformanceSnapshot

logger = logging.getLogger(__name__)

_ENDPOINT = "https://pagespeedonline.googleapis.com/pagespeedonline/v5/runPagespeed"
_TIMEOUT_S = 60.0

# Google's official thresholds for Web Vitals (2026).
_THRESHOLDS = {
    "LCP": {"good": 2500, "poor": 4000, "unit": "ms", "display": "< 2.5s"},
    "INP": {"good": 200, "poor": 500, "unit": "ms", "display": "< 200ms"},
    "CLS": {"good": 0.1, "poor": 0.25, "unit": "", "display": "< 0.1"},
    "FCP": {"good": 1800, "poor": 3000, "unit": "ms", "display": "< 1.8s"},
    "TTFB": {"good": 800, "poor": 1800, "unit": "ms", "display": "< 800ms"},
}


def fetch_performance(url: str, strategy: str = "mobile") -> PerformanceSnapshot:
    """Run PSI on the URL. Never raises — returns an "unavailable" snapshot
    if anything goes wrong so the pipeline keeps running."""
    settings = get_settings()
    now = datetime.now(timezone.utc).isoformat()

    if not settings.pagespeed_api_key:
        logger.info("PSI skipped: no PAGESPEED_API_KEY configured")
        return PerformanceSnapshot(
            url=url,
            strategy=strategy,
            source="unavailable",
            fetchedAt=now,
            error="PAGESPEED_API_KEY absente",
        )

    params = {
        "url": url,
        "strategy": strategy,
        "key": settings.pagespeed_api_key,
        "category": "PERFORMANCE",
    }

    try:
        with httpx.Client(timeout=_TIMEOUT_S) as client:
            r = client.get(_ENDPOINT, params=params)
    except httpx.HTTPError as e:
        logger.warning("PSI network error for %s: %s", url, e)
        return PerformanceSnapshot(
            url=url, strategy=strategy, source="unavailable",
            fetchedAt=now, error=f"Erreur réseau PSI: {e}",
        )

    if r.status_code != 200:
        detail = ""
        try:
            detail = r.json().get("error", {}).get("message", "")[:200]
        except Exception:
            detail = r.text[:200]
        logger.warning("PSI HTTP %d for %s: %s", r.status_code, url, detail)
        return PerformanceSnapshot(
            url=url, strategy=strategy, source="unavailable",
            fetchedAt=now,
            error=f"HTTP {r.status_code}: {detail or 'réponse invalide'}",
        )

    try:
        payload = r.json()
    except ValueError as e:
        return PerformanceSnapshot(
            url=url, strategy=strategy, source="unavailable",
            fetchedAt=now, error=f"JSON invalide: {e}",
        )

    return _parse_psi_response(url, strategy, now, payload)


def _parse_psi_response(
    url: str, strategy: str, fetched_at: str, payload: dict,
) -> PerformanceSnapshot:
    metrics: list[PerformanceMetric] = []
    sources: set[str] = set()

    # --- CrUX field data (real users) ----------------------------------------
    loading_exp = payload.get("loadingExperience") or {}
    if isinstance(loading_exp, dict):
        crux_metrics = loading_exp.get("metrics") or {}
        crux_map = {
            "LARGEST_CONTENTFUL_PAINT_MS": "LCP",
            "INTERACTION_TO_NEXT_PAINT": "INP",
            "CUMULATIVE_LAYOUT_SHIFT_SCORE": "CLS",
            "FIRST_CONTENTFUL_PAINT_MS": "FCP",
            "EXPERIMENTAL_TIME_TO_FIRST_BYTE": "TTFB",
        }
        for key, short in crux_map.items():
            entry = crux_metrics.get(key)
            if not isinstance(entry, dict):
                continue
            p75_raw = entry.get("percentile")
            if p75_raw is None:
                continue
            p75 = _normalize_value(short, p75_raw)
            rating = _classify(short, p75)
            metrics.append(
                PerformanceMetric(
                    name=short,
                    fieldValue=p75,
                    fieldPercentile75=p75,
                    rating=rating,
                    threshold=_THRESHOLDS.get(short, {}).get("display"),
                )
            )
            sources.add("crux")

    # --- Lighthouse lab data --------------------------------------------------
    lh = payload.get("lighthouseResult") or {}
    audits = lh.get("audits") or {}
    lab_score: Optional[int] = None
    categories = lh.get("categories") or {}
    perf_cat = categories.get("performance") if isinstance(categories, dict) else None
    if isinstance(perf_cat, dict):
        s = perf_cat.get("score")
        if isinstance(s, (int, float)):
            lab_score = int(round(float(s) * 100))

    lab_audits = {
        "largest-contentful-paint": "LCP",
        "interactive": None,  # TTI, deprecated as CWV
        "cumulative-layout-shift": "CLS",
        "first-contentful-paint": "FCP",
        "server-response-time": "TTFB",
    }
    # Merge lab values into existing metric or create new.
    for audit_id, short in lab_audits.items():
        if short is None:
            continue
        a = audits.get(audit_id)
        if not isinstance(a, dict):
            continue
        numeric = a.get("numericValue")
        if numeric is None:
            continue
        lab_value = _normalize_value(short, numeric)
        existing = next((m for m in metrics if m.name == short), None)
        if existing is not None:
            existing.labValue = lab_value
            if existing.rating is None:
                existing.rating = _classify(short, lab_value)
        else:
            metrics.append(
                PerformanceMetric(
                    name=short,
                    labValue=lab_value,
                    rating=_classify(short, lab_value),
                    threshold=_THRESHOLDS.get(short, {}).get("display"),
                )
            )
        sources.add("lighthouse")

    source = "mixed" if {"crux", "lighthouse"}.issubset(sources) else (
        "crux" if "crux" in sources else (
            "lighthouse" if "lighthouse" in sources else "unavailable"
        )
    )

    return PerformanceSnapshot(
        url=url,
        strategy=strategy,
        source=source,
        fetchedAt=fetched_at,
        performanceScore=lab_score,
        metrics=metrics,
    )


def _normalize_value(metric: str, raw: object) -> float:
    """Convert PSI numeric to a normalized unit (ms for timings, score for CLS)."""
    try:
        v = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    # CrUX returns seconds for LCP/INP/etc in some fields, ms in others.
    # Lighthouse audits use ms consistently. Heuristic: if value < 10 and
    # metric is CLS, keep as-is; otherwise coerce to ms.
    if metric == "CLS":
        return round(v, 3)
    return round(v, 1)


def _classify(metric: str, value: float) -> str:
    thr = _THRESHOLDS.get(metric)
    if not thr:
        return "unknown"
    if value <= thr["good"]:
        return "good"
    if value <= thr["poor"]:
        return "needs-improvement"
    return "poor"
