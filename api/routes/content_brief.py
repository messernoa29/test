"""Content Brief endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from api.models import ContentBrief, ContentBriefRequest
from api.services.runner import create_brief_job
from api.services.store import get_store

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=ContentBrief, status_code=202)
def start_brief(req: ContentBriefRequest) -> ContentBrief:
    return create_brief_job(query=req.query, locale=req.locale)


@router.get("", response_model=list[ContentBrief])
def list_briefs() -> list[ContentBrief]:
    return get_store().list_briefs()


@router.get("/{brief_id}", response_model=ContentBrief)
def get_brief(brief_id: str) -> ContentBrief:
    brief = get_store().get_brief(brief_id)
    if brief is None:
        raise HTTPException(status_code=404, detail="Brief introuvable")
    return brief


@router.delete("/{brief_id}", status_code=204)
def delete_brief(brief_id: str) -> Response:
    if not get_store().delete_brief(brief_id):
        raise HTTPException(status_code=404, detail="Brief introuvable")
    return Response(status_code=204)
