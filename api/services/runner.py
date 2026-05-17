"""Background runner for the crawl + analyse pipeline.

A worker thread executes the pipeline and updates the store. The store is
the source of truth; every code path (including unexpected exceptions)
guarantees the job ends in either `done` or `failed` state — never stuck
in `pending`.
"""

from __future__ import annotations

import logging
import os
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
    ProspectSheet,
)
from api.services import (
    ai_visibility,
    analyzer,
    brief as brief_service,
    crawler,
    pagespeed,
    prospect as prospect_service,
)
from api.services.store import get_store

logger = logging.getLogger(__name__)

import threading as _threading
import time as _time

_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = Lock()

# Hard ceiling on a single audit. Past this, the in-pipeline guard (checked
# between stages) aborts; a background sweeper also catches jobs whose worker
# died entirely. Generous because Gemini free-tier rate limits add minutes.
AUDIT_HARD_TIMEOUT_S = int(os.getenv("AUDIT_HARD_TIMEOUT_S", str(20 * 60)))

# Tracks when each running audit started (monotonic), so the sweeper can fail
# the ones that have been pending too long without a per-audit thread.
_audit_started_at: dict[str, float] = {}
_audit_started_lock = Lock()
_sweeper_thread: Optional[_threading.Thread] = None


class AuditTimeout(Exception):
    """Raised inside _run when the audit exceeds AUDIT_HARD_TIMEOUT_S."""


def _get_executor() -> ThreadPoolExecutor:
    global _executor, _sweeper_thread
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="audit")
        if _sweeper_thread is None or not _sweeper_thread.is_alive():
            _sweeper_thread = _threading.Thread(
                target=_sweep_stale_audits, name="audit-sweeper", daemon=True,
            )
            _sweeper_thread.start()
        return _executor


def _sweep_stale_audits() -> None:
    """Daemon: every 60s, fail any audit that's been running past the hard
    timeout (covers the case where its worker thread died outright). One
    thread for the whole process — no per-audit thread."""
    while True:
        _time.sleep(60)
        try:
            now = _time.monotonic()
            stale: list[str] = []
            with _audit_started_lock:
                for jid, started in list(_audit_started_at.items()):
                    if now - started > AUDIT_HARD_TIMEOUT_S + 30:
                        stale.append(jid)
            if not stale:
                continue
            store = get_store()
            from api.services import progress
            for jid in stale:
                try:
                    job = store.get(jid)
                    if job is not None and job.status == "pending":
                        logger.warning("Sweeper: audit %s stale — marking failed", jid)
                        progress.add(jid, "Audit interrompu (délai dépassé, worker perdu)")
                        store.fail_job(
                            jid,
                            f"L'audit a dépassé le délai de {AUDIT_HARD_TIMEOUT_S // 60} min "
                            "et a été interrompu.",
                        )
                finally:
                    with _audit_started_lock:
                        _audit_started_at.pop(jid, None)
        except Exception as e:
            logger.warning("Sweeper error: %s", e)


def submit_audit(
    job_id: str, url: str, max_pages: int = 50, platform: str = "unknown"
) -> None:
    """Queue a pipeline run on the shared pool."""
    with _audit_started_lock:
        _audit_started_at[job_id] = _time.monotonic()
    _get_executor().submit(_run, job_id, url, max_pages, platform)


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


