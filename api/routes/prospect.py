"""Prospect Sheet endpoints — pre-meeting brief from a company's website."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from api.models import ProspectRequest, ProspectSheet
from api.services.prospect_pdf_generator import generate_prospect_pdf
from api.services.runner import create_prospect_job
from api.services.store import get_store

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=ProspectSheet, status_code=202)
def start_prospect(req: ProspectRequest) -> ProspectSheet:
    return create_prospect_job(url=str(req.url))


@router.get("", response_model=list[ProspectSheet])
def list_prospects() -> list[ProspectSheet]:
    return get_store().list_prospects()


@router.get("/{prospect_id}", response_model=ProspectSheet)
def get_prospect(prospect_id: str) -> ProspectSheet:
    sheet = get_store().get_prospect(prospect_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="Fiche prospect introuvable")
    return sheet


@router.get("/{prospect_id}/pdf")
def download_prospect_pdf(prospect_id: str) -> Response:
    sheet = get_store().get_prospect(prospect_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="Fiche prospect introuvable")
    if sheet.status != "done":
        raise HTTPException(
            status_code=409,
            detail="La fiche n'est pas encore prête (statut : %s)" % sheet.status,
        )
    try:
        data = generate_prospect_pdf(sheet)
    except Exception as e:  # pragma: no cover - defensive
        logger.exception("Prospect PDF generation failed for %s: %s", prospect_id, e)
        raise HTTPException(status_code=500, detail="Échec de la génération du PDF")
    slug = (sheet.domain or sheet.id).replace("/", "-").replace(":", "-")
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="fiche-prospect-{slug}.pdf"'},
    )


@router.delete("/{prospect_id}", status_code=204)
def delete_prospect(prospect_id: str) -> Response:
    if not get_store().delete_prospect(prospect_id):
        raise HTTPException(status_code=404, detail="Fiche prospect introuvable")
    return Response(status_code=204)
