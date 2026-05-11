"""Audit endpoints — async job lifecycle, archive/delete, PDF rendering."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

_FILENAME_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(stem: str) -> str:
    """Build a file-system-safe filename stem (keeps domain recognizable)."""
    cleaned = _FILENAME_UNSAFE.sub("-", stem).strip("-._") or "audit"
    return cleaned[:80]

from api.models import (
    AuditJobDetail,
    AuditJobSummary,
    AuditRequest,
    AuditResult,
)
from api.services import branding as branding_service, drift
from api.services.pdf_generator import generate_pdf
from api.services.runner import submit_audit
from api.services.store import AuditJob, get_store
from api.services.xlsx_generator import generate_xlsx

logger = logging.getLogger(__name__)

router = APIRouter()


class PdfRequest(BaseModel):
    audit: AuditResult
    agencyName: Optional[str] = None


class ArchiveRequest(BaseModel):
    archived: bool


class ScoreDeltaOut(BaseModel):
    axis: str
    baseline: int
    current: int
    delta: int
    direction: str


class FindingOut(BaseModel):
    severity: str
    title: str
    description: str


class FindingsBucketOut(BaseModel):
    resolved: list[FindingOut]
    appeared: list[FindingOut]
    persistent: list[FindingOut]


class DriftResponse(BaseModel):
    baselineId: str
    baselineDate: str
    currentId: str
    currentDate: str
    domain: str
    globalDelta: ScoreDeltaOut
    axisDeltas: list[ScoreDeltaOut]
    perAxisFindings: dict[str, FindingsBucketOut]
    resolvedCount: int
    appearedCount: int
    persistentCount: int


def _summary(job: AuditJob) -> AuditJobSummary:
    result = job.result
    return AuditJobSummary(
        id=job.id,
        url=job.url,
        domain=job.domain,
        createdAt=job.created_at,
        status=job.status,
        error=job.error,
        archived=job.archived,
        globalScore=result.globalScore if result else None,
        globalVerdict=result.globalVerdict if result else None,
        criticalCount=result.criticalCount if result else None,
        warningCount=result.warningCount if result else None,
    )


def _detail(job: AuditJob) -> AuditJobDetail:
    return AuditJobDetail(
        id=job.id,
        url=job.url,
        domain=job.domain,
        createdAt=job.created_at,
        status=job.status,
        error=job.error,
        archived=job.archived,
        result=job.result,
    )


@router.post("", response_model=AuditJobSummary, status_code=202)
def run_audit(req: AuditRequest) -> AuditJobSummary:
    """Create a pending job and launch the pipeline in the background."""
    url = str(req.url)
    job_id = uuid.uuid4().hex
    domain = urlparse(url).netloc or url
    job = get_store().create_job(job_id, url, domain)
    submit_audit(job_id, url, max_pages=req.maxPages)
    return _summary(job)


@router.get("/by-domain", response_model=list[AuditJobSummary])
def list_by_domain(domain: str = Query(..., min_length=1)) -> list[AuditJobSummary]:
    """Recent audits for a domain — used by the compare UI to pick a baseline."""
    jobs = get_store().list_by_domain(domain)
    return [_summary(j) for j in jobs]


@router.get("/{audit_id}/compare", response_model=DriftResponse)
def compare_audits(
    audit_id: str,
    against: Optional[str] = Query(
        None,
        description=(
            "Baseline audit id. If omitted, the previous audit on the same "
            "domain is used automatically."
        ),
    ),
) -> DriftResponse:
    store = get_store()
    current_job = store.get(audit_id)
    if current_job is None or current_job.result is None:
        raise HTTPException(status_code=404, detail="Audit courant introuvable ou incomplet")

    baseline_job: Optional[AuditJob] = None
    if against:
        baseline_job = store.get(against)
    else:
        candidates = store.list_by_domain(current_job.domain, limit=10)
        for candidate in candidates:
            if candidate.id == audit_id:
                continue
            if candidate.result is None:
                continue
            baseline_job = candidate
            break

    if baseline_job is None or baseline_job.result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Aucun audit précédent exploitable pour ce domaine. "
                "Relancez une analyse pour créer un point de comparaison."
            ),
        )
    if baseline_job.id == current_job.id:
        raise HTTPException(
            status_code=400, detail="Impossible de comparer un audit avec lui-même"
        )

    report = drift.compare(baseline_job.result, current_job.result)

    def _f(f) -> FindingOut:
        return FindingOut(
            severity=f.severity, title=f.title, description=f.description
        )

    return DriftResponse(
        baselineId=report.baseline_id,
        baselineDate=report.baseline_date,
        currentId=report.current_id,
        currentDate=report.current_date,
        domain=report.domain,
        globalDelta=ScoreDeltaOut(**report.global_delta.__dict__),
        axisDeltas=[ScoreDeltaOut(**d.__dict__) for d in report.axis_deltas],
        perAxisFindings={
            name: FindingsBucketOut(
                resolved=[_f(x) for x in b.resolved],
                appeared=[_f(x) for x in b.appeared],
                persistent=[_f(x) for x in b.persistent],
            )
            for name, b in report.per_axis_findings.items()
        },
        resolvedCount=report.resolved_count,
        appearedCount=report.appeared_count,
        persistentCount=report.persistent_count,
    )


@router.get("/recent", response_model=list[AuditJobSummary])
def list_recent(
    include_archived: bool = Query(False, alias="includeArchived"),
) -> list[AuditJobSummary]:
    jobs = get_store().list_recent(include_archived=include_archived)
    return [_summary(j) for j in jobs]


@router.get("/archived", response_model=list[AuditJobSummary])
def list_archived() -> list[AuditJobSummary]:
    return [_summary(j) for j in get_store().list_archived()]


@router.get("/{audit_id}", response_model=AuditJobDetail)
def get_audit(audit_id: str) -> AuditJobDetail:
    job = get_store().get(audit_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    return _detail(job)


@router.patch("/{audit_id}/archive", response_model=AuditJobSummary)
def set_archive(audit_id: str, req: ArchiveRequest) -> AuditJobSummary:
    store = get_store()
    if not store.set_archived(audit_id, req.archived):
        raise HTTPException(status_code=404, detail="Audit not found")
    job = store.get(audit_id)
    assert job is not None
    return _summary(job)


@router.delete("/{audit_id}", status_code=204)
def delete_audit(audit_id: str) -> Response:
    if not get_store().delete(audit_id):
        raise HTTPException(status_code=404, detail="Audit not found")
    return Response(status_code=204)


@router.get("/{audit_id}/pdf")
def download_pdf(audit_id: str, agency: Optional[str] = None) -> Response:
    job = get_store().get(audit_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    if job.status != "done" or job.result is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Audit pas encore prêt."
                if job.status == "pending"
                else f"Audit échoué : {job.error or 'erreur inconnue'}"
            ),
        )
    branding = branding_service.load()
    try:
        data = generate_pdf(job.result, agency_name=agency, branding=branding)
    except Exception as e:
        logger.exception("PDF generation error")
        raise HTTPException(status_code=500, detail="PDF generation failed") from e

    filename = f"audit-{_safe_filename(job.domain)}.pdf"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{audit_id}/xlsx")
def download_xlsx(audit_id: str) -> Response:
    job = get_store().get(audit_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    if job.status != "done" or job.result is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Audit pas encore prêt."
                if job.status == "pending"
                else f"Audit échoué : {job.error or 'erreur inconnue'}"
            ),
        )
    branding = branding_service.load()
    try:
        data = generate_xlsx(job.result, branding=branding)
    except Exception as e:
        logger.exception("XLSX generation error")
        raise HTTPException(status_code=500, detail="Excel generation failed") from e

    filename = f"audit-{_safe_filename(job.domain)}.xlsx"
    return Response(
        content=data,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/pdf")
def render_pdf_from_body(req: PdfRequest) -> Response:
    """Fallback: render a PDF from an AuditResult posted in the body (no store)."""
    branding = branding_service.load()
    try:
        data = generate_pdf(req.audit, agency_name=req.agencyName, branding=branding)
    except Exception as e:
        logger.exception("PDF generation error")
        raise HTTPException(status_code=500, detail="PDF generation failed") from e

    filename = f"audit-{_safe_filename(req.audit.domain)}.pdf"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
