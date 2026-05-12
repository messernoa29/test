export type AuditSection =
  | 'security'
  | 'seo'
  | 'ux'
  | 'content'
  | 'performance'
  | 'business'

export type Severity = 'critical' | 'warning' | 'info' | 'ok' | 'missing'
export type Impact = 'high' | 'medium' | 'low'
export type Effort = 'quick' | 'medium' | 'heavy'

export interface Finding {
  severity: Severity
  title: string
  description: string
  recommendation?: string
  actions?: string[]
  impact?: Impact
  effort?: Effort
  evidence?: string
  reference?: string
}

export interface SectionResult {
  section: AuditSection
  title: string
  score: number
  verdict: string
  findings: Finding[]
}

export interface PageTechnical {
  statusCode: number | null
  depth: number | null
  htmlBytes: number
  wordCount: number
  textRatio: number
  canonical: string | null
  canonicalIsSelf: boolean | null
  robotsMeta: string
  htmlLang: string
  hreflangLangs: string[]
  internalLinksOut: number
  externalLinksOut: number
  imagesCount: number
  imagesWithoutAlt: number
  hasViewportMeta: boolean
  hasMixedContent: boolean
  ogTitle: string | null
  ogDescription: string | null
  ogImage: string | null
  twitterCard: string | null
  redirectChain: string[]
  schemaTypes: string[]
  issues: string[]
  pageType?: string
  suggestedSchema?: string
  suggestedSchemaType?: string
}

export interface PageAnalysis {
  url: string
  status: 'critical' | 'warning' | 'improve' | 'ok'
  title: string
  titleLength: number
  h1: string
  metaDescription: string | null
  metaLength: number
  targetKeywords: string[]
  presentKeywords: string[]
  missingKeywords: string[]
  findings: Finding[]
  recommendation?: PageRecommendation
  technical?: PageTechnical
  /** When this page represents a template group: how many *other* URLs share it. */
  representsCount?: number
  representsPattern?: string
  representsSampleUrls?: string[]
}

export interface PageRecommendation {
  urlCurrent?: string
  titleCurrent?: string
  h1Current?: string
  metaCurrent?: string
  url?: string
  title?: string
  h1?: string
  meta?: string
  actions?: string[]
  estimatedMonthlyTraffic?: number
}

export interface MissingPage {
  url: string
  reason: string
  estimatedSearchVolume?: number
  priority: 'high' | 'medium' | 'low'
}

export interface InternalLink {
  target: string
  anchorText: string
  rel: string
}

export interface LinkGraphPageStat {
  url: string
  inDegree: number
  outDegree: number
}

export interface DeadInternalLink {
  target: string
  statusCode: number | null
  sourceCount: number
}

export interface LinkGraphSummary {
  totalEdges: number
  pages: LinkGraphPageStat[]
  orphanPages: string[]
  hubPages: string[]
  topAnchorTexts: string[]
  deadLinks: DeadInternalLink[]
}

export interface DuplicatePair {
  urlA: string
  urlB: string
  similarity: number
  kind: 'exact' | 'near'
}

export interface RedirectChain {
  requestUrl: string
  finalUrl: string
  hops: string[]
  hopCount: number
}

export interface CrawlData {
  domain: string
  url: string
  crawledAt: string
  pages: Array<{
    url: string
    title: string
    h1: string
    metaDescription: string | null
    headings: string[]
    textSnippet: string
    renderedWithPlaywright?: boolean
    internalLinks?: InternalLink[]
    internalLinksCount?: number
    contentHash?: string
    wordCount?: number
    finalUrl?: string
    redirectChain?: string[]
    canonical?: string | null
    robotsMeta?: string
    hreflang?: HreflangEntry[]
    htmlLang?: string
    images?: ImageAsset[]
    imagesWithoutAlt?: number
  }>
  linkGraph?: LinkGraphSummary
  duplicates?: DuplicatePair[]
  redirectChains?: RedirectChain[]
}

export interface HreflangEntry {
  lang: string
  href: string
}

export interface ImageAsset {
  src: string
  alt: string | null
  width: number | null
  height: number | null
  loading: string
  fileFormat: string
  isInlineSvg: boolean
}

export interface AuditResult {
  id: string
  domain: string
  url: string
  createdAt: string
  globalScore: number
  globalVerdict: string
  scores: Record<AuditSection, number>
  sections: SectionResult[]
  criticalCount: number
  warningCount: number
  quickWins: string[]
  pages?: PageAnalysis[]
  missingPages?: MissingPage[]
  technicalCrawl?: TechnicalCrawlSummary
  visibilityEstimate?: VisibilityEstimate
  culturalAudit?: CulturalAuditSummary
  geoAudit?: GeoAuditSummary
  programmaticAudit?: ProgrammaticAuditSummary
  sxoAudit?: SxoAuditSummary
  crawlCoverage?: CrawlCoverage
  accessibilityAudit?: AccessibilityAudit
  responsiveAudit?: ResponsiveAudit
}

