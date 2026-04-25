"""APScheduler-backed cron jobs.

In-process scheduler that runs alongside the FastAPI app. Jobs iterate over
the rows in the store and call the same refresh functions used by the manual
HTTP endpoints, so behaviour stays consistent.

Toggle with SCHEDULER_ENABLED=1 in env. Cron expressions use the 5-field
format (minute hour day month weekday), evaluated in UTC.

Keep jobs idempotent — APScheduler's `coalesce=True` prevents stacking and
`max_instances=1` blocks concurrent runs of the same job.
"""

from __future__ import annotations

import logging
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from api.config import get_settings
from api.services import perf_monitor as pm
from api.services import seo_tracker as seo
from api.services import sitemap_watcher as sw
from api.services.store import get_store

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None


def start() -> None:
    """Start the scheduler if SCHEDULER_ENABLED=1. Idempotent."""
    global _scheduler
    settings = get_settings()
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled (set SCHEDULER_ENABLED=1 to enable).")
        return
    if _scheduler is not None and _scheduler.running:
        return

    scheduler = BackgroundScheduler(timezone="UTC")

    scheduler.add_job(
        _run_sitemap_refresh,
        CronTrigger.from_crontab(settings.scheduler_sitemap_cron, timezone="UTC"),
        id="sitemap_refresh",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )
    scheduler.add_job(
        _run_perf_refresh,
        CronTrigger.from_crontab(settings.scheduler_perf_cron, timezone="UTC"),
        id="perf_refresh",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )
    scheduler.add_job(
        _run_seo_check,
        CronTrigger.from_crontab(settings.scheduler_seo_cron, timezone="UTC"),
        id="seo_check",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )

    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "Scheduler started: sitemap=%s perf=%s seo=%s",
        settings.scheduler_sitemap_cron,
        settings.scheduler_perf_cron,
        settings.scheduler_seo_cron,
    )


def status() -> dict:
    """Return the active scheduler state for health/debug endpoints."""
    settings = get_settings()
    if _scheduler is None or not _scheduler.running:
        return {"enabled": settings.scheduler_enabled, "running": False, "jobs": []}
    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append(
            {
                "id": job.id,
                "next_run": job.next_run_time.isoformat()
                if job.next_run_time else None,
                "trigger": str(job.trigger),
            }
        )
    return {"enabled": True, "running": True, "jobs": jobs}


def trigger_now(job_id: str) -> bool:
    """Run a job immediately (manual trigger). Returns True if dispatched."""
    handlers = {
        "sitemap_refresh": _run_sitemap_refresh,
        "perf_refresh": _run_perf_refresh,
        "seo_check": _run_seo_check,
    }
    handler = handlers.get(job_id)
    if handler is None:
        return False
    handler()
    return True


def shutdown(wait: bool = False) -> None:
    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown(wait=wait)
    except Exception as e:
        logger.warning("Scheduler shutdown error: %s", e)
    _scheduler = None


# ---------------------------------------------------------------------------
# Job bodies — keep each row's failure isolated so one bad target never
# poisons the rest of the batch.


def _run_sitemap_refresh() -> None:
    store = get_store()
    watches = store.list_sitemaps(limit=500)
    logger.info("Cron sitemap_refresh: %d watch(es)", len(watches))
    for watch in watches:
        try:
            sw.refresh_watch(watch)
        except Exception as e:
            logger.warning("Sitemap refresh failed for %s: %s", watch.domain, e)


def _run_perf_refresh() -> None:
    store = get_store()
    monitors = store.list_perfs(limit=500)
    logger.info("Cron perf_refresh: %d monitor(s)", len(monitors))
    for monitor in monitors:
        try:
            pm.watch_url(monitor.url, strategy=monitor.strategy)
        except Exception as e:
            logger.warning("Perf refresh failed for %s: %s", monitor.url, e)


def _run_seo_check() -> None:
    store = get_store()
    campaigns = store.list_seo(limit=500)
    logger.info("Cron seo_check: %d campaign(s)", len(campaigns))
    for campaign in campaigns:
        try:
            seo.run_check(campaign.id)
        except Exception as e:
            logger.warning("SEO check failed for %s: %s", campaign.domain, e)
