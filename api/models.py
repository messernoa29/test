"""Pydantic models mirroring lib/types.ts — keep in sync.

Validators are deliberately tolerant: the LLM output is unpredictable at the
margins and we'd rather degrade gracefully than reject a whole audit for a
single off-by-one value. The sanitization layer in analyzer.py handles
alias/enum fixes; these models take care of nullable strings, clamped
numbers, and default lists.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator

AuditSection = Literal[
    "security", "seo", "ux", "content", "performance", "business"
]
Severity = Literal["critical", "warning", "info", "ok", "missing"]
PageStatus = Literal["critical", "warning", "improve", "ok"]
Priority = Literal["high", "medium", "low"]


Impact = Literal["high", "medium", "low"]
Effort = Literal["quick", "medium", "heavy"]


_REQUIRED_SECTIONS: frozenset[str] = frozenset(
    ("security", "seo", "ux", "content", "performance", "business")
)


def _clamp_score(v: object) -> int:
    try:
        n = int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, n))


def _clamp_nonneg_int(v: object) -> int:
    try:
        n = int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return max(0, n)


def _coerce_str(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return str(v)


def _coerce_list(v: object) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return []


def _coerce_str_list(v: object) -> list[str]:
    if not isinstance(v, list):
        return []
    return [str(x) for x in v if x is not None]


class Finding(BaseModel):
    severity: Severity
    title: str
    description: str
    recommendation: Optional[str] = None
    actions: list[str] = Field(default_factory=list)
    impact: Optional[Impact] = None
    effort: Optional[Effort] = None
    evidence: Optional[str] = None
    reference: Optional[str] = None

    @field_validator("title", "description", mode="before")
    @classmethod
    def _str_fields(cls, v: object) -> str:
        return _coerce_str(v)

    @field_validator("actions", mode="before")
    @classmethod
    def _actions(cls, v: object) -> list[str]:
        return _coerce_str_list(v)


class SectionResult(BaseModel):
    section: AuditSection
    title: str
    score: int = Field(ge=0, le=100)
    verdict: str
    findings: list[Finding] = Field(default_factory=list)

    @field_validator("title", "verdict", mode="before")
    @classmethod
    def _strings(cls, v: object) -> str:
        return _coerce_str(v)

    @field_validator("score", mode="before")
    @classmethod
    def _score(cls, v: object) -> int:
        return _clamp_score(v)

    @field_validator("findings", mode="before")
    @classmethod
    def _findings(cls, v: object) -> list:
        return _coerce_list(v)


class PageRecommendation(BaseModel):
    urlCurrent: Optional[str] = None
    titleCurrent: Optional[str] = None
    h1Current: Optional[str] = None
    metaCurrent: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None
    h1: Optional[str] = None
    meta: Optional[str] = None
    actions: list[str] = Field(default_factory=list)
    estimatedMonthlyTraffic: Optional[int] = None

    @field_validator("actions", mode="before")
    @classmethod
    def _actions(cls, v: object) -> list[str]:
        return _coerce_str_list(v)

    @field_validator("estimatedMonthlyTraffic", mode="before")
    @classmethod
    def _traffic(cls, v: object) -> Optional[int]:
        if v is None or v == "":
            return None
        try:
            n = int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return max(0, n)


class PageTechnical(BaseModel):
    """Crawl-derived on-page facts merged into a PageAnalysis by the runner."""

    statusCode: Optional[int] = None
    depth: Optional[int] = None
    htmlBytes: int = 0
    wordCount: int = 0
    textRatio: float = 0.0
    canonical: Optional[str] = None
    canonicalIsSelf: Optional[bool] = None
    robotsMeta: str = ""
    htmlLang: str = ""
    hreflangLangs: list[str] = Field(default_factory=list)
    internalLinksOut: int = 0
    externalLinksOut: int = 0
    imagesCount: int = 0
    imagesWithoutAlt: int = 0
    hasViewportMeta: bool = True
    hasMixedContent: bool = False
    ogTitle: Optional[str] = None
    ogDescription: Optional[str] = None
    ogImage: Optional[str] = None
    twitterCard: Optional[str] = None
    redirectChain: list[str] = Field(default_factory=list)
    schemaTypes: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class PageAnalysis(BaseModel):
    url: str
    status: PageStatus
    title: str = ""
    titleLength: int = 0
    h1: str = ""
    metaDescription: Optional[str] = None
    metaLength: int = 0
    targetKeywords: list[str] = Field(default_factory=list)
    presentKeywords: list[str] = Field(default_factory=list)
    missingKeywords: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    recommendation: Optional[PageRecommendation] = None
    technical: Optional[PageTechnical] = None

    @field_validator("title", "h1", "url", mode="before")
    @classmethod
    def _strings(cls, v: object) -> str:
        return _coerce_str(v)

    @field_validator("titleLength", "metaLength", mode="before")
    @classmethod
    def _lengths(cls, v: object) -> int:
        return _clamp_nonneg_int(v)

    @field_validator(
        "targetKeywords", "presentKeywords", "missingKeywords", mode="before"
    )
    @classmethod
    def _kw(cls, v: object) -> list[str]:
        return _coerce_str_list(v)

    @field_validator("findings", mode="before")
    @classmethod
    def _findings(cls, v: object) -> list:
        return _coerce_list(v)


class MissingPage(BaseModel):
    url: str
    reason: str
    estimatedSearchVolume: Optional[int] = None
    priority: Priority

    @field_validator("url", "reason", mode="before")
    @classmethod
    def _strings(cls, v: object) -> str:
        return _coerce_str(v)

    @field_validator("estimatedSearchVolume", mode="before")
    @classmethod
    def _volume(cls, v: object) -> Optional[int]:
        if v is None or v == "":
            return None
        try:
            n = int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return max(0, n)


SchemaStatus = Literal["active", "restricted", "deprecated", "unknown"]
SchemaFormat = Literal["json-ld", "microdata", "rdfa"]


class DetectedSchema(BaseModel):
    """One Schema.org entity found on a page."""

    type: str  # e.g. "Organization", "LocalBusiness", "FAQPage"
    format: SchemaFormat
    status: SchemaStatus = "unknown"
    issues: list[str] = Field(default_factory=list)


class InternalLink(BaseModel):
    """Single internal anchor extracted from a crawled page."""

    target: str
    anchorText: str = ""
    rel: str = ""  # raw "rel" attribute (nofollow, sponsored, ugc...)


class HreflangEntry(BaseModel):
    """One <link rel="alternate" hreflang="..."> tag."""

    lang: str
    href: str


class OpenGraphData(BaseModel):
    """Social-card metadata observed on a page."""

    ogTitle: Optional[str] = None
    ogDescription: Optional[str] = None
    ogImage: Optional[str] = None
    ogType: Optional[str] = None
    twitterCard: Optional[str] = None
    hasViewportMeta: bool = False


class TechnicalPageRow(BaseModel):
    """One row of the Screaming-Frog-style crawl table."""

    url: str
    statusCode: Optional[int] = None  # None = no response / network error
    contentType: str = ""
    isIndexable: bool = True  # 200 + not noindex + canonical to self/none
    indexabilityReason: str = ""  # why not indexable, when applicable
    depth: Optional[int] = None  # clicks from the entry URL (BFS distance)
    htmlBytes: int = 0
    textBytes: int = 0
    textRatio: float = 0.0  # textBytes / htmlBytes
    titleLength: int = 0
    metaDescLength: int = 0
    h1Count: int = 0
    h2Count: int = 0
    wordCount: int = 0
    internalLinksOut: int = 0
    externalLinksOut: int = 0
    imagesCount: int = 0
    imagesWithoutAlt: int = 0
    issues: list[str] = Field(default_factory=list)  # short issue codes/labels


class TechnicalCrawlSummary(BaseModel):
    """Site-wide aggregates over the technical crawl, plus the per-page rows."""

    pagesCrawled: int = 0
    statusCounts: dict[str, int] = Field(default_factory=dict)  # "200" -> n
    indexablePages: int = 0
    nonIndexablePages: int = 0
    duplicateTitles: list[list[str]] = Field(default_factory=list)  # groups of URLs
    duplicateMetaDescriptions: list[list[str]] = Field(default_factory=list)
    duplicateH1s: list[list[str]] = Field(default_factory=list)
    missingTitles: list[str] = Field(default_factory=list)
    missingMetaDescriptions: list[str] = Field(default_factory=list)
    missingH1: list[str] = Field(default_factory=list)
    multipleH1: list[str] = Field(default_factory=list)
    titleTooLong: list[str] = Field(default_factory=list)  # > 60 chars
    titleTooShort: list[str] = Field(default_factory=list)  # < 30 chars
    metaTooLong: list[str] = Field(default_factory=list)  # > 160 chars
    metaTooShort: list[str] = Field(default_factory=list)  # 1..70 chars
    lowTextRatioPages: list[str] = Field(default_factory=list)  # < 0.10
    brokenInternalLinks: list[str] = Field(default_factory=list)  # 4xx/5xx targets
    maxDepth: int = 0
    rows: list[TechnicalPageRow] = Field(default_factory=list)


class ImageAsset(BaseModel):
    """One <img> tag observed on a page."""

    src: str
    alt: Optional[str] = None  # None when attribute missing entirely
    width: Optional[int] = None
    height: Optional[int] = None
    loading: str = ""  # "lazy" | "eager" | ""
    fileFormat: str = ""  # "webp" | "avif" | "jpg" | "png" | "gif" | "svg" | ""
    isInlineSvg: bool = False


class CrawlPage(BaseModel):
    url: str
    title: str = ""
    h1: str = ""
    metaDescription: Optional[str] = None
    headings: list[str] = Field(default_factory=list)
    textSnippet: str = ""
    schemas: list[DetectedSchema] = Field(default_factory=list)
    # True when the page was rendered via Playwright (JS fallback).
    renderedWithPlaywright: bool = False
    internalLinks: list[InternalLink] = Field(default_factory=list)
    internalLinksCount: int = 0
    # Hash of the normalized text body — used to detect exact duplicates.
    contentHash: str = ""
    # Word count of the normalized text — proxy for thin content detection.
    wordCount: int = 0
    # Final URL after redirects (may differ from request URL).
    finalUrl: str = ""
    # Redirect hops between request URL and final URL (each hop = one Location).
    redirectChain: list[str] = Field(default_factory=list)
    # Canonical URL declared by the page (<link rel="canonical">).
    canonical: Optional[str] = None
    # robots meta directives ("index,follow" / "noindex" / etc.).
    robotsMeta: str = ""
    # hreflang tags declared on the page.
    hreflang: list[HreflangEntry] = Field(default_factory=list)
    # Lang attribute on <html>.
    htmlLang: str = ""
    # Image inventory.
    images: list[ImageAsset] = Field(default_factory=list)
    imagesWithoutAlt: int = 0
    # Social-card metadata.
    openGraph: Optional[OpenGraphData] = None
    # HTTP status of the (final) response. 200 for fully crawled pages.
    statusCode: Optional[int] = None
    # Raw HTML byte length.
    htmlBytes: int = 0
    # Outbound link counts.
    externalLinksCount: int = 0
    # True if the page declares mixed content (http:// asset on https:// page).
    hasMixedContent: bool = False


class LinkGraphPageStat(BaseModel):
    """In-degree / out-degree for one crawled page."""

    url: str
    inDegree: int = 0
    outDegree: int = 0


class DeadInternalLink(BaseModel):
    """Internal link whose target returned 4xx/5xx or did not resolve."""

    target: str
    statusCode: Optional[int] = None
    sourceCount: int = 0  # how many crawled pages link to it


class LinkGraphSummary(BaseModel):
    """Aggregated stats across the crawled site's internal link graph."""

    totalEdges: int = 0
    pages: list[LinkGraphPageStat] = Field(default_factory=list)
    orphanPages: list[str] = Field(default_factory=list)  # in-degree 0
    hubPages: list[str] = Field(default_factory=list)  # top in-degree
    topAnchorTexts: list[str] = Field(default_factory=list)
    deadLinks: list[DeadInternalLink] = Field(default_factory=list)