def _run(job_id: str, url: str, max_pages: int = 50, platform: str = "unknown") -> None:
    store = get_store()
    from api.services import progress
    started = _time.monotonic()

    def _check_deadline(stage: str) -> None:
        if _time.monotonic() - started > AUDIT_HARD_TIMEOUT_S:
            raise AuditTimeout(f"Délai dépassé avant l'étape « {stage} »")

    progress.add(job_id, f"Audit lancé sur {url} (max {max_pages} pages)")
    # try/finally guarantees we never leave a job in `pending` silently if
    # the thread dies from something unexpected (OSError, MemoryError, ...).
    success = False
    try:
        progress.add(job_id, f"Crawl du site en cours (jusqu'à {max_pages} pages)…")
        crawl_data = crawler.crawl(url, max_pages=max_pages)
        if not crawl_data.pages:
            progress.add(job_id, "Aucune page récupérée — échec.")
            store.fail_job(
                job_id, "Le site n'a pas répondu ou aucune page n'a été trouvée."
            )
            return
        n_crawled = len(crawl_data.pages)
        n_discovered = crawl_data.discoveredUrlCount or n_crawled
        if n_discovered > n_crawled:
            progress.add(
                job_id,
                f"Crawl terminé : {n_crawled} pages analysées sur {n_discovered} "
                f"URLs trouvées (limite : {max_pages})",
            )
        else:
            progress.add(
                job_id,
                f"Crawl terminé : {n_crawled} pages analysées "
                f"(le site n'en a pas plus ; vous aviez demandé jusqu'à {max_pages})"
                if n_crawled < max_pages
                else f"Crawl terminé : {n_crawled} pages analysées",
            )
        _check_deadline("PageSpeed")

        # Enrich with real Core Web Vitals before analysis. Falls back to
        # "unavailable" snapshot if the API key is absent or the call fails.
        # Strategy: PSI on the home + the top 2 hub pages (most internally
        # linked) so the analyzer gets variety, not just the landing page.
        psi_targets = [crawl_data.url]
        if crawl_data.linkGraph and crawl_data.linkGraph.hubPages:
            for hub in crawl_data.linkGraph.hubPages[:2]:
                if hub != crawl_data.url and hub not in psi_targets:
                    psi_targets.append(hub)
        progress.add(job_id, f"PageSpeed Insights sur {len(psi_targets)} page(s)…")
        perf_snapshots = []
        for target in psi_targets:
            snap = pagespeed.fetch_performance(target, strategy="mobile")
            perf_snapshots.append(snap)
            logger.info(
                "PSI for %s: source=%s score=%s metrics=%d",
                target, snap.source, snap.performanceScore, len(snap.metrics),
            )
        progress.add(
            job_id,
            f"PageSpeed : {perf_snapshots[0].source}"
            + (f", score {perf_snapshots[0].performanceScore}/100" if perf_snapshots[0].performanceScore is not None else ""),
        )
        # Keep the home snapshot in CrawlData.performance for backward compat;
        # extras are merged into the analyzer prompt via the formatter.
        crawl_data = crawl_data.model_copy(
            update={
                "performance": perf_snapshots[0],
                "performanceExtra": perf_snapshots[1:],
            }
        )

        _check_deadline("analyse IA")
        progress.add(job_id, "Analyse IA des 6 axes (Gemini)…")
        deadline_at = started + AUDIT_HARD_TIMEOUT_S
        audit = analyzer.analyze(
            crawl_data,
            on_progress=lambda m: progress.add(job_id, m),
            deadline_monotonic=deadline_at,
            platform=platform,
        )
        progress.add(job_id, "Analyse IA terminée — assemblage du rapport")
        enriched_pages = _merge_page_technical(audit.pages, crawl_data)
        cultural = _build_cultural_audit(crawl_data)
        geo = _build_geo_audit(crawl_data)
        # GEO citation test (LLM + web_search) — best-effort, only if we still
        # have a comfortable margin before the hard timeout.
        if _time.monotonic() - started < AUDIT_HARD_TIMEOUT_S - 150:
            progress.add(job_id, "Test de citabilité par les IA…")
            try:
                pages_for_geo = [p.model_dump() if hasattr(p, "model_dump") else p for p in (enriched_pages or [])]
                gc = _time_boxed_call(
                    lambda: analyzer._run_geo_citation(crawl_data, pages_for_geo), 120
                )
                if gc:
                    geo = geo.model_copy(update={
                        "queryVerdicts": gc.get("queryVerdicts", []),
                        "citedCount": gc.get("citedCount", 0),
                        "queriesTested": gc.get("queriesTested", 0),
                    })
                    progress.add(
                        job_id,
                        f"Citabilité IA : site probablement cité sur {gc.get('citedCount',0)}/{gc.get('queriesTested',0)} requêtes testées",
                    )
                else:
                    progress.add(job_id, "Test de citabilité IA ignoré (délai/erreur)")
            except Exception as e:
                logger.warning("GEO citation failed: %s", e)
        programmatic = _build_programmatic_audit(crawl_data)
        coverage = _build_crawl_coverage(crawl_data, detailed_count=len(enriched_pages or []))
        # Accessibility — static aggregates + optional LLM verdict on a sample.
        progress.add(job_id, "Analyse de l'accessibilité (WCAG)…")
        a11y_audit = _build_accessibility_audit(crawl_data, started)
        # Responsive — static signals + Playwright at 3 widths on a sample.
        progress.add(job_id, "Test responsive (rendu mobile/tablette/desktop)…")
        responsive_audit = _build_responsive_audit(crawl_data, started)
        # Deterministic facts snapshot — what the drift view actually diffs.
        try:
            from api.services import scoring as _scoring
            facts = _scoring.build_facts_snapshot(
                crawl_data, axis_scores=dict(audit.scores), global_score=audit.globalScore
            )
        except Exception as e:
            logger.warning("Facts snapshot failed: %s", e)
            facts = {}
        audit = audit.model_copy(
            update={
                "id": job_id,
                "technicalCrawl": crawl_data.technicalCrawl,
                "pages": enriched_pages,
                "culturalAudit": cultural,
                "geoAudit": geo,
                "programmaticAudit": programmatic,
                "crawlCoverage": coverage,
                "accessibilityAudit": a11y_audit,
                "responsiveAudit": responsive_audit,
                "factsSnapshot": facts,
            }
        )
        if audit.domain:
            store.update_domain(job_id, audit.domain)
        store.complete_job(job_id, audit, crawl_data)
        progress.add(job_id, "Rapport prêt ✓")
        success = True
    except AuditTimeout as e:
        logger.warning("Audit %s timed out: %s", job_id, e)
        progress.add(job_id, f"Délai dépassé ({AUDIT_HARD_TIMEOUT_S // 60} min) — audit abandonné")
        store.fail_job(
            job_id,
            f"L'audit a dépassé le délai maximum de {AUDIT_HARD_TIMEOUT_S // 60} minutes. "
            "Réessayez avec moins de pages, ou vérifiez les quotas de l'API Gemini.",
        )
    except Exception as e:
        logger.exception("Pipeline failed for job %s: %s", job_id, e)
        progress.add(job_id, f"Échec : {e}")
        store.fail_job(job_id, str(e) or e.__class__.__name__)
    finally:
        with _audit_started_lock:
            _audit_started_at.pop(job_id, None)
        if not success:
            try:
                job = store.get(job_id)
                if job is not None and job.status == "pending":
                    # Safety net: thread died before any status write.
                    store.fail_job(
                        job_id,
                        "Erreur inattendue lors de l'audit (thread interrompu).",
                    )
            except Exception as e:
                logger.warning("Final safety-net check failed for %s: %s", job_id, e)


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
# Prospect sheets


