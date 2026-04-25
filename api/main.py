"""FastAPI entrypoint for the Audit Web IA backend."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
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
    scheduler as scheduler_routes,
    seo_tracker as seo_tracker_routes,
    settings as settings_routes,
    sitemap_watcher as sitemap_routes,
)
from api.services import scheduler as scheduler_service
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

app.include_router(audit.router, prefix="/audit", tags=["audit"])
app.include_router(competitor.router, prefix="/competitor", tags=["competitor"])
app.include_router(
    content_brief_routes.router, prefix="/content-brief", tags=["content-brief"],
)
app.include_router(
    ai_visibility_routes.router, prefix="/ai-visibility", tags=["ai-visibility"],
)
app.include_router(settings_routes.router, prefix="/settings", tags=["settings"])
app.include_router(llms_txt_routes.router, prefix="/llms-txt", tags=["llms-txt"])
app.include_router(bulk_routes.router, prefix="/bulk", tags=["bulk"])
app.include_router(sitemap_routes.router, prefix="/sitemap-watcher", tags=["sitemap-watcher"])
app.include_router(perf_monitor_routes.router, prefix="/perf-monitor", tags=["perf-monitor"])
app.include_router(seo_tracker_routes.router, prefix="/seo-tracker", tags=["seo-tracker"])
app.include_router(scheduler_routes.router, prefix="/scheduler", tags=["scheduler"])


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
def _start_scheduler() -> None:
    """Start the in-process cron scheduler when SCHEDULER_ENABLED=1."""
    scheduler_service.start()


@app.on_event("shutdown")
def _shutdown_pool() -> None:
    """Release background workers + scheduler when the server stops."""
    scheduler_service.shutdown(wait=False)
    shutdown_executor(wait=False)


@app.get("/health")
def health() -> dict[str, str]:
    active_model = (
        settings.anthropic_model
        if settings.llm_provider == "anthropic"
        else settings.gemini_model
    )
    return {
        "status": "ok",
        "provider": settings.llm_provider,
        "model": active_model,
    }