class DuplicatePair(BaseModel):
    """Two pages whose content is similar above a threshold."""

    urlA: str
    urlB: str
    similarity: float  # 0.0 – 1.0 (Jaccard on shingles)
    kind: str = "near"  # "exact" (same hash) | "near" (Jaccard high)


class RedirectChain(BaseModel):
    """A page reached only after one or more redirects."""

    requestUrl: str
    finalUrl: str
    hops: list[str] = Field(default_factory=list)
    hopCount: int = 0


class PerformanceMetric(BaseModel):
    """One Core Web Vital with real + lab values when available."""

    name: str  # "LCP" | "INP" | "CLS" | "FCP" | "TTFB"
    fieldValue: Optional[float] = None  # CrUX (real users)
    fieldPercentile75: Optional[float] = None
    labValue: Optional[float] = None  # Lighthouse lab
    rating: Optional[str] = None  # "good" | "needs-improvement" | "poor"
    threshold: Optional[str] = None  # "< 2.5s", etc.


class PerformanceSnapshot(BaseModel):
    """Result of a PageSpeed Insights call on a URL."""

    url: str
    strategy: str  # "mobile" | "desktop"
    source: str  # "crux" | "lighthouse" | "mixed" | "unavailable"
    fetchedAt: str
    performanceScore: Optional[int] = None  # 0-100 from Lighthouse
    metrics: list[PerformanceMetric] = Field(default_factory=list)
    error: Optional[str] = None


