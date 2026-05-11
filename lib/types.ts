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
  includeSeoDeep?: boolean
  agencyName?: string
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
}
