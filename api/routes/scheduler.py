"""Scheduler observability endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.services import scheduler as scheduler_service

router = APIRouter()


@router.get("")
def get_status() -> dict:
    return scheduler_service.status()


@router.post("/trigger/{job_id}")
def trigger(job_id: str) -> dict:
    if not scheduler_service.trigger_now(job_id):
        raise HTTPException(
            status_code=404,
            detail=(
                "Job inconnu. Valides: sitemap_refresh, perf_refresh, seo_check."
            ),
        )
    return {"status": "ok", "job": job_id}
