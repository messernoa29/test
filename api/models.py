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
    # Detected page type ("article" | "product" | "localBusiness" | "faq" |
    # "service" | "homepage" | "contact" | "other") — informs schema + SXO.
    pageType: str = ""
    # Ready-to-paste JSON-LD the page is missing (empty if nothing useful to add).
    suggestedSchema: str = ""
    suggestedSchemaType: str = ""


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
    # When this page is a representative of a template group (e.g. one of
    # 200 near-identical blog posts), how many other URLs share its template
    # and a few example URLs. The analysis applies to all of them.
    representsCount: int = 0
    representsPattern: str = ""
    representsSampleUrls: list[str] = Field(default_factory=list)

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
    # CTA-looking anchor/button texts (for cultural-adaptation audit).
    ctaTexts: list[str] = Field(default_factory=list)
    # Static accessibility signals (computed in the crawler from the HTML).
    a11y: Optional["PageA11y"] = None
    # Static responsive signals (computed in the crawler from HTML/CSS).
    responsive: Optional["PageResponsive"] = None


class PageA11y(BaseModel):
    """WCAG signals detectable from static HTML (no rendering)."""

    htmlHasLang: bool = False
    imagesTotal: int = 0
    imagesWithoutAlt: int = 0
    imagesAltEmpty: int = 0           # alt="" — fine for decorative, flagged en masse
    formInputsTotal: int = 0
    formInputsWithoutLabel: int = 0   # no <label for>, aria-label, aria-labelledby, title
    buttonsAsDiv: int = 0             # <div onclick> / role=button without keyboard handling
    linksEmpty: int = 0               # <a> with no text and no aria-label
    linksGeneric: int = 0             # "cliquez ici", "en savoir plus", "lire la suite"…
    h1Count: int = 0
    headingOrderIssues: int = 0       # skipped levels (h1 → h3) etc.
    positiveTabindex: int = 0         # tabindex > 0 — breaks tab order
    iframeWithoutTitle: int = 0
    skipLinkPresent: bool = False     # "skip to content" link near the top
    landmarksPresent: bool = False    # <main> / role=main present
    ariaInvalidCount: int = 0         # obviously broken aria-* (e.g. aria-hidden=foo)
    issues: list[str] = Field(default_factory=list)  # short labels


class PageResponsive(BaseModel):
    """Responsive signals — static now, enriched by Playwright at 3 widths."""

    hasViewportMeta: bool = False
    viewportContent: str = ""         # raw content of <meta name=viewport>
    viewportBlocksZoom: bool = False  # maximum-scale=1 / user-scalable=no
    cssMediaQueries: int = 0          # count of @media rules in inline/linked CSS we saw
    imagesWithSrcset: int = 0
    imagesTotal: int = 0
    fixedPxFontDecls: int = 0         # font-size: Npx in inline styles
    largeFixedWidthDecls: int = 0     # width: Npx with N > 768 in inline styles
    # Filled by the Playwright pass (None until then):
    horizontalScrollAt375: Optional[bool] = None
    horizontalScrollAt768: Optional[bool] = None
    overflowingElementsAt375: Optional[int] = None
    smallTouchTargetsAt375: Optional[int] = None  # interactive elements < 44x44 CSS px
    issues: list[str] = Field(default_factory=list)


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
    # Raw /robots.txt content (empty if absent/unreachable).
    robotsTxt: str = ""
    # Whether /llms.txt exists.
    hasLlmsTxt: bool = False
    # Crawl coverage: how many pages the user asked for, how many distinct URLs
    # were discovered (sitemap + links), and how many were actually fetched OK.
    requestedMaxPages: int = 0
    discoveredUrlCount: int = 0
    crawledPageCount: int = 0


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


class GeoPageScore(BaseModel):
    url: str
    score: int = 0  # 0-100 citability
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)


class GeoQueryVerdict(BaseModel):
    """One plausible search query and whether the site would likely be cited
    by AI assistants on it."""

    query: str
    intent: str = ""  # "informational" | "transactional" | "local" | "navigational"
    likelyCited: bool = False
    confidence: str = "low"  # "low" | "medium" | "high"
    citingEngines: list[str] = Field(default_factory=list)  # e.g. ["Google AI Overviews", "Perplexity"]
    reason: str = ""             # why cited / why not
    competitorsCitedInstead: list[str] = Field(default_factory=list)
    improvement: str = ""        # one concrete action to get cited


class GeoAuditSummary(BaseModel):
    """GEO (AI-citability) audit. Page scores + site-level robots/llms.txt +
    a real "would AI cite this site?" test on plausible intent queries."""

    averagePageScore: int = 0
    pageScores: list[GeoPageScore] = Field(default_factory=list)
    siteStrengths: list[str] = Field(default_factory=list)
    siteWeaknesses: list[str] = Field(default_factory=list)
    aiCrawlerStatus: dict[str, str] = Field(default_factory=dict)  # UA -> status
    hasLlmsTxt: bool = False
    # LLM-based citation test (optional, best-effort).
    queryVerdicts: list[GeoQueryVerdict] = Field(default_factory=list)
    citedCount: int = 0       # how many of the tested queries the site would likely be cited on
    queriesTested: int = 0


