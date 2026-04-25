"""Bulk audit endpoints."""

from __future__ import annotations

import csv
import io
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from api.models import BulkAudit, BulkAuditRequest
from api.services import bulk as bulk_service
from api.services.store import get_store

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=BulkAudit, status_code=202)
def start_bulk(req: BulkAuditRequest) -> BulkAudit:
    return bulk_service.create_bulk(
        urls=[str(u) for u in req.urls],
        labels=req.labels,
    )


@router.get("", response_model=list[BulkAudit])
def list_bulks() -> list[BulkAudit]:
    return get_store().list_bulks()


@router.get("/{bulk_id}", response_model=BulkAudit)
def get_bulk(bulk_id: str) -> BulkAudit:
    bulk = get_store().get_bulk(bulk_id)
    if bulk is None:
        raise HTTPException(status_code=404, detail="Bulk introuvable")
    return bulk_service.refresh_status(bulk)


@router.delete("/{bulk_id}", status_code=204)
def delete_bulk(bulk_id: str) -> Response:
    if not get_store().delete_bulk(bulk_id):
        raise HTTPException(status_code=404, detail="Bulk introuvable")
    return Response(status_code=204)


@router.get("/{bulk_id}/csv")
def export_bulk_csv(bulk_id: str) -> Response:
    """Consolidated CSV: one row per URL with global score and key counts."""
    store = get_store()
    bulk = store.get_bulk(bulk_id)
    if bulk is None:
        raise HTTPException(status_code=404, detail="Bulk introuvable")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "url",
            "label",
            "domain",
            "status",
            "globalScore",
            "globalVerdict",
            "criticalCount",
            "warningCount",
            "auditId",
            "error",
        ]
    )
    for item in bulk.items:
        job = store.get(item.auditId) if item.auditId else None
        if job is None:
            writer.writerow(
                [item.url, item.label or "", "", "missing", "", "", "", "",
                 item.auditId or "", "audit row missing"]
            )
            continue
        result = job.result
        writer.writerow(
            [
                item.url,
                item.label or "",
                job.domain,
                job.status,
                result.globalScore if result else "",
                result.globalVerdict if result else "",
                result.criticalCount if result else "",
                result.warningCount if result else "",
                job.id,
                job.error or "",
            ]
        )

    csv_bytes = output.getvalue().encode("utf-8-sig")  # BOM for Excel
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="bulk-{bulk_id[:12]}.csv"',
        },
    )