class CrawlData(BaseModel):
    domain: str
    url: str
    crawledAt: str
    pages: list[CrawlPage] = Field(default_factory=list)
    performance: Optional[PerformanceSnapshot] = None
    performanceExtra: list[PerformanceSnapshot] = Field(default_factory=list)
    linkGraph: Optional[LinkGraphSummary] = None
    duplicates: list[DuplicatePair] = Field(default_factory=list)
    redirectChains: list[RedirectChain] = Field(default_factory=list)
    technicalCrawl: Optional[TechnicalCrawlSummary] = None


class EstimatedKeyword(BaseModel):
    keyword: str
    estimatedMonthlyVolume: Optional[int] = None  # rough order of magnitude
    estimatedPosition: Optional[int] = None  # where the site likely ranks (1-100)
    rankingUrl: Optional[str] = None  # which page probably ranks
    intent: str = ""  # "informational" | "transactional" | "navigational" | ""
    note: str = ""


class KeywordOpportunity(BaseModel):
    keyword: str
    estimatedMonthlyVolume: Optional[int] = None
    difficulty: str = ""  # "low" | "medium" | "high" | ""
    suggestedPage: str = ""  # existing URL to optimize, or "(nouvelle page)"
    rationale: str = ""


class VisibilityEstimate(BaseModel):
    """LLM-estimated organic visibility. Every number is an order-of-magnitude
    guess from public signals, NOT measured data."""

    disclaimer: str = (
        "Estimations indicatives produites par IA + recherche web. "
        "Ce ne sont PAS des données de clickstream type SEMrush/Ahrefs."
    )
    estimatedMonthlyOrganicTraffic: Optional[int] = None  # visits/month, rough
    trafficRange: str = ""  # e.g. "500–1 500 visites/mois"
    estimatedRankingKeywordsCount: Optional[int] = None  # how many KW the site ranks for
    topKeywords: list[EstimatedKeyword] = Field(default_factory=list)
    opportunities: list[KeywordOpportunity] = Field(default_factory=list)
    competitorsLikelyOutranking: list[str] = Field(default_factory=list)
    summary: str = ""


