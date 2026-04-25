'use client'

import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { runAudit } from '@/lib/api'

export function AuditForm() {
  const router = useRouter()
  const [url, setUrl] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!url || submitting) return
    setError(null)
    setSubmitting(true)
    try {
      const job = await runAudit(url)
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
      {error && (
        <p className="text-xs text-[var(--status-critical-text)]">{error}</p>
      )}
      <p className="text-xs text-text-tertiary">
        L&apos;analyse dure 40 à 90 s. Vous pouvez quitter la page, elle continuera
        côté serveur.
      </p>
    </form>
  )
}
