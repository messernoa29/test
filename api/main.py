"""FastAPI entrypoint for the Audit Web IA backend."""

from __future__ import annotations

import logging
import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_settings
from api.routes import (
    ai_visibility as ai_visibility_routes,
    audit,
    bulk as bulk_routes,
    competitor,
    content_brief as content_brief_routes,
    llms_txt as llms_txt_routes,
    perf_monitor as perf_monitor_routes,
    prospect as prospect_routes,
    scheduler as scheduler_routes,
    seo_tracker as seo_tracker_routes,
    settings as settings_routes,
    sitemap_watcher as sitemap_routes,
)
from api.services import scheduler as scheduler_service
from api.services.auth import require_auth
from api.services.runner import shutdown_executor
from api.services.store import get_store

logger = logging.getLogger(__name__)

app = FastAPI(title="Audit Web IA API", version="0.1.0")

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=settings.allowed_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_auth = [Depends(require_auth)]

app.include_router(audit.router, prefix="/audit", tags=["audit"], dependencies=_auth)
app.include_router(competitor.router, prefix="/competitor", tags=["competitor"], dependencies=_auth)
app.include_router(
    content_brief_routes.router, prefix="/content-brief", tags=["content-brief"], dependencies=_auth,
)
app.include_router(
    ai_visibility_routes.router, prefix="/ai-visibility", tags=["ai-visibility"], dependencies=_auth,
)
app.include_router(
    prospect_routes.router, prefix="/prospect", tags=["prospect"], dependencies=_auth,
)
app.include_router(settings_routes.router, prefix="/settings", tags=["settings"], dependencies=_auth)
app.include_router(llms_txt_routes.router, prefix="/llms-txt", tags=["llms-txt"], dependencies=_auth)
app.include_router(bulk_routes.router, prefix="/bulk", tags=["bulk"], dependencies=_auth)
app.include_router(sitemap_routes.router, prefix="/sitemap-watcher", tags=["sitemap-watcher"], dependencies=_auth)
app.include_router(perf_monitor_routes.router, prefix="/perf-monitor", tags=["perf-monitor"], dependencies=_auth)
app.include_router(seo_tracker_routes.router, prefix="/seo-tracker", tags=["seo-tracker"], dependencies=_auth)
app.include_router(scheduler_routes.router, prefix="/scheduler", tags=["scheduler"], dependencies=_auth)


@app.on_event("startup")
def _init_db() -> None:
    """Initialize the database schema (idempotent)."""
    # Touching get_store() kicks in SQL backend init + Base.metadata.create_all
    get_store()


@app.on_event("startup")
def _seed_fixture_if_requested() -> None:
    if os.getenv("SEED_FIXTURE", "").lower() not in ("1", "true", "yes"):
        return
    from api.fixtures import build_demo_audit, build_demo_crawl

    audit_result = build_demo_audit()
    store = get_store()
    # Idempotent: only seed when the row is missing so user-added data keeps
    # its place across restarts.
    if store.get(audit_result.id) is not None:
        logger.info("Seed skipped: demo audit %s already present", audit_result.id)
        return
    crawl = build_demo_crawl(audit_result)
    store.save(audit_result, crawl)
    logger.info("Seeded demo audit id=%s", audit_result.id)


@app.on_event("startup")
def _fail_stale_jobs_on_boot() -> None:
    """A restart kills any in-flight audit's worker thread but leaves the row
    in 'pending'/'running' forever (the in-memory sweeper restarts with an
    empty state). At boot, fail every job that's been running longer than the
    hard timeout so it doesn't show as 'in progress' for 42h."""
    from datetime import datetime, timezone, timedelta
    store = get_store()
    stale_min = int(os.getenv("STALE_JOB_MIN", "25"))
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_min)
    try:
        for job in store.list_recent(limit=200, include_archived=True):
            if job.status not in ("pending", "running"):
                continue
            try:
                created = datetime.fromisoformat(job.created_at.replace("Z", "+00:00"))
            except Exception:
                continue
            if created < cutoff:
                logger.warning("Boot: failing stale audit %s (started %s)", job.id, job.created_at)
                store.fail_job(job.id, f"Audit interrompu (redémarrage du serveur après {stale_min} min).")
    except Exception as e:
        logger.warning("Boot stale-audit sweep failed: %s", e)
    try:
        for sheet in store.list_prospects(limit=200):
            if sheet.status not in ("pending", "running"):
                continue
            try:
                created = datetime.fromisoformat(sheet.createdAt.replace("Z", "+00:00"))
            except Exception:
                continue
            if created < cutoff:
                logger.warning("Boot: failing stale prospect %s (started %s)", sheet.id, sheet.createdAt)
                store.save_prospect(sheet.model_copy(update={
                    "status": "failed",
                    "error": f"Fiche interrompue (redémarrage du serveur après {stale_min} min).",
                }))
    except Exception as e:
        logger.warning("Boot stale-prospect sweep failed: %s", e)


@app.on_event("startup")
def _start_scheduler() -> None:
    """Start the in-process cron scheduler when SCHEDULER_ENABLED=1."""
    scheduler_service.start()


@app.on_event("shutdown")
def _shutdown_pool() -> None:
    """Release background workers + scheduler when the server stops."""
    scheduler_service.shutdown(wait=False)
    shutdown_executor(wait=False)


@app.get("/auth/status")
def auth_status() -> dict[str, bool]:
    """Tell the frontend whether a password is required at all."""
    return {"required": settings.auth_password is not None}


@app.get("/auth/verify", dependencies=_auth)
def auth_verify() -> dict[str, str]:
    """200 if creds OK, 401 otherwise. Used by the login screen / token checks."""
    return {"status": "ok"}


@app.post("/auth/token")
def auth_token(body: dict | None = None) -> dict[str, object]:
    """Exchange the shared password for an opaque session token.

    Body: {"password": "..."}. On success returns {"token", "expiresIn"} so
    the client can store the token instead of the raw password.
    """
    from fastapi import HTTPException, status as _status
    from api.services import auth as _auth_svc, session_tokens

    pw = ""
    if isinstance(body, dict):
        pw = str(body.get("password") or "")
    # When auth is disabled (dev), still hand out a token so the client flow
    # is uniform.
    if not _auth_svc.verify_password(pw):
        raise HTTPException(
            status_code=_status.HTTP_401_UNAUTHORIZED, detail="Mot de passe incorrect."
        )
    token, ttl = session_tokens.issue()
    return {"token": token, "expiresIn": ttl}


@app.post("/auth/logout")
def auth_logout(body: dict | None = None) -> dict[str, str]:
    """Revoke a session token. Body: {"token": "..."}."""
    from api.services import session_tokens

    if isinstance(body, dict):
        tok = str(body.get("token") or "")
        if tok:
            session_tokens.revoke(tok)
    return {"status": "ok"}


@app.get("/health")
def health() -> dict[str, object]:
    active_model = (
        settings.anthropic_model
        if settings.llm_provider == "anthropic"
        else settings.gemini_model
    )
    from api.services.store import is_persistent

    return {
        "status": "ok",
        "provider": settings.llm_provider,
        "model": active_model,
        "persistentStorage": is_persistent(),
    }
