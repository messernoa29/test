"""Performance Monitor.

Each monitored URL stores a rolling history of PageSpeed Insights snapshots
so the user can see Core Web Vitals trend over time. The id is a deterministic
hash of url+strategy so re-watching the same URL appends to the existing row.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from api.models import PerfMonitor
from api.services import pagespeed
from api.services.store import get_store

logger = logging.getLogger(__name__)

MAX_HISTORY = 90  # roughly one snapshot per day for 3 months


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _perf_id(url: str, strategy: str) -> str:
    raw = f"{url.lower()}::{strategy.lower()}".encode("utf-8")
    return hashlib.md5(raw).hexdigest()


def watch_url(url: str, strategy: str = "mobile") -> PerfMonitor:
    """Run PSI on the URL, append the snapshot to the monitor row."""
    if strategy not in ("mobile", "desktop"):
        raise ValueError("Stratégie invalide (mobile | desktop).")

    store = get_store()
    monitor_id = _perf_id(url, strategy)
    existing: Optional[PerfMonitor] = store.get_perf(monitor_id)

    snapshot = pagespeed.fetch_performance(url, strategy=strategy)

    if existing is None:
        monitor = PerfMonitor(
            id=monitor_id,
            url=url,
            strategy=strategy,
            createdAt=_now_iso(),
            updatedAt=_now_iso(),
            history=[snapshot],
        )
    else:
        history = list(existing.history) + [snapshot]
        if len(history) > MAX_HISTORY:
            history = history[-MAX_HISTORY:]
        monitor = existing.model_copy(
            update={
                "history": history,
                "updatedAt": _now_iso(),
            }
        )

    store.save_perf(monitor)
    return monitor
