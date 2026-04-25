"""Sitemap watcher endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from api.models import SitemapWatch, SitemapWatchRequest
from api.services import sitemap_watcher as sm
from api.services.store import get_store

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=SitemapWatch)
def add_or_refresh(req: SitemapWatchRequest) -> SitemapWatch:
    try:
        return sm.watch_site(str(req.url))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Sitemap watch failed")
        raise HTTPException(status_code=500, detail=f"Échec : {e}")


@router.get("", response_model=list[SitemapWatch])
def list_watches() -> list[SitemapWatch]:
    return get_store().list_sitemaps()


@router.get("/{watch_id}", response_model=SitemapWatch)
def get_watch(watch_id: str) -> SitemapWatch:
    watch = get_store().get_sitemap(watch_id)
    if watch is None:
        raise HTTPException(status_code=404, detail="Watch introuvable")
    return watch


@router.post("/{watch_id}/refresh", response_model=SitemapWatch)
def refresh_watch(watch_id: str) -> SitemapWatch:
    watch = get_store().get_sitemap(watch_id)
    if watch is None:
        raise HTTPException(status_code=404, detail="Watch introuvable")
    try:
        return sm.refresh_watch(watch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Sitemap refresh failed")
        raise HTTPException(status_code=500, detail=f"Échec : {e}")


@router.delete("/{watch_id}", status_code=204)
def delete_watch(watch_id: str) -> Response:
    if not get_store().delete_sitemap(watch_id):
        raise HTTPException(status_code=404, detail="Watch introuvable")
    return Response(status_code=204)