class AuditResult(BaseModel):
    id: str
    domain: str
    url: str
    createdAt: str
    globalScore: int = Field(ge=0, le=100)
    globalVerdict: str
    scores: dict[AuditSection, int]
    sections: list[SectionResult]
    criticalCount: int = 0
    warningCount: int = 0
    quickWins: list[str] = Field(default_factory=list)
    pages: Optional[list[PageAnalysis]] = None
    missingPages: Optional[list[MissingPage]] = None
    # Screaming-Frog-style technical crawl table (populated by the runner from
    # the CrawlData, not by the LLM).
    technicalCrawl: Optional[TechnicalCrawlSummary] = None
    # SEMrush-style organic visibility estimate (LLM + web_search, clearly
    # labelled as an estimate — NOT clickstream data).
    visibilityEstimate: Optional[VisibilityEstimate] = None

    @field_validator("globalScore", mode="before")
    @classmethod
    def _global_score(cls, v: object) -> int:
        return _clamp_score(v)

    @field_validator("criticalCount", "warningCount", mode="before")
    @classmethod
    def _counts(cls, v: object) -> int:
        return _clamp_nonneg_int(v)

    @field_validator("globalVerdict", mode="before")
    @classmethod
    def _verdict(cls, v: object) -> str:
        return _coerce_str(v) or "À consolider"

    @field_validator("quickWins", mode="before")
    @classmethod
    def _wins(cls, v: object) -> list[str]:
        return _coerce_str_list(v)

    @field_validator("scores", mode="before")
    @classmethod
    def _scores(cls, v: object) -> dict:
        """Guarantee every axis is present and in range.

        Missing axes default to 50 (neutral) rather than failing validation.
        Extra axes are dropped.
        """
        out: dict[str, int] = {s: 50 for s in _REQUIRED_SECTIONS}
        if isinstance(v, dict):
            for k, raw in v.items():
                if isinstance(k, str) and k in _REQUIRED_SECTIONS:
                    out[k] = _clamp_score(raw)
        return out


