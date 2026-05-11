"""Tests for api.services.markdown_generator.generate_markdown."""

from __future__ import annotations

from api.models import (
    AuditResult,
    CulturalAuditSummary,
    CulturalLocaleReport,
    Finding,
    GeoAuditSummary,
    ProgrammaticAuditSummary,
    ProgrammaticGroup,
    SectionResult,
    SxoAuditSummary,
    SxoPageVerdict,
    TechnicalCrawlSummary,
    VisibilityEstimate,
)
from api.services.markdown_generator import generate_markdown


def _minimal_audit(**overrides) -> AuditResult:
    base = dict(
        id="abc123",
        domain="exemple.com",
        url="https://exemple.com",
        createdAt="2026-05-11T12:00:00",
        globalScore=62,
        globalVerdict="À consolider",
        scores={"security": 70, "seo": 55, "ux": 60, "content": 65, "performance": 50, "business": 72},
        sections=[
            SectionResult(
                section="seo",
                title="SEO technique & on-page",
                score=55,
                verdict="Quelques points à corriger.",
                findings=[
                    Finding(
                        severity="critical",
                        title="Balise title manquante sur la home",
                        description="La page d'accueil n'a pas de <title>.",
                        recommendation="Ajouter un title descriptif.",
                        actions=["Rédiger un title de 50-60 caractères"],
                        impact="high",
                        effort="quick",
                    )
                ],
            )
        ],
        criticalCount=1,
        warningCount=3,
        quickWins=["Ajouter une balise title", "Compresser les images"],
    )
    base.update(overrides)
    return AuditResult(**base)


def test_markdown_basic_structure():
    md = generate_markdown(_minimal_audit())
    assert "# Audit web — exemple.com" in md
    assert "| Axe | Score |" in md
    # quick wins rendered as checkboxes
    assert "- [ ] Ajouter une balise title" in md
    # critical finding severity emoji
    assert "🔴" in md
    # date truncated to YYYY-MM-DD
    assert "2026-05-11" in md


def test_markdown_with_agency_name():
    md = generate_markdown(_minimal_audit(), agency_name="Agence Démo")
    assert "_Réalisé par Agence Démo_" in md


def test_markdown_optional_sections_appear():
    audit = _minimal_audit(
        technicalCrawl=TechnicalCrawlSummary(pagesCrawled=5, indexablePages=4, nonIndexablePages=1, maxDepth=2),
        geoAudit=GeoAuditSummary(averagePageScore=58, hasLlmsTxt=False, siteWeaknesses=["/llms.txt absent"]),
        culturalAudit=CulturalAuditSummary(
            isMultilingual=True,
            detectedLocales=["fr", "de"],
            locales=[
                CulturalLocaleReport(
                    locale="fr",
                    label="Francophone",
                    pagesCount=10,
                    pagesWithIssues=0,
                    expectedNumberFormat="1 000,00",
                    expectedDateFormat="JJ/MM/AAAA",
                )
            ],
        ),
        sxoAudit=SxoAuditSummary(
            evaluated=2,
            mismatches=1,
            verdicts=[
                SxoPageVerdict(
                    url="https://exemple.com/blog/x",
                    keyword="acheter chaise",
                    pageType="article",
                    serpDominantType="product",
                    match=False,
                    severity="warning",
                    recommendation="Créer une page catégorie produit.",
                )
            ],
        ),
        programmaticAudit=ProgrammaticAuditSummary(
            isProgrammatic=True,
            groups=[
                ProgrammaticGroup(
                    pattern="/services/plomberie/{}",
                    pageCount=8,
                    sampleUrls=["https://exemple.com/services/plomberie/lyon"],
                    uniquenessRatio=0.2,
                    boilerplateRatio=0.8,
                    avgWordCount=180,
                    gate="HARD_STOP",
                    notes=["80% du contenu est partagé"],
                )
            ],
        ),
        visibilityEstimate=VisibilityEstimate(trafficRange="500–1 500 visites/mois", summary="Visibilité faible."),
    )
    md = generate_markdown(audit)
    assert "## Crawl technique" in md
    assert "## GEO — citabilité par les IA" in md
    assert "## Adaptation culturelle (site multilingue)" in md
    assert "## SXO — type de page vs intention SERP" in md
    assert "## Pages générées en masse (quality gates)" in md
    assert "## Visibilité organique (estimation)" in md


def test_markdown_ends_with_newline():
    md = generate_markdown(_minimal_audit())
    assert md.endswith("\n")
