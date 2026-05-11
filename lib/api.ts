import type {
  AgencyBranding,
  AiVisibilityCheck,
  AuditJobDetail,
  AuditJobSummary,
  BulkAudit,
  CompetitorBattle,
  ContentBrief,
  DriftReport,
  PerfMonitor,
  SeoCampaign,
  SitemapWatch,
} from './types'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

const DEFAULT_TIMEOUT_MS = 30000
const AUTH_STORAGE_KEY = 'audit-bureau:password'

export function setStoredPassword(pw: string | null): void {
  if (typeof window === 'undefined') return
  if (pw) window.localStorage.setItem(AUTH_STORAGE_KEY, pw)
  else window.localStorage.removeItem(AUTH_STORAGE_KEY)
}

export function getStoredPassword(): string | null {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(AUTH_STORAGE_KEY)
}

function authHeader(): Record<string, string> {
  const pw = getStoredPassword()
  if (!pw) return {}
  // username fixed to "admin", password matches APP_PASSWORD on the API.
  const token = typeof window !== 'undefined'
    ? window.btoa(`admin:${pw}`)
    : Buffer.from(`admin:${pw}`).toString('base64')
  return { Authorization: `Basic ${token}` }
}

export class AuthRequiredError extends Error {
  constructor(message = 'Authentification requise.') {
    super(message)
    this.name = 'AuthRequiredError'
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const headers = {
      ...authHeader(),
      ...((init.headers as Record<string, string>) ?? {}),
    }
    const res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers,
      signal: controller.signal,
      cache: 'no-store',
    })
    if (res.status === 401) {
      // Clear bad creds so the login screen reappears.
      setStoredPassword(null)
      if (typeof window !== 'undefined') {
        // Soft reload to bounce the user back to the login gate.
        window.dispatchEvent(new Event('audit-bureau:auth-required'))
      }
      throw new AuthRequiredError()
    }
    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`
      try {
        const body = (await res.json()) as { detail?: string }
        if (body?.detail) detail = body.detail
      } catch {
        try {
          const text = await res.text()
          if (text) detail = text.slice(0, 500)
        } catch {
          /* keep the status fallback */
        }
      }
      throw new Error(detail)
    }
    if (res.status === 204) {
      return undefined as unknown as T
    }
    return (await res.json()) as T
  } catch (err) {
    if ((err as Error).name === 'AbortError') {
      throw new Error(
        'La requête a dépassé le délai. Le serveur est peut-être saturé ou indisponible.',
      )
    }
    throw err
  } finally {
    clearTimeout(timer)
  }
}

// --- Auth ------------------------------------------------------------------

export async function fetchAuthStatus(): Promise<{ required: boolean }> {
  return request<{ required: boolean }>('/auth/status')
}

export interface HealthInfo {
  status: string
  provider?: string
  model?: string
  persistentStorage?: boolean
}

export async function fetchHealth(): Promise<HealthInfo> {
  const res = await fetch(`${BASE_URL}/health`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`health ${res.status}`)
  return (await res.json()) as HealthInfo
}

export async function verifyPassword(password: string): Promise<boolean> {
  const token = typeof window !== 'undefined'
    ? window.btoa(`admin:${password}`)
    : Buffer.from(`admin:${password}`).toString('base64')
  try {
    const res = await fetch(`${BASE_URL}/auth/verify`, {
      headers: { Authorization: `Basic ${token}` },
      cache: 'no-store',
    })
    return res.status === 200
  } catch {
    return false
  }
}

export async function runAudit(
  url: string,
  maxPages = 50,
): Promise<AuditJobSummary> {
  return request<AuditJobSummary>('/audit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, maxPages }),
  })
}

export async function getAudit(id: string): Promise<AuditJobDetail> {
  return request<AuditJobDetail>(`/audit/${encodeURIComponent(id)}`)
}

export interface AuditLogLine {
  t: number
  msg: string
}

export async function getAuditLogs(id: string): Promise<AuditLogLine[]> {
  const res = await request<{ lines: AuditLogLine[] }>(
    `/audit/${encodeURIComponent(id)}/logs`,
  )
  return res.lines ?? []
}

export async function listRecent(includeArchived = false): Promise<AuditJobSummary[]> {
  const qs = includeArchived ? '?includeArchived=true' : ''
  return request<AuditJobSummary[]>(`/audit/recent${qs}`)
}

export async function listArchived(): Promise<AuditJobSummary[]> {
  return request<AuditJobSummary[]>('/audit/archived')
}

export async function setArchived(
  id: string,
  archived: boolean,
): Promise<AuditJobSummary> {
  return request<AuditJobSummary>(`/audit/${encodeURIComponent(id)}/archive`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ archived }),
  })
}

export async function deleteAudit(id: string): Promise<void> {
  await request<void>(`/audit/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export async function listByDomain(domain: string): Promise<AuditJobSummary[]> {
  return request<AuditJobSummary[]>(
    `/audit/by-domain?domain=${encodeURIComponent(domain)}`,
  )
}

