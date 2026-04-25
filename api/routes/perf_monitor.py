"""Performance Monitor endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from api.models import PerfMonitor, PerfMonitorRequest
from api.services import perf_monitor as pm
from api.services.store import get_store

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=PerfMonitor)
def watch(req: PerfMonitorRequest) -> PerfMonitor:
    try:
        return pm.watch_url(str(req.url), strategy=req.strategy)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Perf watch failed")
        raise HTTPException(status_code=500, detail=f"Échec : {e}")


@router.get("", response_model=list[PerfMonitor])
def list_monitors() -> list[PerfMonitor]:
    return get_store().list_perfs()


@router.get("/{perf_id}", response_model=PerfMonitor)
def get_monitor(perf_id: str) -> PerfMonitor:
    monitor = get_store().get_perf(perf_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor introuvable")
    return monitor


@router.post("/{perf_id}/refresh", response_model=PerfMonitor)
def refresh(perf_id: str) -> PerfMonitor:
    monitor = get_store().get_perf(perf_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor introuvable")
    return pm.watch_url(monitor.url, strategy=monitor.strategy)


@router.delete("/{perf_id}", status_code=204)
def delete_monitor(perf_id: str) -> Response:
    if not get_store().delete_perf(perf_id):
        raise HTTPException(status_code=404, detail="Monitor introuvable")
    return Response(status_code=204)
