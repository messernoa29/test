"""Bulk audit orchestrator.

Takes a list of URLs and queues a regular audit pipeline for each one,
tracking the cohort under a single `BulkAudit` row. No LLM synthesis — the
goal is throughput, not comparative analysis (use Competitor Watch for that).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from api.models import BulkAudit, BulkAuditItem
from api.services.store import get_store

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_bulk(
    urls: list[str], labels: Optional[list[str]] = None
) -> BulkAudit:
    """Create a bulk row, kick off one audit per URL, return the populated row."""
    # Lazy import to avoid circular dependency runner -> bulk -> runner.
    from api.services.runner import _get_executor, _run

    store = get_store()
    bulk_id = uuid.uuid4().hex
    items: list[BulkAuditItem] = []
    for index, url in enumerate(urls):
        url_str = str(url)
        audit_id = uuid.uuid4().hex
        domain = urlparse(url_str).netloc or url_str
        store.create_job(audit_id, url_str, domain)
        _get_executor().submit(_run, audit_id, url_str)
        label = None
        if labels and index < len(labels):
            raw = (labels[index] or "").strip()
            if raw:
                label = raw[:120]
        items.append(BulkAuditItem(url=url_str, auditId=audit_id, label=label))

    bulk = BulkAudit(
        id=bulk_id,
        createdAt=_now_iso(),
        status="running",
        items=items,
    )
    store.save_bulk(bulk)
    return bulk


def refresh_status(bulk: BulkAudit) -> BulkAudit:
    """Recompute the bulk-level status from its underlying audits."""
    store = get_store()
    if not bulk.items:
        return bulk

    pending = 0
    failed = 0
    done = 0
    for item in bulk.items:
        if not item.auditId:
            failed += 1
            continue
        job = store.get(item.auditId)
        if job is None:
            failed += 1
            continue
        if job.status == "pending":
            pending += 1
        elif job.status == "failed":
            failed += 1
        else:
            done += 1

    if pending == 0:
        new_status = "done" if failed < len(bulk.items) else "failed"
        if bulk.status != new_status:
            updated = bulk.model_copy(update={"status": new_status})
            store.save_bulk(updated)
            return updated
    return bulk
