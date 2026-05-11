"""Background runner for the crawl + analyse pipeline.

A worker thread executes the pipeline and updates the store. The store is
the source of truth; every code path (including unexpected exceptions)
guarantees the job ends in either `done` or `failed` state — never stuck
in `pending`.
"""

from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
from typing import Optional
from urllib.parse import urlparse

from api.models import (
    AiVisibilityCheck,
    CompetitorBattle,
    CompetitorSite,
    ContentBrief,
)
from api.services import (
    ai_visibility,
    analyzer,
    brief as brief_service,
    crawler,
    pagespeed,
)
from api.services.store import get_store

logger = logging.getLogger(__name__)

_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = Lock()


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="audit")
        return _executor


def submit_audit(job_id: str, url: str, max_pages: int = 50) -> None:
    """Queue a pipeline run; updates the store as it progresses."""
    _get_executor().submit(_run, job_id, url, max_pages)


def shutdown_executor(wait: bool = False) -> None:
    """Called on app shutdown to release the background worker pool cleanly."""
    global _executor
    with _executor_lock:
        if _executor is not None:
            try:
                _executor.shutdown(wait=wait, cancel_futures=True)
            except Exception as e:
                logger.warning("Executor shutdown error: %s", e)
            _executor = None


def _run(job_id: str, url: str, max_pages: int = 50) -> None:
    store = get_store()
    # try/finally guarantees we never leave a job in `pending` silently if
    # the thread dies from something unexpected (OSError, MemoryError, ...).
    success = False
    try:
        crawl_data = crawler.crawl(url, max_pages=max_pages)
        if not crawl_data.pages:
            store.fail_job(
                job_id, "Le site n'a pas répondu ou aucune page n'a été trouvée."
            )
            return

        # Enrich with real Core Web Vitals before analysis. Falls back to
        # "unavailable" snapshot if the API key is absent or the call fails.
        # Strategy: PSI on the home + the top 2 hub pages (most internally
        # linked) so the analyzer gets variety, not just the landing page.
        psi_targets = [crawl_data.url]
        if crawl_data.linkGraph and crawl_data.linkGraph.hubPages:
            for hub in crawl_data.linkGraph.hubPages[:2]:
                if hub != crawl_data.url and hub not in psi_targets:
                    psi_targets.append(hub)
        perf_snapshots = []
        for target in psi_targets:
            snap = pagespeed.fetch_performance(target, strategy="mobile")
            perf_snapshots.append(snap)
            logger.info(
                "PSI for %s: source=%s score=%s metrics=%d",
                target, snap.source, snap.performanceScore, len(snap.metrics),
            )
        # Keep the home snapshot in CrawlData.performance for backward compat;
        # extras are merged into the analyzer prompt via the formatter.
        crawl_data = crawl_data.model_copy(
            update={
                "performance": perf_snapshots[0],
                "performanceExtra": perf_snapshots[1:],
            }
        )

        audit = analyzer.analyze(crawl_data)
        audit = audit.model_copy(
            update={"id": job_id, "technicalCrawl": crawl_data.technicalCrawl}
        )
        if audit.domain:
            store.update_domain(job_id, audit.domain)
        store.complete_job(job_id, audit, crawl_data)
        success = True
    except Exception as e:
        logger.exception("Pipeline failed for job %s: %s", job_id, e)
        store.fail_job(job_id, str(e) or e.__class__.__name__)
    finally:
        if not success:
            job = store.get(job_id)
            if job is not None and job.status == "pending":
                # Safety net: thread died before any status write.
                store.fail_job(
                    job_id,
                    "Erreur inattendue lors de l'audit (thread interrompu).",
                )


# ---------------------------------------------------------------------------
# Competitor battles


def submit_competitor_battle(battle_id: str) -> None:
    """Queue the orchestration of a competitor battle.

    The battle row must already exist in the store with status='pending' and
    its `competitors` list holding all URLs (target + competitors).
    """
    _get_executor().submit(_run_battle, battle_id)