class AuditRequest(BaseModel):
    url: HttpUrl
    includeSeoDeep: bool = False
    agencyName: Optional[str] = None
    # Max pages to fully crawl. Clamped server-side to {50, 150, 300}.
    maxPages: int = 50

    @field_validator("maxPages", mode="before")
    @classmethod
    def _clamp_max_pages(cls, v: object) -> int:
        try:
            n = int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 50
        if n <= 50:
            return 50
        if n <= 150:
            return 150
        return 300


JobStatus = Literal["pending", "done", "failed"]


class AuditJobSummary(BaseModel):
    """Lightweight view of an audit — used in lists/sidebar."""

    id: str
    url: str
    domain: str
    createdAt: str
    status: JobStatus
    error: Optional[str] = None
    archived: bool = False
    globalScore: Optional[int] = None
    globalVerdict: Optional[str] = None
    criticalCount: Optional[int] = None
    warningCount: Optional[int] = None


class AuditJobDetail(BaseModel):
    """Full detail returned by GET /audit/{id} — handles all statuses."""

    id: str
    url: str
    domain: str
    createdAt: str
    status: JobStatus
    error: Optional[str] = None
    archived: bool = False
    result: Optional[AuditResult] = None


class AgencyBranding(BaseModel):
    """Identity of the agency displayed on generated reports.

    `logoUrl` is either a data URL (frontend preview) or a relative path
    served by the backend (/settings/branding/logo) once uploaded.
    """

    name: Optional[str] = None
    tagline: Optional[str] = None
    website: Optional[str] = None
    accentColor: Optional[str] = None  # hex, e.g. "#2563EB"
    logoUrl: Optional[str] = None
    updatedAt: Optional[str] = None


# --- Competitor Watch --------------------------------------------------------

CompetitorBattleStatus = Literal["pending", "running", "done", "failed"]


class CompetitorSite(BaseModel):
    """One competitor inside a battle: URL + pointer to its underlying audit."""

    url: str
    auditId: Optional[str] = None
    label: Optional[str] = None  # optional display name ("Nous" / concurrent)


class CompetitorReport(BaseModel):
    """LLM-produced synthesis across all sites in a battle."""

    winnersByAxis: dict[str, str] = Field(default_factory=dict)
    keyInsights: list[str] = Field(default_factory=list)
    ourStrengths: list[str] = Field(default_factory=list)
    ourWeaknesses: list[str] = Field(default_factory=list)
    priorityActions: list[str] = Field(default_factory=list)
    verdict: Optional[str] = None


class CompetitorBattle(BaseModel):
    """A comparison between one target site and N competitors."""

    id: str
    targetUrl: str
    competitors: list[CompetitorSite]
    createdAt: str
    status: CompetitorBattleStatus
    error: Optional[str] = None
    # Populated as soon as the first audit completes and fully built once
    # all audits are done.
    report: Optional[CompetitorReport] = None


class CompetitorBattleRequest(BaseModel):
    targetUrl: HttpUrl
    competitors: list[HttpUrl] = Field(min_length=1, max_length=5)


# --- Content Brief ----------------------------------------------------------

ContentBriefStatus = Literal["pending", "running", "done", "failed"]


class SerpResult(BaseModel):
    """One organic result inspected during the brief generation."""

    rank: int
    url: str
    title: str
    h1: Optional[str] = None
    headings: list[str] = Field(default_factory=list)
    metaDescription: Optional[str] = None
    wordCount: Optional[int] = None


class ContentBriefOutline(BaseModel):
    """A proposed H2 with optional H3 bullets and intent description."""

    title: str
    intent: Optional[str] = None
    bullets: list[str] = Field(default_factory=list)
    targetWords: Optional[int] = None


class ContentBriefResult(BaseModel):
    """LLM-produced editorial brief from the SERP analysis."""

    summary: Optional[str] = None
    intent: Optional[str] = None  # informational / commercial / navigational
    targetAudience: Optional[str] = None
    suggestedTitle: Optional[str] = None
    suggestedMeta: Optional[str] = None
    h1: Optional[str] = None
    targetWordCount: Optional[int] = None
    primaryKeywords: list[str] = Field(default_factory=list)
    semanticKeywords: list[str] = Field(default_factory=list)
    outline: list[ContentBriefOutline] = Field(default_factory=list)
    faq: list[str] = Field(default_factory=list)
    quickWins: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class ContentBrief(BaseModel):
    """A brief job — request + status + serp data + result."""

    id: str
    query: str
    locale: str = "fr-FR"
    createdAt: str
    status: ContentBriefStatus
    error: Optional[str] = None
    serpResults: list[SerpResult] = Field(default_factory=list)
    result: Optional[ContentBriefResult] = None