export interface A11yPageIssue {
  url: string
  score: number
  issues: string[]
}

export interface AccessibilityAudit {
  averageScore: number
  pagesWithoutLang: number
  imagesWithoutAlt: number
  formInputsWithoutLabel: number
  linksGeneric: number
  buttonsAsDiv: number
  pagesWithHeadingIssues: number
  pagesWithPositiveTabindex: number
  pagesWithoutLandmarks: number
  pageScores: A11yPageIssue[]
  llmVerdict: string
  llmTopFixes: string[]
  llmPagesEvaluated: number
}

export interface ResponsivePageIssue {
  url: string
  horizontalScrollAt375: boolean | null
  horizontalScrollAt768: boolean | null
  overflowingElementsAt375: number | null
  smallTouchTargetsAt375: number | null
  issues: string[]
}

export interface ResponsiveAudit {
  pagesWithoutViewport: number
  pagesBlockingZoom: number
  pagesWithMediaQueries: number
  imagesWithSrcsetRatio: number
  renderedPagesTested: number
  pagesWithHorizontalScroll: number
  pageResults: ResponsivePageIssue[]
  summary: string
}

export interface CrawlCoverage {
  requestedMaxPages: number
  discoveredUrlCount: number
  crawledPageCount: number
  detailedPageCount: number
  cappedByLimit: boolean
  cappedBySite: boolean
}

export interface SxoPageVerdict {
  url: string
  keyword: string
  pageType: string
  serpDominantType: string
  match: boolean
  severity: 'ok' | 'info' | 'warning' | 'critical'
  recommendation: string
}

export interface SxoAuditSummary {
  evaluated: number
  mismatches: number
  verdicts: SxoPageVerdict[]
  note: string
}

export interface ProgrammaticGroup {
  pattern: string
  pageCount: number
  sampleUrls: string[]
  uniquenessRatio: number
  boilerplateRatio: number
  avgWordCount: number
  gate: 'PASS' | 'WARNING' | 'HARD_STOP'
  notes: string[]
}

export interface ProgrammaticAuditSummary {
  isProgrammatic: boolean
  groups: ProgrammaticGroup[]
}

export interface GeoPageScore {
  url: string
  score: number
  strengths: string[]
  weaknesses: string[]
}

export interface GeoQueryVerdict {
  query: string
  intent: string
  likelyCited: boolean
  confidence: 'low' | 'medium' | 'high'
  citingEngines: string[]
  reason: string
  competitorsCitedInstead: string[]
  improvement: string
}

export interface GeoAuditSummary {
  averagePageScore: number
  pageScores: GeoPageScore[]
  siteStrengths: string[]
  siteWeaknesses: string[]
  aiCrawlerStatus: Record<string, string>
  hasLlmsTxt: boolean
  queryVerdicts: GeoQueryVerdict[]
  citedCount: number
  queriesTested: number
}

export interface CulturalPageIssue {
  url: string
  locale: string
  issues: string[]
}

export interface CulturalLocaleReport {
  locale: string
  label: string
  pagesCount: number
  pagesWithIssues: number
  expectedNumberFormat: string
  expectedDateFormat: string
  issueExamples: CulturalPageIssue[]
}

export interface CulturalAuditSummary {
  isMultilingual: boolean
  detectedLocales: string[]
  locales: CulturalLocaleReport[]
}

export interface EstimatedKeyword {
  keyword: string
  estimatedMonthlyVolume: number | null
  estimatedPosition: number | null
  rankingUrl: string | null
  intent: string
  note: string
}

export interface KeywordOpportunity {
  keyword: string
  estimatedMonthlyVolume: number | null
  difficulty: string
  suggestedPage: string
  rationale: string
}

export interface VisibilityEstimate {
  disclaimer: string
  estimatedMonthlyOrganicTraffic: number | null
  trafficRange: string
  estimatedRankingKeywordsCount: number | null
  topKeywords: EstimatedKeyword[]
  opportunities: KeywordOpportunity[]
  competitorsLikelyOutranking: string[]
  summary: string
}