def submit_prospect(sheet_id: str) -> None:
    _get_executor().submit(_run_prospect, sheet_id)


def _run_prospect(sheet_id: str) -> None:
    store = get_store()
    sheet = store.get_prospect(sheet_id)
    if sheet is None:
        return
    store.save_prospect(sheet.model_copy(update={"status": "running"}))
    try:
        result = prospect_service.run_pipeline(sheet)
        store.save_prospect(result)
    except Exception as e:
        logger.exception("Prospect pipeline failed for %s: %s", sheet_id, e)
        store.save_prospect(
            sheet.model_copy(
                update={"status": "failed", "error": str(e) or e.__class__.__name__}
            )
        )


def create_prospect_job(url: str) -> ProspectSheet:
    sheet = prospect_service.create_sheet(url=url)
    get_store().save_prospect(sheet)
    submit_prospect(sheet.id)
    return sheet


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


# ---------------------------------------------------------------------------
# Per-page technical enrichment
#
# The LLM produces PageAnalysis entries from the compact crawl payload but
# doesn't carry the full crawl facts (status code, depth, OG tags, ratios…).
# We merge those in from CrawlData here, matching by normalized URL, and also
# attach the per-URL issue list computed by the technical crawl.


def _merge_page_technical(pages, crawl_data):
    """Return a new list of PageAnalysis with .technical populated, or the
    original list if there's nothing to merge."""
    if not pages:
        return pages
    from api.models import PageTechnical
    from api.services.crawler import _normalize  # local import to avoid cycle
    from api.services import page_classifier, schema_generator

    crawl_by_url = {_normalize(p.url): p for p in (crawl_data.pages or [])}
    tc_rows_by_url = {}
    if crawl_data.technicalCrawl:
        tc_rows_by_url = {
            _normalize(r.url): r for r in crawl_data.technicalCrawl.rows
        }
    home_norm = _normalize(crawl_data.url)
    domain = crawl_data.domain

    out = []
    for pa in pages:
        norm = _normalize(pa.url)
        cp = crawl_by_url.get(norm)
        row = tc_rows_by_url.get(norm)
        if cp is None and row is None:
            out.append(pa)
            continue
        canonical = cp.canonical if cp else None
        canonical_is_self = None
        if cp and canonical:
            canonical_is_self = canonical in (norm, _normalize(cp.finalUrl or ""))
        og = cp.openGraph if (cp and cp.openGraph) else None
        schema_types = sorted({s.type for s in cp.schemas}) if cp and cp.schemas else []
        headings = cp.headings if cp else []
        text_snippet = cp.textSnippet if cp else ""
        word_count = cp.wordCount if cp else (row.wordCount if row else 0)

        page_type = page_classifier.classify_page(
            url=pa.url,
            title=pa.title or (cp.title if cp else ""),
            h1=pa.h1 or (cp.h1 if cp else ""),
            headings=headings,
            text_snippet=text_snippet,
            schemas=schema_types,
            word_count=word_count,
            is_homepage=(norm == home_norm),
        )

        question_headings = [h for h in headings if "?" in h]
        image_urls = [img.src for img in (cp.images if cp else []) if img.src]
        suggested_json, suggested_type = schema_generator.suggest_schema(
            url=pa.url,
            page_type=page_type,
            existing_types=schema_types,
            title=pa.title or (cp.title if cp else ""),
            h1=pa.h1 or (cp.h1 if cp else ""),
            meta_description=pa.metaDescription if pa.metaDescription is not None else (cp.metaDescription if cp else None),
            image_urls=image_urls,
            domain=domain,
            headings_questions=question_headings,
        )

        tech = PageTechnical(
            statusCode=(cp.statusCode if cp else (row.statusCode if row else None)),
            depth=(row.depth if row else None),
            htmlBytes=(cp.htmlBytes if cp else (row.htmlBytes if row else 0)),
            wordCount=word_count,
            textRatio=(row.textRatio if row else 0.0),
            canonical=canonical,
            canonicalIsSelf=canonical_is_self,
            robotsMeta=(cp.robotsMeta if cp else ""),
            htmlLang=(cp.htmlLang if cp else ""),
            hreflangLangs=sorted({h.lang for h in cp.hreflang}) if cp and cp.hreflang else [],
            internalLinksOut=(cp.internalLinksCount if cp else (row.internalLinksOut if row else 0)),
            externalLinksOut=(cp.externalLinksCount if cp else (row.externalLinksOut if row else 0)),
            imagesCount=(len(cp.images) if cp else (row.imagesCount if row else 0)),
            imagesWithoutAlt=(cp.imagesWithoutAlt if cp else (row.imagesWithoutAlt if row else 0)),
            hasViewportMeta=(og.hasViewportMeta if og else True),
            hasMixedContent=(cp.hasMixedContent if cp else False),
            ogTitle=(og.ogTitle if og else None),
            ogDescription=(og.ogDescription if og else None),
            ogImage=(og.ogImage if og else None),
            twitterCard=(og.twitterCard if og else None),
            redirectChain=(cp.redirectChain if cp else []),
            schemaTypes=schema_types,
            issues=(row.issues if row else []),
            pageType=page_type,
            suggestedSchema=suggested_json,
            suggestedSchemaType=suggested_type,
        )
        out.append(pa.model_copy(update={"technical": tech}))
    return out


