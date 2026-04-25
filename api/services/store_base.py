"""Shared type definitions for audit stores.

Both the in-memory and SQL implementations return the same `AuditJob`
dataclass. Keeping it here avoids a circular import between them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from api.models import AuditResult, CrawlData


JobStatus = Literal["pending", "done", "failed"]


@dataclass
class AuditJob:
    id: str
    url: str
    domain: str
    created_at: str
    status: JobStatus = "pending"
    error: Optional[str] = None
    archived: bool = False
    result: Optional[AuditResult] = None
    crawl: Optional[CrawlData] = None