def _run_battle(battle_id: str) -> None:
    store = get_store()
    battle = store.get_battle(battle_id)
    if battle is None:
        logger.warning("Battle %s not found at run time", battle_id)
        return

    battle = battle.model_copy(update={"status": "running"})
    store.save_battle(battle)

    audit_ids_by_url: dict[str, str] = {}
    # Kick off every audit in parallel (one per URL). The audit pipeline
    # itself runs on the same executor — the pool is sized large enough
    # (4 workers) to absorb a 1 + N fan-out for small N.
    for site in battle.competitors:
        try:
            audit_id = _launch_single_audit(store, site.url)
            audit_ids_by_url[site.url] = audit_id
        except Exception as e:
            logger.exception("Failed to launch audit for %s: %s", site.url, e)

    # Persist the audit IDs immediately so the UI can link to them while
    # audits are still pending.
    updated_sites: list[CompetitorSite] = []
    for site in battle.competitors:
        updated_sites.append(
            site.model_copy(update={"auditId": audit_ids_by_url.get(site.url)})
        )
    battle = battle.model_copy(update={"competitors": updated_sites})
    store.save_battle(battle)

    # Poll until all audits terminate (done/failed) — with a hard timeout.
    audits = _wait_for_audits(
        list(audit_ids_by_url.values()), timeout_seconds=600,
    )

    # Build the report from the audits that succeeded.
    successful = [a for a in audits if a is not None and a.id in audit_ids_by_url]
    target_audit_id = audit_ids_by_url.get(battle.targetUrl)
    target = next(
        (a for a in successful if a.id == target_audit_id), None,
    )
    if target is None:
        store.save_battle(
            battle.model_copy(
                update={
                    "status": "failed",
                    "error": "L'audit du site cible n'a pas abouti.",
                }
            )
        )
        return

    competitor_audits = [a for a in successful if a.id != target_audit_id]
    try:
        report = analyzer.compare_competitors(target, competitor_audits)
    except Exception as e:
        logger.exception("Competitor synthesis failed for %s: %s", battle_id, e)
        store.save_battle(
            battle.model_copy(
                update={
                    "status": "failed",
                    "error": f"Synthèse comparative échouée : {e}",
                }
            )
        )
        return

    store.save_battle(
        battle.model_copy(update={"status": "done", "report": report})
    )


def _launch_single_audit(store, url: str) -> str:
    """Create an audit row and schedule its pipeline. Returns the audit id."""
    audit_id = uuid.uuid4().hex
    domain = urlparse(url).netloc or url
    store.create_job(audit_id, url, domain)
    _get_executor().submit(_run, audit_id, url)
    return audit_id


def _wait_for_audits(audit_ids: list[str], timeout_seconds: int = 600):
    """Poll the store until every audit reaches a terminal status.

    Returns the list of `AuditResult` objects in the same order as `audit_ids`.
    Failed audits yield `None` at their index.
    """
    import time

    from api.models import AuditResult

    store = get_store()
    deadline = time.time() + timeout_seconds
    pending = set(audit_ids)
    results: dict[str, Optional[AuditResult]] = {aid: None for aid in audit_ids}

    while pending and time.time() < deadline:
        for aid in list(pending):
            job = store.get(aid)
            if job is None:
                pending.discard(aid)
                continue
            if job.status in ("done", "failed"):
                results[aid] = job.result if job.status == "done" else None
                pending.discard(aid)
        if pending:
            time.sleep(2)

    if pending:
        logger.warning(
            "Competitor battle timed out waiting for audits: %s", list(pending)
        )

    return [results[aid] for aid in audit_ids]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_battle(target_url: str, competitor_urls: list[str]) -> CompetitorBattle:
    """Create a fresh battle row and queue its orchestration."""
    battle_id = uuid.uuid4().hex
    sites = [CompetitorSite(url=target_url, label="Cible")] + [
        CompetitorSite(url=str(u), label=None) for u in competitor_urls
    ]
    battle = CompetitorBattle(
        id=battle_id,
        targetUrl=target_url,
        competitors=sites,
        createdAt=now_iso(),
        status="pending",
    )
    get_store().save_battle(battle)
    submit_competitor_battle(battle_id)
    return battle


# ---------------------------------------------------------------------------
# Content briefs


def submit_brief(brief_id: str) -> None:
    _get_executor().submit(_run_brief, brief_id)


def _run_brief(brief_id: str) -> None:
    store = get_store()
    brief = store.get_brief(brief_id)
    if brief is None:
        return
    store.save_brief(brief.model_copy(update={"status": "running"}))
    try:
        result = brief_service.run_brief_pipeline(brief)
        store.save_brief(result)
    except Exception as e:
        logger.exception("Brief pipeline failed for %s: %s", brief_id, e)
        store.save_brief(
            brief.model_copy(
                update={"status": "failed", "error": str(e) or e.__class__.__name__}
            )
        )


def create_brief_job(query: str, locale: str = "fr-FR") -> ContentBrief:
    brief = brief_service.create_brief(query=query, locale=locale)
    get_store().save_brief(brief)
    submit_brief(brief.id)
    return brief


# ---------------------------------------------------------------------------
# AI visibility checks


def submit_ai_check(check_id: str) -> None:
    _get_executor().submit(_run_ai_check, check_id)


def _run_ai_check(check_id: str) -> None:
    store = get_store()
    check = store.get_ai_check(check_id)
    if check is None:
        return
    store.save_ai_check(check.model_copy(update={"status": "running"}))
    try:
        result = ai_visibility.run_check_pipeline(check)
        store.save_ai_check(result)
    except Exception as e:
        logger.exception("AI visibility pipeline failed for %s: %s", check_id, e)
        store.save_ai_check(
            check.model_copy(
                update={"status": "failed", "error": str(e) or e.__class__.__name__}
            )
        )


def create_ai_visibility_job(
    target_domain: str,
    queries: list[str],
    target_name: Optional[str] = None,
) -> AiVisibilityCheck:
    check = ai_visibility.create_check(
        target_domain=target_domain,
        queries=queries,
        target_name=target_name,
    )
    get_store().save_ai_check(check)
    submit_ai_check(check.id)
    return check