export interface TechnicalPageRow {
  url: string
  statusCode: number | null
  contentType: string
  isIndexable: boolean
  indexabilityReason: string
  depth: number | null
  htmlBytes: number
  textBytes: number
  textRatio: number
  titleLength: number
  metaDescLength: number
  h1Count: number
  h2Count: number
  wordCount: number
  internalLinksOut: number
  externalLinksOut: number
  imagesCount: number
  imagesWithoutAlt: number
  issues: string[]
}

export interface TechnicalCrawlSummary {
  pagesCrawled: number
  statusCounts: Record<string, number>
  indexablePages: number
  nonIndexablePages: number
  duplicateTitles: string[][]
  duplicateMetaDescriptions: string[][]
  duplicateH1s: string[][]
  missingTitles: string[]
  missingMetaDescriptions: string[]
  missingH1: string[]
  multipleH1: string[]
  titleTooLong: string[]
  titleTooShort: string[]
  metaTooLong: string[]
  metaTooShort: string[]
  lowTextRatioPages: string[]
  brokenInternalLinks: string[]
  maxDepth: number
  rows: TechnicalPageRow[]
}

export interface AuditRequest {
  url: string
  /** Crawl depth — clamped server-side to 100 / 300 / 1000. */
  maxPages?: number
  /** Site builder — adapts the recommendations. */
  platform?: string
}

export type JobStatus = 'pending' | 'done' | 'failed'

export interface AuditJobSummary {
  id: string
  url: string
  domain: string
  createdAt: string
  status: JobStatus
  error?: string
  archived: boolean
  globalScore?: number
  globalVerdict?: string
  criticalCount?: number
  warningCount?: number
}

export interface AuditJobDetail {
  id: string
  url: string
  domain: string
  createdAt: string
  status: JobStatus
  error?: string
  archived: boolean
  result?: AuditResult
}

// Drift comparison between two audits of the same domain
export type DeltaDirection = 'up' | 'down' | 'stable'

export interface ScoreDelta {
  axis: string
  baseline: number
  current: number
  delta: number
  direction: DeltaDirection
}

export interface DriftFinding {
  severity: Severity
  title: string
  description: string
}

export interface FindingsBucket {
  resolved: DriftFinding[]
  appeared: DriftFinding[]
  persistent: DriftFinding[]
}

export interface AgencyBranding {
  name?: string
  tagline?: string
  website?: string
  accentColor?: string
  logoUrl?: string
  updatedAt?: string
}

// --- Competitor Watch -------------------------------------------------------

export type CompetitorBattleStatus = 'pending' | 'running' | 'done' | 'failed'

export interface CompetitorSite {
  url: string
  auditId?: string
  label?: string
}

export interface CompetitorReport {
  winnersByAxis: Record<string, string>
  keyInsights: string[]
  ourStrengths: string[]
  ourWeaknesses: string[]
  priorityActions: string[]
  verdict?: string
}

export interface CompetitorBattle {
  id: string
  targetUrl: string
  competitors: CompetitorSite[]
  createdAt: string
  status: CompetitorBattleStatus
  error?: string
  report?: CompetitorReport
}

// --- Content Brief ----------------------------------------------------------

export type ContentBriefStatus = 'pending' | 'running' | 'done' | 'failed'

export interface SerpResult {
  rank: number
  url: string
  title: string
  h1?: string
  headings: string[]
  metaDescription?: string
  wordCount?: number
}

export interface ContentBriefOutline {
  title: string
  intent?: string
  bullets: string[]
  targetWords?: number
}

export interface ContentBriefResult {
  summary?: string
  intent?: string
  targetAudience?: string
  suggestedTitle?: string
  suggestedMeta?: string
  h1?: string
  targetWordCount?: number
  primaryKeywords: string[]
  semanticKeywords: string[]
  outline: ContentBriefOutline[]
  faq: string[]
  quickWins: string[]
  notes?: string
}

export interface ContentBrief {
  id: string
  query: string
  locale: string
  createdAt: string
  status: ContentBriefStatus
  error?: string
  serpResults: SerpResult[]
  result?: ContentBriefResult
}

// --- Prospect Sheet ---------------------------------------------------------

export type ProspectStatus = 'pending' | 'running' | 'done' | 'failed'

export type TechConfidence = 'high' | 'medium' | 'low'

export interface DetectedTech {
  category: string
  name: string
  confidence: TechConfidence
  evidence: string
}

export interface ProspectParentContact {
  firstName: string
  lastName: string
  role: string
  source: string
  sourceUrl: string
  sourceUrlOk: boolean | null
}

export interface ProspectParentCompany {
  name: string
  relation: string
  website: string
  location: string
  notes: string
  source: string
  sourceUrl: string
  sourceUrlOk: boolean | null
  contacts: ProspectParentContact[]
}

