'use client'

import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { runAudit } from '@/lib/api'

// Depth = pages fetched for the *technical* crawl (status codes, link graph,
// dups, canonicals…). The IA analyses only a fixed subset of important pages
// in detail (~30), so a bigger crawl mostly affects the technical coverage,
// not the IA cost — but it does take longer.
const DEPTH_OPTIONS = [
  { value: 100, label: '100 pages crawlées — rapide (~3-6 min)' },
  { value: 300, label: '300 pages crawlées — recommandé (~6-12 min)' },
  { value: 1000, label: '1000 pages crawlées — gros sites (~15-30 min)' },
] as const

// Site builder — adapts the recommendations to the tool (where to do each fix).
const PLATFORM_OPTIONS = [
  { value: 'unknown', label: 'Plateforme inconnue' },
  { value: 'custom', label: 'Codé sur mesure' },
  { value: 'wordpress', label: 'WordPress' },
  { value: 'webflow', label: 'Webflow' },
  { value: 'shopify', label: 'Shopify' },
  { value: 'wix', label: 'Wix' },
  { value: 'squarespace', label: 'Squarespace' },
  { value: 'bubble', label: 'Bubble' },
  { value: 'framer', label: 'Framer' },
  { value: 'nextjs', label: 'Next.js / React' },
  { value: 'other', label: 'Autre' },
] as const

export function AuditForm() {
  const router = useRouter()
  const [url, setUrl] = useState('')
  const [maxPages, setMaxPages] = useState<number>(300)
  const [platform, setPlatform] = useState<string>('unknown')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!url || submitting) return
    setError(null)
    setSubmitting(true)
    try {
      const job = await runAudit(url, maxPages, platform)
      router.push(`/audit/${job.id}`)
    } catch (err) {
      setError((err as Error).message || "Impossible de lancer l'audit.")
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-2">
      <div className="flex flex-col sm:flex-row gap-2">
        <input
          type="url"
          name="url"
          required
          disabled={submitting}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://exemple.com"
          className="flex-1 h-10 px-3 bg-bg-surface border border-[var(--border-default)] rounded-md text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-primary focus:ring-2 focus:ring-[var(--primary-dim)] transition text-sm disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={submitting}
          className="h-10 px-5 bg-primary hover:bg-primary-hover text-white rounded-md font-medium text-sm transition-colors disabled:opacity-60"
        >
          {submitting ? 'Création...' : 'Analyser'}
        </button>
      </div>
      <div className="flex flex-col sm:flex-row gap-2">
        <select
          value={maxPages}
          onChange={(e) => setMaxPages(Number(e.target.value))}
          disabled={submitting}
          className="flex-1 h-10 px-3 bg-bg-surface border border-[var(--border-default)] rounded-md text-text-primary text-sm disabled:opacity-60"
          aria-label="Profondeur du crawl"
        >
          {DEPTH_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select
          value={platform}
          onChange={(e) => setPlatform(e.target.value)}
          disabled={submitting}
          className="flex-1 h-10 px-3 bg-bg-surface border border-[var(--border-default)] rounded-md text-text-primary text-sm disabled:opacity-60"
          aria-label="Plateforme du site"
        >
          {PLATFORM_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
      {error && (
        <p className="text-xs text-[var(--status-critical-text)]">{error}</p>
      )}
      <p className="text-xs text-text-tertiary">
        La profondeur fixe le nombre de pages crawlées techniquement ; l&apos;IA
        analyse en détail les ~30 pages les plus importantes. La plateforme
        adapte les actions recommandées (ex. « via Yoast » sur WordPress, « via
        Page Settings → SEO » sur Webflow). Vous pouvez quitter la page,
        l&apos;audit continue côté serveur.
      </p>
    </form>
  )
}
