"""SQLAlchemy tables.

Design: one row per audit job. The full `AuditResult` payload + the
associated crawl data are stored as JSON columns. Rationale:
- The payload is deeply nested (sections → findings → actions, pages →
  recommendations → actions) and is always read/written in bulk by the API.
  Normalising would require 6+ tables for zero query benefit.
- Postgres has native JSONB with fast indexing if we ever need to filter
  inside the payload later. SQLite stores it as TEXT transparently.
- Columns promoted out of JSON (`id`, `domain`, `status`, `created_at`,
  `archived`) are the ones we actually filter/sort by, so they get proper
  indexes.
"""

"""SQLAlchemy table definition.

Note: annotations are intentionally NOT `from __future__ import annotations`
because SQLAlchemy 2.x's `Mapped[...]` resolver needs to see the real types
at class body evaluation. Stick to `Optional[X]` instead of `X | None`.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, String, Text, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AuditRow(Base):
    __tablename__ = "audits"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    result_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    crawl_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_audits_domain_created", "domain", "created_at"),
        Index("ix_audits_status", "status"),
        Index("ix_audits_archived", "archived"),
    )


class ContentBriefRow(Base):
    __tablename__ = "content_briefs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="fr-FR")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    payload_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_briefs_created", "created_at"),
        Index("ix_briefs_status", "status"),
    )


class ProspectSheetRow(Base):
    __tablename__ = "prospect_sheets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    payload_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_prospects_created", "created_at"),
        Index("ix_prospects_status", "status"),
    )


class AiVisibilityRow(Base):
    __tablename__ = "ai_visibility_checks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    payload_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_aivis_created", "created_at"),
        Index("ix_aivis_status", "status"),
    )


class BulkAuditRow(Base):
    __tablename__ = "bulk_audits"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    payload_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_bulk_created", "created_at"),
        Index("ix_bulk_status", "status"),
    )


class SitemapWatchRow(Base):
    __tablename__ = "sitemap_watches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    payload_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_sitemap_domain", "domain"),
        Index("ix_sitemap_updated", "updated_at"),
    )


class PerfMonitorRow(Base):
    __tablename__ = "perf_monitors"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    strategy: Mapped[str] = mapped_column(String(16), nullable=False, default="mobile")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    payload_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_perf_updated", "updated_at"),
    )


class SeoCampaignRow(Base):
    __tablename__ = "seo_campaigns"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    payload_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_seo_domain", "domain"),
        Index("ix_seo_updated", "updated_at"),
    )


class CompetitorBattleRow(Base):
    __tablename__ = "competitor_battles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    # Full CompetitorBattle serialized (sites + report).
    payload_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_battles_status", "status"),
        Index("ix_battles_created", "created_at"),
    )