export interface ProspectCompanyIdentity {
  name: string
  location: string
  sector: string
  estimatedFoundedYear: number | null
  estimatedSize: string
  socialProfiles: string[]
  onlinePresenceNotes: string
  valueProposition: string
  parentCompany: ProspectParentCompany | null
}

export interface ProspectStackByCategory {
  cms: DetectedTech[]
  analytics: DetectedTech[]
  advertising: DetectedTech[]
  chatCrm: DetectedTech[]
  hostingCdn: DetectedTech[]
  other: DetectedTech[]
}

export interface ProspectContact {
  firstName: string
  lastName: string
  role: string
  email: string
  phone: string
  linkedin: string
  note: string
  source: string
  sourceUrl: string
  sourceUrlOk: boolean | null
  otherAffiliations: string[]
  searchLinks: Record<string, string>
  confidence: TechConfidence
}

export interface ProspectPersona {
  likelyContactRoles: string[]
  likelyPriorities: string[]
  approachAngles: string[]
  contacts: ProspectContact[]
  companyEmails: string[]
  companyPhones: string[]
  companyAddress: string
}

export interface ProspectSheet {
  id: string
  url: string
  domain: string
  createdAt: string
  status: ProspectStatus
  error: string | null
  identity: ProspectCompanyIdentity | null
  stack: ProspectStackByCategory | null
  persona: ProspectPersona | null
}

// --- AI Search Visibility ---------------------------------------------------

export type AiVisibilityStatus = 'pending' | 'running' | 'done' | 'failed'

export interface AiCitation {
  url?: string
  title?: string
  snippet?: string
}

export interface AiQueryResult {
  engine: string
  query: string
  answer?: string
  cited: boolean
  targetMentioned: boolean
  citations: AiCitation[]
  error?: string
}

export interface AiVisibilityReport {
  summary?: string
  citationRate: number
  mentionRate: number
  strengths: string[]
  weaknesses: string[]
  actions: string[]
}

export interface AiVisibilityCheck {
  id: string
  targetDomain: string
  targetName?: string
  queries: string[]
  createdAt: string
  status: AiVisibilityStatus
  error?: string
  probes: AiQueryResult[]
  report?: AiVisibilityReport
}

// --- Bulk audit -------------------------------------------------------------

export type BulkAuditStatus = 'pending' | 'running' | 'done' | 'failed'

export interface BulkAuditItem {
  url: string
  auditId?: string
  label?: string
}

export interface BulkAudit {
  id: string
  createdAt: string
  status: BulkAuditStatus
  items: BulkAuditItem[]
  error?: string
}

// --- Sitemap watcher --------------------------------------------------------

export interface SitemapDiff {
  domain: string
  sitemapUrl: string
  fetchedAt: string
  previousFetchedAt?: string
  currentCount: number
  previousCount: number
  added: string[]
  removed: string[]
  unchanged: number
}

export interface SitemapWatch {
  id: string
  domain: string
  sitemapUrl: string
  createdAt: string
  updatedAt: string
  snapshotUrls: string[]
  lastDiff?: SitemapDiff
}

// --- Performance Monitor ---------------------------------------------------

export interface PerformanceMetric {
  name: string
  fieldValue?: number
  fieldPercentile75?: number
  labValue?: number
  rating?: string
  threshold?: string
}

export interface PerformanceSnapshot {
  url: string
  strategy: string
  source: string
  fetchedAt: string
  performanceScore?: number
  metrics: PerformanceMetric[]
  error?: string
}

export interface PerfMonitor {
  id: string
  url: string
  strategy: string
  createdAt: string
  updatedAt: string
  history: PerformanceSnapshot[]
}

// --- SEO Tracker -----------------------------------------------------------

export interface KeywordReading {
  keyword: string
  checkedAt: string
  position?: number | null
  url?: string | null
  engine: string
}

export interface TrackedKeyword {
  keyword: string
  history: KeywordReading[]
}

export interface SeoCampaign {
  id: string
  domain: string
  locale: string
  createdAt: string
  updatedAt: string
  keywords: TrackedKeyword[]
}

export interface FactDelta {
  key: string
  label: string
  baseline: number
  current: number
  delta: number
  direction: 'up' | 'down' | 'stable'
  lowerIsBetter: boolean
}

export interface DriftReport {
  baselineId: string
  baselineDate: string
  currentId: string
  currentDate: string
  domain: string
  globalDelta: ScoreDelta
  axisDeltas: ScoreDelta[]
  perAxisFindings: Record<string, FindingsBucket>
  resolvedCount: number
  appearedCount: number
  persistentCount: number
  factDeltas: FactDelta[]
  factsUnavailable: boolean
}