class ContentBriefRequest(BaseModel):
    query: str = Field(min_length=3, max_length=200)
    locale: str = Field(default="fr-FR", min_length=2, max_length=10)


# --- AI Search Visibility ---------------------------------------------------

AiVisibilityStatus = Literal["pending", "running", "done", "failed"]


class AiCitation(BaseModel):
    """One source cited by an AI engine when answering a query."""

    url: Optional[str] = None
    title: Optional[str] = None
    snippet: Optional[str] = None


class AiQueryResult(BaseModel):
    """Result of probing one query against one AI engine."""

    engine: str  # "gemini" | "anthropic" | …
    query: str
    answer: Optional[str] = None
    cited: bool = False  # target domain found in citations
    targetMentioned: bool = False  # target name mentioned in answer text
    citations: list[AiCitation] = Field(default_factory=list)
    error: Optional[str] = None


class AiVisibilityReport(BaseModel):
    """LLM-produced synthesis once all probes are done."""

    summary: Optional[str] = None
    citationRate: float = 0.0  # 0..1
    mentionRate: float = 0.0
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)


class AiVisibilityCheck(BaseModel):
    """A check job — target site + queries + per-query probe results."""

    id: str
    targetDomain: str
    targetName: Optional[str] = None
    queries: list[str]
    createdAt: str
    status: AiVisibilityStatus
    error: Optional[str] = None
    probes: list[AiQueryResult] = Field(default_factory=list)
    report: Optional[AiVisibilityReport] = None


class AiVisibilityRequest(BaseModel):
    targetDomain: str = Field(min_length=3, max_length=255)
    targetName: Optional[str] = Field(default=None, max_length=120)
    queries: list[str] = Field(min_length=1, max_length=10)


# --- Bulk Audit -------------------------------------------------------------

BulkAuditStatus = Literal["pending", "running", "done", "failed"]


class BulkAuditItem(BaseModel):
    url: str
    auditId: Optional[str] = None
    label: Optional[str] = None  # optional friendly name from the CSV


class BulkAudit(BaseModel):
    id: str
    createdAt: str
    status: BulkAuditStatus
    items: list[BulkAuditItem]
    error: Optional[str] = None


class BulkAuditRequest(BaseModel):
    urls: list[HttpUrl] = Field(min_length=1, max_length=50)
    labels: Optional[list[str]] = None


# --- Sitemap Watcher --------------------------------------------------------


class SitemapDiff(BaseModel):
    domain: str
    sitemapUrl: str
    fetchedAt: str
    previousFetchedAt: Optional[str] = None
    currentCount: int
    previousCount: int = 0
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    unchanged: int = 0


class SitemapWatch(BaseModel):
    id: str            # md5(domain) — stable per site
    domain: str
    sitemapUrl: str
    createdAt: str
    updatedAt: str
    snapshotUrls: list[str] = Field(default_factory=list)
    lastDiff: Optional[SitemapDiff] = None


class SitemapWatchRequest(BaseModel):
    url: HttpUrl


# --- Performance Monitor ----------------------------------------------------


class PerfMonitor(BaseModel):
    id: str
    url: str
    strategy: str  # "mobile" | "desktop"
    createdAt: str
    updatedAt: str
    history: list[PerformanceSnapshot] = Field(default_factory=list)


class PerfMonitorRequest(BaseModel):
    url: HttpUrl
    strategy: str = "mobile"


# --- SEO Tracker ------------------------------------------------------------


class KeywordReading(BaseModel):
    """One position check for one keyword at a point in time."""

    keyword: str
    checkedAt: str
    position: Optional[int] = None     # 1..100, None when not in top 100
    url: Optional[str] = None          # URL that ranked, when found
    engine: str = "duckduckgo"


class TrackedKeyword(BaseModel):
    keyword: str
    history: list[KeywordReading] = Field(default_factory=list)


class SeoCampaign(BaseModel):
    id: str
    domain: str
    locale: str = "fr-FR"
    createdAt: str
    updatedAt: str
    keywords: list[TrackedKeyword] = Field(default_factory=list)


class SeoCampaignRequest(BaseModel):
    domain: str = Field(min_length=3, max_length=255)
    keywords: list[str] = Field(min_length=1, max_length=50)
    locale: str = Field(default="fr-FR", min_length=2, max_length=10)


class SeoCampaignAddKeywordsRequest(BaseModel):
    keywords: list[str] = Field(min_length=1, max_length=20)
