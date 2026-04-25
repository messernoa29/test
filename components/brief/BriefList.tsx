'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import {
  deleteContentBrief,
  listContentBriefs,
  startContentBrief,
} from '@/lib/api'
import type { ContentBrief, ContentBriefStatus } from '@/lib/types'
import { usePolling } from '@/lib/usePolling'

interface Props {
  initial: ContentBrief[]
}

export function BriefList({ initial }: Props) {
  const hasPending = initial.some(
    (b) => b.status === 'pending' || b.status === 'running',
  )
  const { data } = usePolling(() => listContentBriefs(), hasPending, 4000)
  const briefs = data ?? initial

  return (
    <div className="max-w-5xl mx-auto px-8 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-text-primary mb-1">
          Content Brief
        </h1>
        <p className="text-sm text-text-secondary max-w-2xl">
          Saisissez une requête cible : on inspecte les premiers résultats Google
          puis on produit un brief éditorial structuré (titre, meta, plan H2/H3,
          mots-clés sémantiques, FAQ, quick wins).
        </p>
      </div>

      <section className="mb-10">
        <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md p-5">
          <BriefForm />
        </div>
      </section>

      <section>
        <div className="flex items-end justify-between mb-4">
          <div>
            <h2 className="text-base font-semibold text-text-primary">
              Briefs précédents
            </h2>
            <p className="text-xs text-text-tertiary mt-0.5">
              {briefs.length} brief{briefs.length > 1 ? 's' : ''} enregistré
              {briefs.length > 1 ? 's' : ''}
            </p>
          </div>
        </div>
        <BriefTable briefs={briefs} />
      </section>
    </div>
  )
}

function BriefForm() {
  const router = useRouter()
  const [query, setQuery] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (submitting || !query.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      const brief = await startContentBrief(query.trim())
      router.push(`/content-brief/${brief.id}`)
    } catch (e) {
      setError((e as Error).message)
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3">
      <label className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary">
        Requête cible
      </label>
      <div className="flex flex-col sm:flex-row gap-2">
        <input
          type="text"
          required
          minLength={3}
          maxLength={200}
          disabled={submitting}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder='Ex: "comment choisir son école de cuisine"'
          className="flex-1 h-10 px-3 bg-bg-surface border border-[var(--border-default)] rounded-md text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-primary focus:ring-2 focus:ring-[var(--primary-dim)] disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={submitting || !query.trim()}
          className="h-10 px-5 bg-primary hover:bg-primary-hover text-white rounded-md font-medium text-sm transition-colors disabled:opacity-60"
        >
          {submitting ? 'Création…' : 'Générer le brief'}
        </button>
      </div>
      {error && (
        <p className="text-xs text-[var(--status-critical-text)]">{error}</p>
      )}
      <p className="text-xs text-text-tertiary">
        Le SERP scrape + la synthèse prennent 60 à 120 s. Vous pouvez quitter
        la page.
      </p>
    </form>
  )
}

function BriefTable({ briefs }: { briefs: ContentBrief[] }) {
  const router = useRouter()

  async function remove(id: string) {
    try {
      await deleteContentBrief(id)
      router.refresh()
    } catch {
      /* swallow */
    }
  }

  if (briefs.length === 0) {
    return (
      <div className="border border-dashed border-[var(--border-default)] rounded-md p-10 text-center bg-bg-surface">
        <p className="text-sm text-text-tertiary">
          Aucun brief généré pour le moment.
        </p>
      </div>
    )
  }
  return (
    <div className="border border-[var(--border-subtle)] rounded-md overflow-hidden bg-bg-surface">
      <div className="grid grid-cols-[1.7fr_80px_140px_60px] bg-bg-elevated border-b border-[var(--border-subtle)]">
        {['Requête', 'Statut', 'Date', ''].map((h, i) => (
          <div
            key={i}
            className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary px-4 py-2.5"
          >
            {h}
          </div>
        ))}
      </div>
      {briefs.map((b) => (
        <div
          key={b.id}
          className="grid grid-cols-[1.7fr_80px_140px_60px] border-b border-[var(--border-subtle)] last:border-0 items-center hover:bg-bg-elevated transition-colors"
        >
          <Link
            href={`/content-brief/${b.id}`}
            className="px-4 py-3 min-w-0 text-sm font-medium text-text-primary truncate"
          >
            {b.query}
          </Link>
          <Link href={`/content-brief/${b.id}`} className="px-4 py-3">
            <StatusPill status={b.status} />
          </Link>
          <Link
            href={`/content-brief/${b.id}`}
            className="px-4 py-3 font-mono text-[11px] text-text-tertiary"
          >
            {b.createdAt.slice(0, 16).replace('T', ' ')}
          </Link>
          <div className="px-4 py-3">
            <button
              onClick={() => remove(b.id)}
              title="Supprimer"
              className="w-7 h-7 flex items-center justify-center rounded-md text-text-tertiary hover:text-[var(--status-critical-text)] hover:bg-[var(--status-critical-bg)] transition-colors"
            >
              ✕
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}

function StatusPill({ status }: { status: ContentBriefStatus }) {
  const map = {
    pending: { label: 'En file', cls: 'info' },
    running: { label: 'En cours', cls: 'warning' },
    done: { label: 'Prêt', cls: 'ok' },
    failed: { label: 'Échec', cls: 'critical' },
  }[status]
  const classes = {
    info: 'bg-[var(--status-info-bg)] text-[var(--status-info-text)] border-[var(--status-info-border)]',
    ok: 'bg-[var(--status-ok-bg)] text-[var(--status-ok-text)] border-[var(--status-ok-border)]',
    critical:
      'bg-[var(--status-critical-bg)] text-[var(--status-critical-text)] border-[var(--status-critical-border)]',
    warning:
      'bg-[var(--status-warning-bg)] text-[var(--status-warning-text)] border-[var(--status-warning-border)]',
  }[map.cls]
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded border text-[10px] font-medium uppercase tracking-wider ${classes}`}
    >
      {status === 'running' && (
        <span
          className="w-1.5 h-1.5 rounded-full bg-current"
          style={{ animation: 'pulse-critical 1.5s ease-in-out infinite' }}
        />
      )}
      {map.label}
    </span>
  )
}
