"""Settings endpoints — agency branding only for now."""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from api.models import AgencyBranding
from api.services import branding

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/branding", response_model=AgencyBranding)
def get_branding() -> AgencyBranding:
    return branding.load()


@router.put("/branding", response_model=AgencyBranding)
def update_branding(payload: AgencyBranding) -> AgencyBranding:
    try:
        return branding.save(payload)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/branding/logo", response_model=AgencyBranding)
async def upload_logo(file: UploadFile = File(...)) -> AgencyBranding:
    try:
        data = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lecture du fichier échouée : {e}") from e

    content_type = file.content_type or "application/octet-stream"
    try:
        return branding.save_logo(data, content_type)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.delete("/branding/logo", response_model=AgencyBranding)
def delete_logo() -> AgencyBranding:
    return branding.clear_logo()


@router.get("/branding/logo")
def get_logo() -> Response:
    path = branding.logo_path()
    if path is None:
        raise HTTPException(status_code=404, detail="Aucun logo configuré")
    return FileResponse(
        path,
        media_type=branding.logo_content_type(path),
        headers={"Cache-Control": "public, max-age=60"},
    )