# ---------------------------------------------------------------------------
# Cultural adaptation audit (multilingual sites)


def _build_cultural_audit(crawl_data):
    """Detect multilingual sites and run a per-locale cultural-mismatch check.
    Returns CulturalAuditSummary (isMultilingual False when monolingual)."""
    from api.models import (
        CulturalAuditSummary,
        CulturalLocaleReport,
        CulturalPageIssue,
    )
    from api.services import cultural_audit

    pages = crawl_data.pages or []
    if not pages:
        return CulturalAuditSummary()

    # Map each page to a detected locale.
    by_locale: dict[str, list] = {}
    for p in pages:
        hreflang_self = ""
        # If the page declares an alternate to itself, treat that lang as self.
        for h in (p.hreflang or []):
            try:
                if h.href.rstrip("/") == p.url.rstrip("/"):
                    hreflang_self = h.lang
                    break
            except Exception:
                pass
        loc = cultural_audit.detect_page_locale(
            html_lang=p.htmlLang or "",
            hreflang_self=hreflang_self,
            url=p.url,
        )
        if loc:
            by_locale.setdefault(loc, []).append(p)

    # Also collect locales declared via hreflang anywhere on the site.
    declared = set(by_locale.keys())
    for p in pages:
        for h in (p.hreflang or []):
            n = cultural_audit._norm_lang(h.lang)
            if n in cultural_audit.PROFILES:
                declared.add(n)

    if len(declared) < 2:
        return CulturalAuditSummary(isMultilingual=False, detectedLocales=sorted(declared))

    reports: list[CulturalLocaleReport] = []
    for loc in sorted(by_locale.keys()):
        prof = cultural_audit.PROFILES.get(loc)
        if not prof:
            continue
        plist = by_locale[loc]
        page_issues: list[CulturalPageIssue] = []
        for p in plist:
            issues = cultural_audit.audit_page(
                locale=loc,
                body_text=p.textSnippet or "",
                cta_texts=p.ctaTexts or [],
            )
            if issues:
                page_issues.append(
                    CulturalPageIssue(url=p.url, locale=loc, issues=issues)
                )
        reports.append(CulturalLocaleReport(
            locale=loc,
            label=prof["label"],
            pagesCount=len(plist),
            pagesWithIssues=len(page_issues),
            expectedNumberFormat=prof["numberFormat"],
            expectedDateFormat=prof["dateFormat"],
            issueExamples=page_issues[:15],
        ))

    return CulturalAuditSummary(
        isMultilingual=True,
        detectedLocales=sorted(declared),
        locales=reports,
    )