export async function compareAudits(
  currentId: string,
  againstId?: string,
): Promise<DriftReport> {
  const qs = againstId ? `?against=${encodeURIComponent(againstId)}` : ''
  return request<DriftReport>(
    `/audit/${encodeURIComponent(currentId)}/compare${qs}`,
  )
}

export function pdfUrl(id: string, agency?: string): string {
  const qs = agency ? `?agency=${encodeURIComponent(agency)}` : ''
  return `${BASE_URL}/audit/${encodeURIComponent(id)}/pdf${qs}`
}

export function xlsxUrl(id: string): string {
  return `${BASE_URL}/audit/${encodeURIComponent(id)}/xlsx`
}

export function markdownUrl(id: string, agency?: string): string {
  const qs = agency ? `?agency=${encodeURIComponent(agency)}` : ''
  return `${BASE_URL}/audit/${encodeURIComponent(id)}/markdown${qs}`
}

// --- Branding / agency settings ---------------------------------------------

export async function getBranding(): Promise<AgencyBranding> {
  return request<AgencyBranding>('/settings/branding')
}

export async function updateBranding(
  patch: AgencyBranding,
): Promise<AgencyBranding> {
  return request<AgencyBranding>('/settings/branding', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
}

export async function uploadBrandingLogo(
  file: File,
): Promise<AgencyBranding> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE_URL}/settings/branding/logo`, {
    method: 'POST',
    body: form,
    cache: 'no-store',
  })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = (await res.json()) as { detail?: string }
      if (body?.detail) detail = body.detail
    } catch {
      /* noop */
    }
    throw new Error(detail)
  }
  return (await res.json()) as AgencyBranding
}

export async function deleteBrandingLogo(): Promise<AgencyBranding> {
  return request<AgencyBranding>('/settings/branding/logo', { method: 'DELETE' })
}

export function brandingLogoUrl(cacheBust?: string): string {
  // Support server-returned logoUrl (relative "/settings/branding/logo?v=…").
  const qs = cacheBust ? `?v=${encodeURIComponent(cacheBust)}` : ''
  return `${BASE_URL}/settings/branding/logo${qs}`
}

// --- Competitor Watch -------------------------------------------------------

export async function startCompetitorBattle(
  targetUrl: string,
  competitors: string[],
): Promise<CompetitorBattle> {
  return request<CompetitorBattle>('/competitor', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ targetUrl, competitors }),
  })
}

export async function listCompetitorBattles(): Promise<CompetitorBattle[]> {
  return request<CompetitorBattle[]>('/competitor')
}

export async function getCompetitorBattle(
  id: string,
): Promise<CompetitorBattle> {
  return request<CompetitorBattle>(`/competitor/${encodeURIComponent(id)}`)
}

export async function deleteCompetitorBattle(id: string): Promise<void> {
  await request<void>(`/competitor/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

// --- Content Brief ---------------------------------------------------------

export async function startContentBrief(
  query: string,
  locale = 'fr-FR',
): Promise<ContentBrief> {
  return request<ContentBrief>('/content-brief', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, locale }),
  })
}

export async function listContentBriefs(): Promise<ContentBrief[]> {
  return request<ContentBrief[]>('/content-brief')
}

export async function getContentBrief(id: string): Promise<ContentBrief> {
  return request<ContentBrief>(`/content-brief/${encodeURIComponent(id)}`)
}

