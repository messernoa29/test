"""Re-export the demo fixture so it can be seeded into the store at startup."""

from __future__ import annotations

from api.models import AuditResult, CrawlData, CrawlPage
from api.scripts.test_pdf import build_fixture


def build_demo_audit() -> AuditResult:
    return build_fixture()


def build_demo_crawl(audit: AuditResult) -> CrawlData:
    """Minimal CrawlData accompagnant l'audit fixture (pas utilisé par l'UI,
    mais requis par AuditStore.save qui prend les deux)."""
    pages = [
        CrawlPage(
            url=p.url,
            title=p.title,
            h1=p.h1,
            metaDescription=p.metaDescription,
            headings=[],
            textSnippet="",
        )
        for p in (audit.pages or [])
    ]
    return CrawlData(
        domain=audit.domain,
        url=audit.url,
        crawledAt=audit.createdAt,
        pages=pages,
    )
