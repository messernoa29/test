"""AI Search Visibility endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from api.models import AiVisibilityCheck, AiVisibilityRequest
from api.services.runner import create_ai_visibility_job
from api.services.store import get_store

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=AiVisibilityCheck, status_code=202)
def start_check(req: AiVisibilityRequest) -> AiVisibilityCheck:
    return create_ai_visibility_job(
        target_domain=req.targetDomain,
        queries=req.queries,
        target_name=req.targetName,
    )


@router.get("", response_model=list[AiVisibilityCheck])
def list_checks() -> list[AiVisibilityCheck]:
    return get_store().list_ai_checks()


@router.get("/{check_id}", response_model=AiVisibilityCheck)
def get_check(check_id: str) -> AiVisibilityCheck:
    check = get_store().get_ai_check(check_id)
    if check is None:
        raise HTTPException(status_code=404, detail="Vérification introuvable")
    return check


@router.delete("/{check_id}", status_code=204)
def delete_check(check_id: str) -> Response:
    if not get_store().delete_ai_check(check_id):
        raise HTTPException(status_code=404, detail="Vérification introuvable")
    return Response(status_code=204)