# ---------------------------------------------------------------------------
# GEO (AI-citability) audit


def _build_geo_audit(crawl_data):
    """Per-page citability scoring + site-level robots/llms.txt assessment."""
    from api.models import GeoAuditSummary, GeoPageScore
    from api.services import geo_audit

    pages = crawl_data.pages or []
    page_scores: list[GeoPageScore] = []
    for p in pages:
        schema_types = [s.type for s in p.schemas] if p.schemas else []
        score, strengths, weaknesses = geo_audit.score_page(
            word_count=p.wordCount,
            headings=p.headings,
            text_snippet=p.textSnippet,
            schemas=schema_types,
            rendered_with_playwright=bool(p.renderedWithPlaywright),
        )
        page_scores.append(GeoPageScore(
            url=p.url, score=score, strengths=strengths, weaknesses=weaknesses,
        ))

    avg = round(sum(s.score for s in page_scores) / len(page_scores)) if page_scores else 0

    site_str, site_weak, ai_status = geo_audit.score_site_layer(
        robots_txt=crawl_data.robotsTxt or "",
        has_llms_txt=bool(crawl_data.hasLlmsTxt),
    )

    return GeoAuditSummary(
        averagePageScore=avg,
        pageScores=sorted(page_scores, key=lambda s: s.score)[:50],  # worst first, cap
        siteStrengths=site_str,
        siteWeaknesses=site_weak,
        aiCrawlerStatus=ai_status,
        hasLlmsTxt=bool(crawl_data.hasLlmsTxt),
    )


# ---------------------------------------------------------------------------
# Programmatic-SEO quality gates


