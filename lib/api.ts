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
  ProspectSheet,
  SeoCampaign,
  SitemapWatch,
} from './types'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

const DEFAULT_TIMEOUT_MS = 30000
// We store an opaque session token, never the raw password. Old key kept so
// a stale plaintext password is cleaned up on first load.
const TOKEN_STORAGE_KEY = 'audit-bureau:token'
const LEGACY_PW_KEY = 'audit-bureau:password'

function getStoredToken(): string | null {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(TOKEN_STORAGE_KEY)
}

function setStoredToken(token: string | null): void {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(LEGACY_PW_KEY) // scrub any old plaintext
  if (token) window.localStorage.setItem(TOKEN_STORAGE_KEY, token)
  else window.localStorage.removeItem(TOKEN_STORAGE_KEY)
}

/**
 * @deprecated kept for AuthGate compatibility — clears the session.
 * Passing a password no longer stores it; use verifyPassword() to log in.
 */
export function setStoredPassword(pw: string | null): void {
  if (!pw) setStoredToken(null)
  // a non-null pw is ignored here on purpose — login goes through
  // verifyPassword() which exchanges it for a token.
}

/** True if we currently hold a session token. */
export function getStoredPassword(): string | null {
  return getStoredToken()
}

function authHeader(): Record<string, string> {
  const token = getStoredToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
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

/**
 * Log in: exchange the password for an opaque session token (stored in
 * localStorage). Returns true on success. If `password` is empty we treat it
 * as "re-validate the stored token" — used on app load.
 */
export async function verifyPassword(password: string): Promise<boolean> {
  // Re-validation path: we already have a token, just check it's still good.
  if (!password) {
    const tok = getStoredToken()
    if (!tok) return false
    try {
      const res = await fetch(`${BASE_URL}/auth/verify`, {
        headers: { Authorization: `Bearer ${tok}` },
        cache: 'no-store',
      })
      if (res.status === 200) return true
      setStoredToken(null)
      return false
    } catch {
      return false
    }
  }
  // Login path: trade the password for a token.
  try {
    const res = await fetch(`${BASE_URL}/auth/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
      cache: 'no-store',
    })
    if (res.status !== 200) return false
    const data = (await res.json()) as { token?: string }
    if (!data.token) return false
    setStoredToken(data.token)
    return true
  } catch {
    return false
  }
}

/** Revoke the current session token (best-effort) and clear it locally. */
export async function logout(): Promise<void> {
  const tok = getStoredToken()
  setStoredToken(null)
  if (!tok) return
  try {
    await fetch(`${BASE_URL}/auth/logout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: tok }),
      cache: 'no-store',
    })
  } catch {
    /* best-effort */
  }
}

export async function runAudit(
  url: string,
  maxPages = 300,
  platform = 'unknown',
): Promise<AuditJobSummary> {
  return request<AuditJobSummary>('/audit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, maxPages, platform }),
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

// --- Prospect Sheet --------------------------------------------------------

export async function createProspectSheet(url: string): Promise<ProspectSheet> {
  return request<ProspectSheet>('/prospect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })
}

export async function listProspects(): Promise<ProspectSheet[]> {
  return request<ProspectSheet[]>('/prospect')
}

export async function getProspect(id: string): Promise<ProspectSheet> {
  return request<ProspectSheet>(`/prospect/${encodeURIComponent(id)}`)
}

export async function deleteProspect(id: string): Promise<void> {
  await request<void>(`/prospect/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  })
}

export function prospectPdfUrl(id: string): string {
  return `${BASE_URL}/prospect/${encodeURIComponent(id)}/pdf`
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