class SxoPageVerdict(BaseModel):
    url: str
    keyword: str = ""  # the query we evaluated for this page
    pageType: str = ""  # our classification of the page
    serpDominantType: str = ""  # type Google mostly ranks for this query
    match: bool = True  # pageType compatible with serpDominantType?
    severity: str = "ok"  # "ok" | "info" | "warning" | "critical"
    recommendation: str = ""


class SxoAuditSummary(BaseModel):
    """Search Experience Optimization — page-type vs SERP-intent mismatch."""

    evaluated: int = 0
    mismatches: int = 0
    verdicts: list[SxoPageVerdict] = Field(default_factory=list)
    note: str = (
        "Vérifie que le TYPE de page (fiche produit, comparatif, blog, "
        "service…) correspond à ce que Google récompense pour la requête. "
        "Évaluation IA + recherche web sur un échantillon de pages."
    )


class ProgrammaticGroup(BaseModel):
    pattern: str  # "/services/{}/{}"
    pageCount: int = 0
    sampleUrls: list[str] = Field(default_factory=list)
    uniquenessRatio: float = 0.0  # 0-1, higher = more unique per page
    boilerplateRatio: float = 0.0  # 0-1, shared template content
    avgWordCount: int = 0
    gate: str = "PASS"  # "PASS" | "WARNING" | "HARD_STOP"
    notes: list[str] = Field(default_factory=list)


class ProgrammaticAuditSummary(BaseModel):
    """Quality gates for templated/programmatic page sets."""

    isProgrammatic: bool = False
    groups: list[ProgrammaticGroup] = Field(default_factory=list)


class CulturalPageIssue(BaseModel):
    url: str
    locale: str
    issues: list[str] = Field(default_factory=list)


class CulturalLocaleReport(BaseModel):
    locale: str  # "fr" | "de" | ...
    label: str  # "Francophone" | ...
    pagesCount: int = 0
    pagesWithIssues: int = 0
    expectedNumberFormat: str = ""
    expectedDateFormat: str = ""
    issueExamples: list[CulturalPageIssue] = Field(default_factory=list)


class CulturalAuditSummary(BaseModel):
    """Cultural adaptation audit for multilingual sites. Empty/absent when the
    site appears monolingual."""

    isMultilingual: bool = False
    detectedLocales: list[str] = Field(default_factory=list)
    locales: list[CulturalLocaleReport] = Field(default_factory=list)


class CrawlCoverage(BaseModel):
    """How much of the site the crawl covered vs what was asked, and how many
    pages the LLM analysed in detail."""

    requestedMaxPages: int = 0     # crawl-depth the user picked (100/300/1000)
    discoveredUrlCount: int = 0    # distinct same-origin URLs found
    crawledPageCount: int = 0      # pages fetched for the technical crawl
    detailedPageCount: int = 0     # pages the LLM analysed page-by-page
    cappedByLimit: bool = False    # True if discovery hit the crawl-page limit
    cappedBySite: bool = False     # True if the site simply has fewer pages


class A11yPageIssue(BaseModel):
    url: str
    score: int = 0  # 0-100, higher = more accessible
    issues: list[str] = Field(default_factory=list)


class AccessibilityAudit(BaseModel):
    """WCAG audit — static signals aggregated across pages + an optional LLM
    verdict on a few key pages."""

    averageScore: int = 0
    # Site-wide aggregates (counts over all crawled pages).
    pagesWithoutLang: int = 0
    imagesWithoutAlt: int = 0
    formInputsWithoutLabel: int = 0
    linksGeneric: int = 0
    buttonsAsDiv: int = 0
    pagesWithHeadingIssues: int = 0
    pagesWithPositiveTabindex: int = 0
    pagesWithoutLandmarks: int = 0
    pageScores: list[A11yPageIssue] = Field(default_factory=list)  # worst first
    # LLM verdict on sampled pages (optional, best-effort).
    llmVerdict: str = ""               # 2-4 sentence WCAG summary
    llmTopFixes: list[str] = Field(default_factory=list)  # prioritised fixes
    llmPagesEvaluated: int = 0


class ResponsivePageIssue(BaseModel):
    url: str
    horizontalScrollAt375: Optional[bool] = None
    horizontalScrollAt768: Optional[bool] = None
    overflowingElementsAt375: Optional[int] = None
    smallTouchTargetsAt375: Optional[int] = None
    issues: list[str] = Field(default_factory=list)