def _build_programmatic_audit(crawl_data):
    from api.models import ProgrammaticAuditSummary, ProgrammaticGroup
    from api.services import programmatic_audit

    result = programmatic_audit.analyze_pages(crawl_data.pages or [])
    groups = [ProgrammaticGroup(**g) for g in result.get("groups", [])]
    return ProgrammaticAuditSummary(
        isProgrammatic=result.get("isProgrammatic", False),
        groups=groups,
    )


# ---------------------------------------------------------------------------
# Crawl coverage summary


def _build_crawl_coverage(crawl_data, *, detailed_count: int = 0):
    from api.models import CrawlCoverage

    requested = crawl_data.requestedMaxPages or 0
    discovered = crawl_data.discoveredUrlCount or len(crawl_data.pages or [])
    crawled = crawl_data.crawledPageCount or len(crawl_data.pages or [])
    capped_by_limit = requested > 0 and discovered > requested
    capped_by_site = requested > 0 and discovered <= requested
    return CrawlCoverage(
        requestedMaxPages=requested,
        discoveredUrlCount=discovered,
        crawledPageCount=crawled,
        detailedPageCount=detailed_count or crawled,
        cappedByLimit=capped_by_limit,
        cappedBySite=capped_by_site,
    )


def _time_boxed_call(fn, timeout_s: float):
    """Run fn in a worker thread; return its result or None on timeout/error."""
    from concurrent.futures import ThreadPoolExecutor as _TPE
    from concurrent.futures import TimeoutError as _FT
    try:
        with _TPE(max_workers=1) as ex:
            return ex.submit(fn).result(timeout=timeout_s)
    except _FT:
        logger.warning("_time_boxed_call timed out after %ss", timeout_s)
        return None
    except Exception as e:
        logger.warning("_time_boxed_call failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Accessibility audit


def _build_accessibility_audit(crawl_data, started):
    from api.models import AccessibilityAudit, A11yPageIssue
    from api.services import a11y_static as a11y

    pages = [p for p in (crawl_data.pages or []) if p.a11y is not None]
    if not pages:
        return AccessibilityAudit()

    page_scores: list[A11yPageIssue] = []
    agg = {
        "pagesWithoutLang": 0, "imagesWithoutAlt": 0, "formInputsWithoutLabel": 0,
        "linksGeneric": 0, "buttonsAsDiv": 0, "pagesWithHeadingIssues": 0,
        "pagesWithPositiveTabindex": 0, "pagesWithoutLandmarks": 0,
    }
    total_score = 0
    for p in pages:
        a = p.a11y.model_dump() if hasattr(p.a11y, "model_dump") else dict(p.a11y)
        s = a11y.a11y_score(a)
        total_score += s
        page_scores.append(A11yPageIssue(url=p.url, score=s, issues=list(a.get("issues", []))))
        if not a.get("htmlHasLang"):
            agg["pagesWithoutLang"] += 1
        agg["imagesWithoutAlt"] += a.get("imagesWithoutAlt", 0)
        agg["formInputsWithoutLabel"] += a.get("formInputsWithoutLabel", 0)
        agg["linksGeneric"] += a.get("linksGeneric", 0)
        agg["buttonsAsDiv"] += a.get("buttonsAsDiv", 0)
        if a.get("headingOrderIssues") or a.get("h1Count", 0) != 1:
            agg["pagesWithHeadingIssues"] += 1
        if a.get("positiveTabindex"):
            agg["pagesWithPositiveTabindex"] += 1
        if not a.get("landmarksPresent"):
            agg["pagesWithoutLandmarks"] += 1

    avg = round(total_score / len(pages))
    page_scores.sort(key=lambda x: x.score)

    result = AccessibilityAudit(
        averageScore=avg,
        pageScores=page_scores[:30],
        **agg,
    )

    # Optional LLM verdict on the 3 worst pages (best-effort, time-boxed).
    if _time.monotonic() - started < AUDIT_HARD_TIMEOUT_S - 150:
        try:
            worst = page_scores[:3]
            sample = []
            for ps in worst:
                cp = next((p for p in pages if p.url == ps.url), None)
                if cp is None:
                    continue
                a = cp.a11y.model_dump() if hasattr(cp.a11y, "model_dump") else dict(cp.a11y)
                sample.append({"url": cp.url, "score": ps.score, "signals": a})
            if sample:
                gc = _time_boxed_call(lambda: analyzer.run_a11y_verdict(crawl_data.domain, sample), 90)
                if gc:
                    result = result.model_copy(update={
                        "llmVerdict": gc.get("verdict", ""),
                        "llmTopFixes": gc.get("topFixes", []),
                        "llmPagesEvaluated": len(sample),
                    })
        except Exception as e:
            logger.warning("a11y LLM verdict failed: %s", e)
    return result


# ---------------------------------------------------------------------------
# Responsive audit


def _build_responsive_audit(crawl_data, started):
    from api.models import ResponsiveAudit, ResponsivePageIssue
    from api.services import playwright_fetcher

    pages = [p for p in (crawl_data.pages or []) if p.responsive is not None]
    if not pages:
        return ResponsiveAudit()

    n_no_viewport = sum(1 for p in pages if not p.responsive.hasViewportMeta)
    n_block_zoom = sum(1 for p in pages if p.responsive.viewportBlocksZoom)
    n_media = sum(1 for p in pages if p.responsive.cssMediaQueries > 0)
    total_imgs = sum(p.responsive.imagesTotal for p in pages)
    srcset_imgs = sum(p.responsive.imagesWithSrcset for p in pages)
    srcset_ratio = round(srcset_imgs / total_imgs, 3) if total_imgs else 0.0

    page_results: list[ResponsivePageIssue] = []
    rendered = 0
    n_hscroll = 0
    # Pick a sample to actually render: home + a few others.
    home = crawl_data.url
    sample = ([p for p in pages if p.url == home] + [p for p in pages if p.url != home])[:5]
    can_render = playwright_fetcher.is_enabled() and _time.monotonic() - started < AUDIT_HARD_TIMEOUT_S - 120
    for p in sample:
        rd = p.responsive.model_dump() if hasattr(p.responsive, "model_dump") else dict(p.responsive)
        issues = list(rd.get("issues", []))
        hs375 = hs768 = None
        overflow375 = small_targets = None
        if can_render:
            try:
                m = _time_boxed_call(lambda url=p.url: playwright_fetcher.measure_responsive(url), 35)
                if m:
                    rendered += 1
                    hs375 = m.get("horizontalScrollAt375")
                    hs768 = m.get("horizontalScrollAt768")
                    overflow375 = m.get("overflowingElementsAt375")
                    small_targets = m.get("smallTouchTargetsAt375")
                    if hs375:
                        issues.append("scroll horizontal à 375px (mobile) — un élément déborde")
                        n_hscroll += 1
                    elif hs768:
                        issues.append("scroll horizontal à 768px (tablette)")
                        n_hscroll += 1
                    if small_targets:
                        issues.append(f"{small_targets} cible(s) tactile(s) < 44×44px à 375px")
            except Exception as e:
                logger.debug("responsive render failed on %s: %s", p.url, e)
        page_results.append(ResponsivePageIssue(
            url=p.url,
            horizontalScrollAt375=hs375,
            horizontalScrollAt768=hs768,
            overflowingElementsAt375=overflow375,
            smallTouchTargetsAt375=small_targets,
            issues=issues,
        ))

    parts = []
    if n_no_viewport:
        parts.append(f"{n_no_viewport} page(s) sans <meta viewport>")
    if n_block_zoom:
        parts.append(f"{n_block_zoom} page(s) bloquent le zoom")
    if not can_render:
        parts.append("rendu navigateur non effectué (Playwright désactivé) — signaux statiques uniquement")
    elif n_hscroll:
        parts.append(f"{n_hscroll} page(s) avec scroll horizontal au rendu mobile")
    summary = " · ".join(parts) if parts else "Aucun problème responsive majeur détecté."

    return ResponsiveAudit(
        pagesWithoutViewport=n_no_viewport,
        pagesBlockingZoom=n_block_zoom,
        pagesWithMediaQueries=n_media,
        imagesWithSrcsetRatio=srcset_ratio,
        renderedPagesTested=rendered,
        pagesWithHorizontalScroll=n_hscroll,
        pageResults=page_results,
        summary=summary,
    )
