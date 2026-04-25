"""SEO Tracker endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from api.models import (
    SeoCampaign,
    SeoCampaignAddKeywordsRequest,
    SeoCampaignRequest,
)
from api.services import seo_tracker as seo
from api.services.store import get_store

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=SeoCampaign)
def create(req: SeoCampaignRequest) -> SeoCampaign:
    try:
        return seo.create_campaign(
            domain=req.domain, keywords=req.keywords, locale=req.locale,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=list[SeoCampaign])
def list_campaigns() -> list[SeoCampaign]:
    return get_store().list_seo()


@router.get("/{campaign_id}", response_model=SeoCampaign)
def get_campaign(campaign_id: str) -> SeoCampaign:
    campaign = get_store().get_seo(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campagne introuvable")
    return campaign


@router.post("/{campaign_id}/check", response_model=SeoCampaign)
def run_check(campaign_id: str) -> SeoCampaign:
    try:
        return seo.run_check(campaign_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("SEO check failed")
        raise HTTPException(status_code=500, detail=f"Échec : {e}")


@router.post("/{campaign_id}/keywords", response_model=SeoCampaign)
def add_keywords(
    campaign_id: str, req: SeoCampaignAddKeywordsRequest
) -> SeoCampaign:
    try:
        return seo.add_keywords(campaign_id, req.keywords)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{campaign_id}", status_code=204)
def delete_campaign(campaign_id: str) -> Response:
    if not get_store().delete_seo(campaign_id):
        raise HTTPException(status_code=404, detail="Campagne introuvable")
    return Response(status_code=204)
