'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import {
  AuthRequiredError,
  createProspectSheet,
  deleteProspect,
  listProspects,
} from '@/lib/api'
import type { ProspectSheet, ProspectStatus } from '@/lib/types'
import { usePolling } from '@/lib/usePolling'

export function ProspectTool() {
  const { data, refresh } = usePolling(() => listProspects(), true, 4000)
  const sheets = data ?? []

  return (
    <div className="max-w-5xl mx-auto px-8 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-text-primary mb-1">
          Fiche prospect
        </h1>
        <p className="text-sm text-text-secondary max-w-2xl">
          Saisissez l&apos;URL du site d&apos;une entreprise : on identifie qui
          elle est, on détecte sa stack technique (CMS, analytics, pixels,
          chat/CRM, hébergeur) et on propose un persona décideur avec des angles
          d&apos;approche personnalisés pour préparer le RDV.
        </p>
      </div>

      <section className="mb-10">
        <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md p-5">
          <ProspectForm />
        </div>
      </section>

      <section>
        <div className="flex items-end justify-between mb-4">
          <div>
            <h2 className="text-base font-semibold text-text-primary">
              Fiches précédentes
            </h2>
            <p className="text-xs text-text-tertiary mt-0.5">
              {sheets.length} fiche{sheets.length > 1 ? 's' : ''} enregistrée
              {sheets.length > 1 ? 's' : ''}
            </p>
          </div>
        </div>
        <ProspectTable sheets={sheets} onChange={refresh} />
      </section>
    </div>
  )
}

function ProspectForm() {
  const router = useRouter()
  const [url, setUrl] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function normalize(raw: string): string {
    const trimmed = raw.trim()
    if (!trimmed) return ''
    if (/^https?:\/\//i.test(trimmed)) return trimmed
    return `https://${trimmed}`
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    const target = normalize(url)
    if (submitting || !target) return
    setSubmitting(true)
    setError(null)
    try {
      const sheet = await createProspectSheet(target)
      router.push(`/prospect/${sheet.id}`)
    } catch (e) {
      if (e instanceof AuthRequiredError) return
      setError((e as Error).message)
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3">
      <label className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary">
        URL du site de l&apos;entreprise
      </label>
      <div className="flex flex-col sm:flex-row gap-2">
        <input
          type="text"
          required
          disabled={submitting}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://exemple-entreprise.fr"
          className="flex-1 h-10 px-3 bg-bg-surface border border-[var(--border-default)] rounded-md text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-primary focus:ring-2 focus:ring-[var(--primary-dim)] disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={submitting || !url.trim()}
          className="h-10 px-5 bg-primary hover:bg-primary-hover text-white rounded-md font-medium text-sm transition-colors disabled:opacity-60"
        >
          {submitting ? 'Création…' : 'Générer la fiche'}
        </button>
      </div>
      {error && (
        <p className="text-xs text-[var(--status-critical-text)]">{error}</p>
      )}
      <p className="text-xs text-text-tertiary">
        L&apos;analyse du site + la synthèse IA prennent environ 30 à 90 s. Vous
        pouvez quitter la page.
      </p>
    </form>
  )
}

function ProspectTable({
  sheets,
  onChange,
}: {
  sheets: ProspectSheet[]
  onChange: () => void
}) {
  async function remove(id: string) {
    try {
      await deleteProspect(id)
      onChange()
    } catch {
      /* swallow */
    }
  }

  if (sheets.length === 0) {
    return (
      <div className="border border-dashed border-[var(--border-default)] rounded-md p-10 text-center bg-bg-surface">
        <p className="text-sm text-text-tertiary">
          Aucune fiche prospect générée pour le moment.
        </p>
      </div>
    )
  }
  return (
    <div className="border border-[var(--border-subtle)] rounded-md overflow-hidden bg-bg-surface">
      <div className="grid grid-cols-[1.7fr_90px_140px_60px] bg-bg-elevated border-b border-[var(--border-subtle)]">
        {['Entreprise / domaine', 'Statut', 'Date', ''].map((h, i) => (
          <div
            key={i}
            className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary px-4 py-2.5"
          >
            {h}
          </div>
        ))}
      </div>
      {sheets.map((s) => {
        const label = s.identity?.name?.trim() || s.domain
        return (
          <div
            key={s.id}
            className="grid grid-cols-[1.7fr_90px_140px_60px] border-b border-[var(--border-subtle)] last:border-0 items-center hover:bg-bg-elevated transition-colors"
          >
            <Link
              href={`/prospect/${s.id}`}
              className="px-4 py-3 min-w-0 truncate"
            >
              <span className="text-sm font-medium text-text-primary">
                {label}
              </span>
              {s.identity?.name && (
                <span className="block font-mono text-[11px] text-text-tertiary truncate">
                  {s.domain}
                </span>
              )}
            </Link>
            <Link href={`/prospect/${s.id}`} className="px-4 py-3">
              <StatusPill status={s.status} />
            </Link>
            <Link
              href={`/prospect/${s.id}`}
              className="px-4 py-3 font-mono text-[11px] text-text-tertiary"
            >
              {s.createdAt.slice(0, 16).replace('T', ' ')}
            </Link>
            <div className="px-4 py-3">
              <button
                onClick={() => remove(s.id)}
                title="Supprimer"
                className="w-7 h-7 flex items-center justify-center rounded-md text-text-tertiary hover:text-[var(--status-critical-text)] hover:bg-[var(--status-critical-bg)] transition-colors"
              >
                ✕
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function StatusPill({ status }: { status: ProspectStatus }) {
  const map = {
    pending: { label: 'En file', cls: 'info' },
    running: { label: 'En cours', cls: 'warning' },
    done: { label: 'Prête', cls: 'ok' },
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