class ResponsiveAudit(BaseModel):
    """Responsive / mobile audit — static signals + Playwright rendering at
    375 / 768 / 1280 px on a few key pages."""

    pagesWithoutViewport: int = 0
    pagesBlockingZoom: int = 0
    pagesWithMediaQueries: int = 0     # at least one @media seen
    imagesWithSrcsetRatio: float = 0.0  # over all <img>
    renderedPagesTested: int = 0       # how many pages we actually rendered
    pagesWithHorizontalScroll: int = 0  # at 375 or 768
    pageResults: list[ResponsivePageIssue] = Field(default_factory=list)
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
    # Cultural adaptation audit for multilingual sites (populated by the runner).
    culturalAudit: Optional[CulturalAuditSummary] = None
    # GEO (AI-citability) audit (populated by the runner).
    geoAudit: Optional[GeoAuditSummary] = None
    # Programmatic-SEO quality gates (populated by the runner).
    programmaticAudit: Optional[ProgrammaticAuditSummary] = None
    # SXO page-type-vs-SERP-intent mismatch (LLM + web_search, sampled).
    sxoAudit: Optional[SxoAuditSummary] = None
    # How many pages the crawl actually covered vs the requested depth.
    crawlCoverage: Optional[CrawlCoverage] = None
    # Accessibility (WCAG) audit — populated by the runner.
    accessibilityAudit: Optional[AccessibilityAudit] = None
    # Responsive / mobile audit — populated by the runner.
    responsiveAudit: Optional[ResponsiveAudit] = None
    # Deterministic snapshot of measurable facts (counts), so the drift view
    # can compare what actually changed rather than the LLM's prose. Keys are
    # stable; values are ints. Populated by the runner.
    factsSnapshot: dict[str, int] = Field(default_factory=dict)

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


# Site-building platforms — drives how concrete the LLM's "where to do it"
# instructions are. "custom" = hand-coded, full control. "unknown" = generic.
SitePlatform = Literal[
    "unknown", "custom", "webflow", "wordpress", "shopify", "wix",
    "squarespace", "bubble", "framer", "nextjs", "other",
]


class AuditRequest(BaseModel):
    url: HttpUrl
    # Pages to fetch for the technical crawl (link graph, status codes, dups…).
    # The LLM only analyses a small subset in detail. Clamped to {100,300,1000}.
    maxPages: int = 300
    # Which tool the site was built with — adapts the recommendations.
    platform: SitePlatform = "unknown"

    @field_validator("maxPages", mode="before")
    @classmethod
    def _clamp_max_pages(cls, v: object) -> int:
        try:
            n = int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 300
        if n <= 100:
            return 100
        if n <= 300:
            return 300
        return 1000

    @field_validator("platform", mode="before")
    @classmethod
    def _norm_platform(cls, v: object) -> str:
        s = str(v or "unknown").strip().lower()
        valid = {
            "unknown", "custom", "webflow", "wordpress", "shopify", "wix",
            "squarespace", "bubble", "framer", "nextjs", "other",
        }
        return s if s in valid else "unknown"


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


# --- Prospect Sheet ---------------------------------------------------------

ProspectStatus = Literal["pending", "running", "done", "failed"]


class DetectedTech(BaseModel):
    """A single technology spotted on the prospect's site."""

    category: str
    name: str
    confidence: Literal["high", "medium", "low"] = "medium"
    evidence: str = ""


class ProspectCompanyIdentity(BaseModel):
    """Who the company is — guessed from the site + light web search."""

    name: str = ""
    location: str = ""
    sector: str = ""
    estimatedFoundedYear: Optional[int] = None
    estimatedSize: str = ""  # TPE / PME / ETI / grande entreprise
    socialProfiles: list[str] = Field(default_factory=list)
    onlinePresenceNotes: str = ""
    valueProposition: str = ""


class ProspectStackByCategory(BaseModel):
    """Detected tech stack, grouped by category."""

    cms: list[DetectedTech] = Field(default_factory=list)
    analytics: list[DetectedTech] = Field(default_factory=list)
    advertising: list[DetectedTech] = Field(default_factory=list)
    chatCrm: list[DetectedTech] = Field(default_factory=list)
    hostingCdn: list[DetectedTech] = Field(default_factory=list)
    other: list[DetectedTech] = Field(default_factory=list)


class ProspectPersona(BaseModel):
    """Likely decision-maker + tailored prospecting angles."""

    likelyContactRoles: list[str] = Field(default_factory=list)
    likelyPriorities: list[str] = Field(default_factory=list)
    approachAngles: list[str] = Field(default_factory=list)


class ProspectSheet(BaseModel):
    """A prospecting sheet job — request + status + result."""

    id: str
    url: str
    domain: str
    createdAt: str
    status: ProspectStatus = "pending"
    error: Optional[str] = None
    identity: Optional[ProspectCompanyIdentity] = None
    stack: Optional[ProspectStackByCategory] = None
    persona: Optional[ProspectPersona] = None


class ProspectRequest(BaseModel):
    url: HttpUrl


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
