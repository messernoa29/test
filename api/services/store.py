"""Audit store — in-memory implementation + backend-aware factory.

Two interchangeable backends:
- `InMemoryAuditStore`   — simple dict, fast, process-local, wiped on restart.
- `SqlAuditStore`        — SQLAlchemy-backed, survives restarts (in store_sql).

The factory `get_store()` picks one based on settings. Both expose the exact
same method set, so the routes, runner, etc. never know which is active.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Optional

from api.models import (
    AiVisibilityCheck,
    AuditResult,
    BulkAudit,
    CompetitorBattle,
    ContentBrief,
    CrawlData,
    PerfMonitor,
    SeoCampaign,
    SitemapWatch,
)
from api.services.store_base import AuditJob, JobStatus

# Re-export so the rest of the codebase can keep importing AuditJob / JobStatus
# from `api.services.store`.
__all__ = ["AuditJob", "JobStatus", "get_store"]


MAX_JOBS_RETAINED = 500
MAX_JOB_AGE_DAYS = 14


class InMemoryAuditStore:
    """Process-local store. Kept around for tests and for runs without DB."""

    def __init__(self) -> None:
        self._jobs: dict[str, AuditJob] = {}
        self._battles: dict[str, CompetitorBattle] = {}
        self._briefs: dict[str, ContentBrief] = {}
        self._ai_checks: dict[str, AiVisibilityCheck] = {}
        self._bulks: dict[str, BulkAudit] = {}
        self._sitemaps: dict[str, SitemapWatch] = {}
        self._perfs: dict[str, PerfMonitor] = {}
        self._seo: dict[str, SeoCampaign] = {}
        self._lock = Lock()

    # ------------------------------------------------------------------
    # Job lifecycle

    def create_job(self, job_id: str, url: str, domain: str) -> AuditJob:
        with self._lock:
            self._evict_locked()
            job = AuditJob(
                id=job_id,
                url=url,
                domain=domain,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            self._jobs[job_id] = job
            return job

    def _evict_locked(self) -> None:
        if len(self._jobs) <= MAX_JOBS_RETAINED:
            cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_JOB_AGE_DAYS)
            expired = [
                jid
                for jid, j in self._jobs.items()
                if j.status != "pending" and _parse_iso(j.created_at) < cutoff
            ]
            for jid in expired:
                del self._jobs[jid]
            return

        candidates = [
            (j.created_at, jid)
            for jid, j in self._jobs.items()
            if j.status != "pending"
        ]
        candidates.sort()
        to_drop = len(self._jobs) - MAX_JOBS_RETAINED
        for _, jid in candidates[:to_drop]:
            self._jobs.pop(jid, None)

    def complete_job(self, job_id: str, audit: AuditResult, crawl: CrawlData) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "done"
            job.result = audit
            job.crawl = crawl
            job.error = None

    def fail_job(self, job_id: str, error: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "failed"
            job.error = error

    def get(self, job_id: str) -> Optional[AuditJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def delete(self, job_id: str) -> bool:
        with self._lock:
            return self._jobs.pop(job_id, None) is not None

    def set_archived(self, job_id: str, archived: bool) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job.archived = archived
            return True

    def update_domain(self, job_id: str, domain: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.domain = domain

    # ------------------------------------------------------------------
    # Listings

    def list_recent(
        self, limit: int = 20, include_archived: bool = False
    ) -> list[AuditJob]:
        with self._lock:
            jobs = list(self._jobs.values())
            if not include_archived:
                jobs = [j for j in jobs if not j.archived]
            return jobs[-limit:][::-1]

    def list_archived(self, limit: int = 50) -> list[AuditJob]:
        with self._lock:
            jobs = [j for j in self._jobs.values() if j.archived]
            return jobs[-limit:][::-1]

    def list_by_domain(self, domain: str, limit: int = 20) -> list[AuditJob]:
        needle = domain.lower().removeprefix("www.")
        with self._lock:
            matches = [
                j for j in self._jobs.values()
                if j.domain.lower().removeprefix("www.") == needle
            ]
            matches.sort(key=lambda j: j.created_at, reverse=True)
            return matches[:limit]

    def has_pending(self) -> bool:
        with self._lock:
            return any(j.status == "pending" for j in self._jobs.values())

    def save(self, audit: AuditResult, crawl: CrawlData) -> None:
        with self._lock:
            self._jobs[audit.id] = AuditJob(
                id=audit.id,
                url=audit.url,
                domain=audit.domain,
                created_at=audit.createdAt,
                status="done",
                result=audit,
                crawl=crawl,
            )

    # ------------------------------------------------------------------
    # Competitor battles

    def save_battle(self, battle: CompetitorBattle) -> None:
        with self._lock:
            self._battles[battle.id] = battle

    def get_battle(self, battle_id: str) -> Optional[CompetitorBattle]:
        with self._lock:
            return self._battles.get(battle_id)

    def list_battles(self, limit: int = 20) -> list[CompetitorBattle]:
        with self._lock:
            items = sorted(
                self._battles.values(),
                key=lambda b: b.createdAt,
                reverse=True,
            )
            return items[:limit]

    def delete_battle(self, battle_id: str) -> bool:
        with self._lock:
            return self._battles.pop(battle_id, None) is not None

    # ------------------------------------------------------------------
    # Content briefs

    def save_brief(self, brief: ContentBrief) -> None:
        with self._lock:
            self._briefs[brief.id] = brief

    def get_brief(self, brief_id: str) -> Optional[ContentBrief]:
        with self._lock:
            return self._briefs.get(brief_id)

    def list_briefs(self, limit: int = 20) -> list[ContentBrief]:
        with self._lock:
            items = sorted(
                self._briefs.values(), key=lambda b: b.createdAt, reverse=True,
            )
            return items[:limit]

    def delete_brief(self, brief_id: str) -> bool:
        with self._lock:
            return self._briefs.pop(brief_id, None) is not None

    # ------------------------------------------------------------------
    # AI visibility checks

    def save_ai_check(self, check: AiVisibilityCheck) -> None:
        with self._lock:
            self._ai_checks[check.id] = check

    def get_ai_check(self, check_id: str) -> Optional[AiVisibilityCheck]:
        with self._lock:
            return self._ai_checks.get(check_id)

    def list_ai_checks(self, limit: int = 20) -> list[AiVisibilityCheck]:
        with self._lock:
            items = sorted(
                self._ai_checks.values(), key=lambda c: c.createdAt, reverse=True,
            )
            return items[:limit]

    def delete_ai_check(self, check_id: str) -> bool:
        with self._lock:
            return self._ai_checks.pop(check_id, None) is not None

    # ------------------------------------------------------------------
    # Bulk audits

    def save_bulk(self, bulk: BulkAudit) -> None:
        with self._lock:
            self._bulks[bulk.id] = bulk

    def get_bulk(self, bulk_id: str) -> Optional[BulkAudit]:
        with self._lock:
            return self._bulks.get(bulk_id)

    def list_bulks(self, limit: int = 20) -> list[BulkAudit]:
        with self._lock:
            items = sorted(
                self._bulks.values(), key=lambda b: b.createdAt, reverse=True,
            )
            return items[:limit]

    def delete_bulk(self, bulk_id: str) -> bool:
        with self._lock:
            return self._bulks.pop(bulk_id, None) is not None

    # ------------------------------------------------------------------
    # Sitemap watches

    def save_sitemap(self, watch: SitemapWatch) -> None:
        with self._lock:
            self._sitemaps[watch.id] = watch

    def get_sitemap(self, watch_id: str) -> Optional[SitemapWatch]:
        with self._lock:
            return self._sitemaps.get(watch_id)

    def list_sitemaps(self, limit: int = 50) -> list[SitemapWatch]:
        with self._lock:
            items = sorted(
                self._sitemaps.values(), key=lambda w: w.updatedAt, reverse=True,
            )
            return items[:limit]

    def delete_sitemap(self, watch_id: str) -> bool:
        with self._lock:
            return self._sitemaps.pop(watch_id, None) is not None

    # ------------------------------------------------------------------
    # Performance monitors

    def save_perf(self, perf: PerfMonitor) -> None:
        with self._lock:
            self._perfs[perf.id] = perf

    def get_perf(self, perf_id: str) -> Optional[PerfMonitor]:
        with self._lock:
            return self._perfs.get(perf_id)

    def list_perfs(self, limit: int = 50) -> list[PerfMonitor]:
        with self._lock:
            items = sorted(
                self._perfs.values(), key=lambda p: p.updatedAt, reverse=True,
            )
            return items[:limit]

    def delete_perf(self, perf_id: str) -> bool:
        with self._lock:
            return self._perfs.pop(perf_id, None) is not None

    # ------------------------------------------------------------------
    # SEO campaigns

    def save_seo(self, campaign: SeoCampaign) -> None:
        with self._lock:
            self._seo[campaign.id] = campaign

    def get_seo(self, campaign_id: str) -> Optional[SeoCampaign]:
        with self._lock:
            return self._seo.get(campaign_id)

    def list_seo(self, limit: int = 50) -> list[SeoCampaign]:
        with self._lock:
            items = sorted(
                self._seo.values(), key=lambda c: c.updatedAt, reverse=True,
            )
            return items[:limit]

    def delete_seo(self, campaign_id: str) -> bool:
        with self._lock:
            return self._seo.pop(campaign_id, None) is not None


def _parse_iso(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)


# ---------------------------------------------------------------------------
# Factory


_store: Optional[object] = None


def get_store():
    """Return the active store. Picks SQL when a DATABASE_URL is set, else
    falls back to in-memory. Cached per process."""
    global _store
    if _store is not None:
        return _store

    from api.config import get_settings
    url = (get_settings().database_url or "").strip()
    if not url:
        _store = InMemoryAuditStore()
        return _store

    try:
        from api.services.store_sql import SqlAuditStore
        _store = SqlAuditStore()
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception(
            "SQL store failed to initialise — falling back to in-memory: %s", e
        )
        _store = InMemoryAuditStore()
    return _store


# Typing helper for callers that want to keep annotations tight.
AuditStore = InMemoryAuditStore  # structural-compatible alias
