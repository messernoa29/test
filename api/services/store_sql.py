"""SQLAlchemy-backed implementation of the audit store.

Mirrors `InMemoryAuditStore` method-for-method so the rest of the app never
has to know which backend is active.

`AuditResult` and `CrawlData` are round-tripped via Pydantic's
`model_dump(mode="json")` / `model_validate` so every field (including the
HttpUrl and datetime types) serialises cleanly to JSON.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from api.db.models import (
    AiVisibilityRow,
    AuditRow,
    BulkAuditRow,
    CompetitorBattleRow,
    ContentBriefRow,
    PerfMonitorRow,
    ProspectSheetRow,
    SeoCampaignRow,
    SitemapWatchRow,
)
from api.db.session import create_all_tables, get_session
from api.models import (
    AiVisibilityCheck,
    AuditResult,
    BulkAudit,
    CompetitorBattle,
    ContentBrief,
    CrawlData,
    PerfMonitor,
    ProspectSheet,
    SeoCampaign,
    SitemapWatch,
)
from api.services.store_base import AuditJob

logger = logging.getLogger(__name__)


class SqlAuditStore:
    def __init__(self) -> None:
        # Ensure schema exists. Idempotent — safe to call on every boot.
        create_all_tables()

    # ------------------------------------------------------------------
    # Lifecycle

    def create_job(self, job_id: str, url: str, domain: str) -> AuditJob:
        now = datetime.now(timezone.utc)
        with self._session() as s:
            row = AuditRow(
                id=job_id,
                url=url,
                domain=domain,
                status="pending",
                archived=False,
                created_at=now,
                updated_at=now,
                result_json=None,
                crawl_json=None,
                error=None,
            )
            s.add(row)
            s.commit()
            return _to_job(row)

    def complete_job(self, job_id: str, audit: AuditResult, crawl: CrawlData) -> None:
        with self._session() as s:
            row = s.get(AuditRow, job_id)
            if row is None:
                return
            row.status = "done"
            row.error = None
            row.result_json = audit.model_dump(mode="json")
            row.crawl_json = crawl.model_dump(mode="json")
            # Pydantic's HttpUrl sometimes serialises with a trailing slash;
            # align the stored URL so filters stay consistent.
            if audit.domain:
                row.domain = audit.domain
            s.commit()

    def fail_job(self, job_id: str, error: str) -> None:
        with self._session() as s:
            row = s.get(AuditRow, job_id)
            if row is None:
                return
            row.status = "failed"
            row.error = error
            s.commit()

    def get(self, job_id: str) -> Optional[AuditJob]:
        with self._session() as s:
            row = s.get(AuditRow, job_id)
            return _to_job(row) if row else None

    # ------------------------------------------------------------------
    # Mutations

    def delete(self, job_id: str) -> bool:
        with self._session() as s:
            row = s.get(AuditRow, job_id)
            if row is None:
                return False
            s.delete(row)
            s.commit()
            return True

    def set_archived(self, job_id: str, archived: bool) -> bool:
        with self._session() as s:
            row = s.get(AuditRow, job_id)
            if row is None:
                return False
            row.archived = archived
            s.commit()
            return True

    def update_domain(self, job_id: str, domain: str) -> None:
        with self._session() as s:
            row = s.get(AuditRow, job_id)
            if row is None:
                return
            row.domain = domain
            s.commit()

    # ------------------------------------------------------------------
    # Listings

    def list_recent(
        self, limit: int = 20, include_archived: bool = False
    ) -> list[AuditJob]:
        with self._session() as s:
            stmt = select(AuditRow).order_by(AuditRow.created_at.desc()).limit(limit)
            if not include_archived:
                stmt = stmt.where(AuditRow.archived.is_(False))
            rows = s.execute(stmt).scalars().all()
            return [_to_job(r) for r in rows]

    def list_archived(self, limit: int = 50) -> list[AuditJob]:
        with self._session() as s:
            stmt = (
                select(AuditRow)
                .where(AuditRow.archived.is_(True))
                .order_by(AuditRow.created_at.desc())
                .limit(limit)
            )
            rows = s.execute(stmt).scalars().all()
            return [_to_job(r) for r in rows]

    def list_by_domain(self, domain: str, limit: int = 20) -> list[AuditJob]:
        needle = domain.lower().removeprefix("www.")
        with self._session() as s:
            # Simple scan — a handful of audits per domain, no need for fancy
            # SQL-level normalisation here.
            rows = (
                s.execute(
                    select(AuditRow).order_by(AuditRow.created_at.desc()).limit(500)
                )
                .scalars()
                .all()
            )
            matches = [
                r for r in rows
                if r.domain.lower().removeprefix("www.") == needle
            ]
            return [_to_job(r) for r in matches[:limit]]

    def has_pending(self) -> bool:
        with self._session() as s:
            count = s.execute(
                select(AuditRow.id).where(AuditRow.status == "pending").limit(1)
            ).first()
            return count is not None

    # ------------------------------------------------------------------
    # Seeding (fixture / demo)

    def save(self, audit: AuditResult, crawl: CrawlData) -> None:
        """Insert or replace a fully-resolved audit (used by the fixture seeder)."""
        with self._session() as s:
            row = s.get(AuditRow, audit.id)
            now = datetime.now(timezone.utc)
            if row is None:
                row = AuditRow(
                    id=audit.id,
                    url=audit.url,
                    domain=audit.domain,
                    status="done",
                    archived=False,
                    created_at=_parse_iso_datetime(audit.createdAt) or now,
                    updated_at=now,
                    result_json=audit.model_dump(mode="json"),
                    crawl_json=crawl.model_dump(mode="json"),
                )
                s.add(row)
            else:
                row.url = audit.url
                row.domain = audit.domain
                row.status = "done"
                row.archived = False
                row.error = None
                row.result_json = audit.model_dump(mode="json")
                row.crawl_json = crawl.model_dump(mode="json")
            s.commit()

    # ------------------------------------------------------------------
    # Maintenance

    def purge_all(self) -> None:
        """Only used by tests/debug — drops every row in the table."""
        with self._session() as s:
            s.execute(delete(AuditRow))
            s.commit()

    # ------------------------------------------------------------------
    # Competitor battles

    def save_battle(self, battle: CompetitorBattle) -> None:
        now = datetime.now(timezone.utc)
        with self._session() as s:
            row = s.get(CompetitorBattleRow, battle.id)
            if row is None:
                row = CompetitorBattleRow(
                    id=battle.id,
                    target_url=battle.targetUrl,
                    status=battle.status,
                    error=battle.error,
                    created_at=_parse_iso_datetime(battle.createdAt) or now,
                    updated_at=now,
                    payload_json=battle.model_dump(mode="json"),
                )
                s.add(row)
            else:
                row.target_url = battle.targetUrl
                row.status = battle.status
                row.error = battle.error
                row.payload_json = battle.model_dump(mode="json")
            s.commit()

    def get_battle(self, battle_id: str) -> Optional[CompetitorBattle]:
        with self._session() as s:
            row = s.get(CompetitorBattleRow, battle_id)
            if row is None or row.payload_json is None:
                return None
            try:
                return CompetitorBattle.model_validate(row.payload_json)
            except Exception as e:
                logger.warning("Could not decode battle %s: %s", battle_id, e)
                return None

    def list_battles(self, limit: int = 20) -> list[CompetitorBattle]:
        with self._session() as s:
            rows = (
                s.execute(
                    select(CompetitorBattleRow)
                    .order_by(CompetitorBattleRow.created_at.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            result: list[CompetitorBattle] = []
            for r in rows:
                if r.payload_json is None:
                    continue
                try:
                    result.append(CompetitorBattle.model_validate(r.payload_json))
                except Exception as e:
                    logger.warning("Skipping unreadable battle %s: %s", r.id, e)
            return result

    def delete_battle(self, battle_id: str) -> bool:
        with self._session() as s:
            row = s.get(CompetitorBattleRow, battle_id)
            if row is None:
                return False
            s.delete(row)
            s.commit()
            return True

    # ------------------------------------------------------------------
    # Content briefs

    def save_brief(self, brief: ContentBrief) -> None:
        now = datetime.now(timezone.utc)
        with self._session() as s:
            row = s.get(ContentBriefRow, brief.id)
            if row is None:
                row = ContentBriefRow(
                    id=brief.id,
                    query=brief.query,
                    locale=brief.locale,
                    status=brief.status,
                    error=brief.error,
                    created_at=_parse_iso_datetime(brief.createdAt) or now,
                    updated_at=now,
                    payload_json=brief.model_dump(mode="json"),
                )
                s.add(row)
            else:
                row.query = brief.query
                row.locale = brief.locale
                row.status = brief.status
                row.error = brief.error
                row.payload_json = brief.model_dump(mode="json")
            s.commit()

    def get_brief(self, brief_id: str) -> Optional[ContentBrief]:
        with self._session() as s:
            row = s.get(ContentBriefRow, brief_id)
            if row is None or row.payload_json is None:
                return None
            try:
                return ContentBrief.model_validate(row.payload_json)
            except Exception as e:
                logger.warning("Could not decode brief %s: %s", brief_id, e)
                return None

    def list_briefs(self, limit: int = 20) -> list[ContentBrief]:
        with self._session() as s:
            rows = (
                s.execute(
                    select(ContentBriefRow)
                    .order_by(ContentBriefRow.created_at.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            out: list[ContentBrief] = []
            for r in rows:
                if r.payload_json is None:
                    continue
                try:
                    out.append(ContentBrief.model_validate(r.payload_json))
                except Exception as e:
                    logger.warning("Skipping brief %s: %s", r.id, e)
            return out

    def delete_brief(self, brief_id: str) -> bool:
        with self._session() as s:
            row = s.get(ContentBriefRow, brief_id)
            if row is None:
                return False
            s.delete(row)
            s.commit()
            return True

    # ------------------------------------------------------------------
    # Prospect sheets

    def save_prospect(self, sheet: ProspectSheet) -> None:
        now = datetime.now(timezone.utc)
        with self._session() as s:
            row = s.get(ProspectSheetRow, sheet.id)
            if row is None:
                row = ProspectSheetRow(
                    id=sheet.id,
                    url=sheet.url,
                    domain=sheet.domain,
                    status=sheet.status,
                    error=sheet.error,
                    created_at=_parse_iso_datetime(sheet.createdAt) or now,
                    updated_at=now,
                    payload_json=sheet.model_dump(mode="json"),
                )
                s.add(row)
            else:
                row.url = sheet.url
                row.domain = sheet.domain
                row.status = sheet.status
                row.error = sheet.error
                row.payload_json = sheet.model_dump(mode="json")
            s.commit()

    def get_prospect(self, prospect_id: str) -> Optional[ProspectSheet]:
        with self._session() as s:
            row = s.get(ProspectSheetRow, prospect_id)
            if row is None or row.payload_json is None:
                return None
            try:
                return ProspectSheet.model_validate(row.payload_json)
            except Exception as e:
                logger.warning("Could not decode prospect %s: %s", prospect_id, e)
                return None

    def list_prospects(self, limit: int = 20) -> list[ProspectSheet]:
        with self._session() as s:
            rows = (
                s.execute(
                    select(ProspectSheetRow)
                    .order_by(ProspectSheetRow.created_at.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            out: list[ProspectSheet] = []
            for r in rows:
                if r.payload_json is None:
                    continue
                try:
                    out.append(ProspectSheet.model_validate(r.payload_json))
                except Exception as e:
                    logger.warning("Skipping prospect %s: %s", r.id, e)
            return out

    def delete_prospect(self, prospect_id: str) -> bool:
        with self._session() as s:
            row = s.get(ProspectSheetRow, prospect_id)
            if row is None:
                return False
            s.delete(row)
            s.commit()
            return True

    # ------------------------------------------------------------------
    # AI visibility checks

    def save_ai_check(self, check: AiVisibilityCheck) -> None:
        now = datetime.now(timezone.utc)
        with self._session() as s:
            row = s.get(AiVisibilityRow, check.id)
            if row is None:
                row = AiVisibilityRow(
                    id=check.id,
                    target_domain=check.targetDomain,
                    status=check.status,
                    error=check.error,
                    created_at=_parse_iso_datetime(check.createdAt) or now,
                    updated_at=now,
                    payload_json=check.model_dump(mode="json"),
                )
                s.add(row)
            else:
                row.target_domain = check.targetDomain
                row.status = check.status
                row.error = check.error
                row.payload_json = check.model_dump(mode="json")
            s.commit()

    def get_ai_check(self, check_id: str) -> Optional[AiVisibilityCheck]:
        with self._session() as s:
            row = s.get(AiVisibilityRow, check_id)
            if row is None or row.payload_json is None:
                return None
            try:
                return AiVisibilityCheck.model_validate(row.payload_json)
            except Exception as e:
                logger.warning("Could not decode ai_check %s: %s", check_id, e)
                return None

    def list_ai_checks(self, limit: int = 20) -> list[AiVisibilityCheck]:
        with self._session() as s:
            rows = (
                s.execute(
                    select(AiVisibilityRow)
                    .order_by(AiVisibilityRow.created_at.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            out: list[AiVisibilityCheck] = []
            for r in rows:
                if r.payload_json is None:
                    continue
                try:
                    out.append(AiVisibilityCheck.model_validate(r.payload_json))
                except Exception as e:
                    logger.warning("Skipping ai_check %s: %s", r.id, e)
            return out

    def delete_ai_check(self, check_id: str) -> bool:
        with self._session() as s:
            row = s.get(AiVisibilityRow, check_id)
            if row is None:
                return False
            s.delete(row)
            s.commit()
            return True

    # ------------------------------------------------------------------
    # Bulk audits

    def save_bulk(self, bulk: BulkAudit) -> None:
        now = datetime.now(timezone.utc)
        with self._session() as s:
            row = s.get(BulkAuditRow, bulk.id)
            if row is None:
                row = BulkAuditRow(
                    id=bulk.id,
                    status=bulk.status,
                    error=bulk.error,
                    created_at=_parse_iso_datetime(bulk.createdAt) or now,
                    updated_at=now,
                    payload_json=bulk.model_dump(mode="json"),
                )
                s.add(row)
            else:
                row.status = bulk.status
                row.error = bulk.error
                row.payload_json = bulk.model_dump(mode="json")
            s.commit()

    def get_bulk(self, bulk_id: str) -> Optional[BulkAudit]:
        with self._session() as s:
            row = s.get(BulkAuditRow, bulk_id)
            if row is None or row.payload_json is None:
                return None
            try:
                return BulkAudit.model_validate(row.payload_json)
            except Exception as e:
                logger.warning("Could not decode bulk %s: %s", bulk_id, e)
                return None

    def list_bulks(self, limit: int = 20) -> list[BulkAudit]:
        with self._session() as s:
            rows = (
                s.execute(
                    select(BulkAuditRow)
                    .order_by(BulkAuditRow.created_at.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            out: list[BulkAudit] = []
            for r in rows:
                if r.payload_json is None:
                    continue
                try:
                    out.append(BulkAudit.model_validate(r.payload_json))
                except Exception as e:
                    logger.warning("Skipping bulk %s: %s", r.id, e)
            return out

    def delete_bulk(self, bulk_id: str) -> bool:
        with self._session() as s:
            row = s.get(BulkAuditRow, bulk_id)
            if row is None:
                return False
            s.delete(row)
            s.commit()
            return True

    # ------------------------------------------------------------------
    # Sitemap watches

    def save_sitemap(self, watch: SitemapWatch) -> None:
        now = datetime.now(timezone.utc)
        with self._session() as s:
            row = s.get(SitemapWatchRow, watch.id)
            if row is None:
                row = SitemapWatchRow(
                    id=watch.id,
                    domain=watch.domain,
                    created_at=_parse_iso_datetime(watch.createdAt) or now,
                    updated_at=_parse_iso_datetime(watch.updatedAt) or now,
                    payload_json=watch.model_dump(mode="json"),
                )
                s.add(row)
            else:
                row.domain = watch.domain
                row.updated_at = _parse_iso_datetime(watch.updatedAt) or now
                row.payload_json = watch.model_dump(mode="json")
            s.commit()

    def get_sitemap(self, watch_id: str) -> Optional[SitemapWatch]:
        with self._session() as s:
            row = s.get(SitemapWatchRow, watch_id)
            if row is None or row.payload_json is None:
                return None
            try:
                return SitemapWatch.model_validate(row.payload_json)
            except Exception as e:
                logger.warning("Could not decode sitemap %s: %s", watch_id, e)
                return None

    def list_sitemaps(self, limit: int = 50) -> list[SitemapWatch]:
        with self._session() as s:
            rows = (
                s.execute(
                    select(SitemapWatchRow)
                    .order_by(SitemapWatchRow.updated_at.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            out: list[SitemapWatch] = []
            for r in rows:
                if r.payload_json is None:
                    continue
                try:
                    out.append(SitemapWatch.model_validate(r.payload_json))
                except Exception as e:
                    logger.warning("Skipping sitemap %s: %s", r.id, e)
            return out

    def delete_sitemap(self, watch_id: str) -> bool:
        with self._session() as s:
            row = s.get(SitemapWatchRow, watch_id)
            if row is None:
                return False
            s.delete(row)
            s.commit()
            return True

    # ------------------------------------------------------------------
    # Performance monitors

    def save_perf(self, perf: PerfMonitor) -> None:
        now = datetime.now(timezone.utc)
        with self._session() as s:
            row = s.get(PerfMonitorRow, perf.id)
            if row is None:
                row = PerfMonitorRow(
                    id=perf.id,
                    url=perf.url,
                    strategy=perf.strategy,
                    created_at=_parse_iso_datetime(perf.createdAt) or now,
                    updated_at=_parse_iso_datetime(perf.updatedAt) or now,
                    payload_json=perf.model_dump(mode="json"),
                )
                s.add(row)
            else:
                row.url = perf.url
                row.strategy = perf.strategy
                row.updated_at = _parse_iso_datetime(perf.updatedAt) or now
                row.payload_json = perf.model_dump(mode="json")
            s.commit()

    def get_perf(self, perf_id: str) -> Optional[PerfMonitor]:
        with self._session() as s:
            row = s.get(PerfMonitorRow, perf_id)
            if row is None or row.payload_json is None:
                return None
            try:
                return PerfMonitor.model_validate(row.payload_json)
            except Exception as e:
                logger.warning("Could not decode perf %s: %s", perf_id, e)
                return None

    def list_perfs(self, limit: int = 50) -> list[PerfMonitor]:
        with self._session() as s:
            rows = (
                s.execute(
                    select(PerfMonitorRow)
                    .order_by(PerfMonitorRow.updated_at.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            out: list[PerfMonitor] = []
            for r in rows:
                if r.payload_json is None:
                    continue
                try:
                    out.append(PerfMonitor.model_validate(r.payload_json))
                except Exception as e:
                    logger.warning("Skipping perf %s: %s", r.id, e)
            return out

    def delete_perf(self, perf_id: str) -> bool:
        with self._session() as s:
            row = s.get(PerfMonitorRow, perf_id)
            if row is None:
                return False
            s.delete(row)
            s.commit()
            return True

    # ------------------------------------------------------------------
    # SEO campaigns

    def save_seo(self, campaign: SeoCampaign) -> None:
        now = datetime.now(timezone.utc)
        with self._session() as s:
            row = s.get(SeoCampaignRow, campaign.id)
            if row is None:
                row = SeoCampaignRow(
                    id=campaign.id,
                    domain=campaign.domain,
                    created_at=_parse_iso_datetime(campaign.createdAt) or now,
                    updated_at=_parse_iso_datetime(campaign.updatedAt) or now,
                    payload_json=campaign.model_dump(mode="json"),
                )
                s.add(row)
            else:
                row.domain = campaign.domain
                row.updated_at = _parse_iso_datetime(campaign.updatedAt) or now
                row.payload_json = campaign.model_dump(mode="json")
            s.commit()

    def get_seo(self, campaign_id: str) -> Optional[SeoCampaign]:
        with self._session() as s:
            row = s.get(SeoCampaignRow, campaign_id)
            if row is None or row.payload_json is None:
                return None
            try:
                return SeoCampaign.model_validate(row.payload_json)
            except Exception as e:
                logger.warning("Could not decode seo %s: %s", campaign_id, e)
                return None

    def list_seo(self, limit: int = 50) -> list[SeoCampaign]:
        with self._session() as s:
            rows = (
                s.execute(
                    select(SeoCampaignRow)
                    .order_by(SeoCampaignRow.updated_at.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            out: list[SeoCampaign] = []
            for r in rows:
                if r.payload_json is None:
                    continue
                try:
                    out.append(SeoCampaign.model_validate(r.payload_json))
                except Exception as e:
                    logger.warning("Skipping seo %s: %s", r.id, e)
            return out

    def delete_seo(self, campaign_id: str) -> bool:
        with self._session() as s:
            row = s.get(SeoCampaignRow, campaign_id)
            if row is None:
                return False
            s.delete(row)
            s.commit()
            return True

    # ------------------------------------------------------------------
    # Session helper

    def _session(self) -> Session:
        return get_session()


# ---------------------------------------------------------------------------
# Row → AuditJob mapping


def _to_job(row: AuditRow) -> AuditJob:
    result = None
    crawl = None
    if row.result_json is not None:
        try:
            result = AuditResult.model_validate(row.result_json)
        except Exception as e:
            logger.warning("Could not decode result_json for %s: %s", row.id, e)
    if row.crawl_json is not None:
        try:
            crawl = CrawlData.model_validate(row.crawl_json)
        except Exception as e:
            logger.warning("Could not decode crawl_json for %s: %s", row.id, e)

    return AuditJob(
        id=row.id,
        url=row.url,
        domain=row.domain,
        created_at=row.created_at.isoformat() if row.created_at else "",
        status=row.status,  # type: ignore[assignment]
        error=row.error,
        archived=bool(row.archived),
        result=result,
        crawl=crawl,
    )


def _parse_iso_datetime(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None