export async function deleteContentBrief(id: string): Promise<void> {
  await request<void>(`/content-brief/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  })
}

// --- llms.txt generator -----------------------------------------------------

export interface LlmsTxtResult {
  domain: string
  content: string
}

export async function generateLlmsTxt(url: string): Promise<LlmsTxtResult> {
  return request<LlmsTxtResult>(
    '/llms-txt',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    },
    120000,
  )
}

// --- Bulk Audit ------------------------------------------------------------

export async function startBulkAudit(
  urls: string[],
  labels?: string[],
): Promise<BulkAudit> {
  return request<BulkAudit>('/bulk', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ urls, labels }),
  })
}

export async function listBulks(): Promise<BulkAudit[]> {
  return request<BulkAudit[]>('/bulk')
}

export async function getBulk(id: string): Promise<BulkAudit> {
  return request<BulkAudit>(`/bulk/${encodeURIComponent(id)}`)
}

export async function deleteBulk(id: string): Promise<void> {
  await request<void>(`/bulk/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export function bulkCsvUrl(id: string): string {
  return `${BASE_URL}/bulk/${encodeURIComponent(id)}/csv`
}

// --- Sitemap watcher -------------------------------------------------------

export async function watchSitemap(url: string): Promise<SitemapWatch> {
  return request<SitemapWatch>(
    '/sitemap-watcher',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    },
    120000,
  )
}

export async function listSitemapWatches(): Promise<SitemapWatch[]> {
  return request<SitemapWatch[]>('/sitemap-watcher')
}

export async function getSitemapWatch(id: string): Promise<SitemapWatch> {
  return request<SitemapWatch>(`/sitemap-watcher/${encodeURIComponent(id)}`)
}

export async function refreshSitemapWatch(id: string): Promise<SitemapWatch> {
  return request<SitemapWatch>(
    `/sitemap-watcher/${encodeURIComponent(id)}/refresh`,
    { method: 'POST' },
    120000,
  )
}

export async function deleteSitemapWatch(id: string): Promise<void> {
  await request<void>(`/sitemap-watcher/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  })
}

// --- Performance Monitor ---------------------------------------------------

export async function watchPerf(
  url: string,
  strategy: 'mobile' | 'desktop' = 'mobile',
): Promise<PerfMonitor> {
  return request<PerfMonitor>(
    '/perf-monitor',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, strategy }),
    },
    120000,
  )
}

export async function listPerfMonitors(): Promise<PerfMonitor[]> {
  return request<PerfMonitor[]>('/perf-monitor')
}

export async function refreshPerfMonitor(id: string): Promise<PerfMonitor> {
  return request<PerfMonitor>(
    `/perf-monitor/${encodeURIComponent(id)}/refresh`,
    { method: 'POST' },
    120000,
  )
}

export async function deletePerfMonitor(id: string): Promise<void> {
  await request<void>(`/perf-monitor/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  })
}

// --- SEO Tracker -----------------------------------------------------------

export async function createSeoCampaign(
  domain: string,
  keywords: string[],
  locale = 'fr-FR',
): Promise<SeoCampaign> {
  return request<SeoCampaign>('/seo-tracker', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ domain, keywords, locale }),
  })
}

export async function listSeoCampaigns(): Promise<SeoCampaign[]> {
  return request<SeoCampaign[]>('/seo-tracker')
}

export async function runSeoCheck(id: string): Promise<SeoCampaign> {
  return request<SeoCampaign>(
    `/seo-tracker/${encodeURIComponent(id)}/check`,
    { method: 'POST' },
    180000,
  )
}

export async function addSeoKeywords(
  id: string,
  keywords: string[],
): Promise<SeoCampaign> {
  return request<SeoCampaign>(`/seo-tracker/${encodeURIComponent(id)}/keywords`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keywords }),
  })
}

export async function deleteSeoCampaign(id: string): Promise<void> {
  await request<void>(`/seo-tracker/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  })
}

// --- AI Search Visibility --------------------------------------------------

export async function startAiVisibilityCheck(
  targetDomain: string,
  queries: string[],
  targetName?: string,
): Promise<AiVisibilityCheck> {
  return request<AiVisibilityCheck>('/ai-visibility', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ targetDomain, targetName, queries }),
  })
}

export async function listAiVisibilityChecks(): Promise<AiVisibilityCheck[]> {
  return request<AiVisibilityCheck[]>('/ai-visibility')
}

export async function getAiVisibilityCheck(
  id: string,
): Promise<AiVisibilityCheck> {
  return request<AiVisibilityCheck>(`/ai-visibility/${encodeURIComponent(id)}`)
}

export async function deleteAiVisibilityCheck(id: string): Promise<void> {
  await request<void>(`/ai-visibility/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  })
}
