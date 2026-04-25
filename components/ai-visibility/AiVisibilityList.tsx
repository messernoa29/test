'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import {
  deleteAiVisibilityCheck,
  listAiVisibilityChecks,
  startAiVisibilityCheck,
} from '@/lib/api'
import type { AiVisibilityCheck, AiVisibilityStatus } from '@/lib/types'
import { usePolling } from '@/lib/usePolling'

interface Props {
  initial: AiVisibilityCheck[]
}

export function AiVisibilityList({ initial }: Props) {
  const hasPending = initial.some(
    (c) => c.status === 'pending' || c.status === 'running',
  )
  const { data } = usePolling(
    () => listAiVisibilityChecks(),
    hasPending,
    5000,
  )
  const checks = data ?? initial

  return (
    <div className="max-w-5xl mx-auto px-8 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-text-primary mb-1">
          AI Visibility
        </h1>
        <p className="text-sm text-text-secondary max-w-2xl">
          Vérifie si un site est cité par les moteurs AI (Gemini, ChatGPT
          search) sur ses requêtes cibles. Chaque requête est sondée avec
          recherche web, on extrait les sources citées et on calcule un taux
          de citation et de mention de marque.
        </p>
      </div>

      <section className="mb-10">
        <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md p-5">
          <CheckForm />
        </div>
      </section>

      <section>
        <div className="flex items-end justify-between mb-4">
          <div>
            <h2 className="text-base font-semibold text-text-primary">
              Vérifications précédentes
            </h2>
            <p className="text-xs text-text-tertiary mt-0.5">
              {checks.length} vérification{checks.length > 1 ? 's' : ''} enregistrée
              {checks.length > 1 ? 's' : ''}
            </p>
          </div>
        </div>
        <CheckTable checks={checks} />
      </section>
    </div>
  )
}

function CheckForm() {
  const router = useRouter()
  const [domain, setDomain] = useState('')
  const [name, setName] = useState('')
  const [queries, setQueries] = useState<string[]>(['', '', ''])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function setQuery(i: number, v: string) {
    setQueries((prev) => {
      const next = [...prev]
      next[i] = v
      return next
    })
  }

  function addRow() {
    if (queries.length >= 10) return
    setQueries((prev) => [...prev, ''])
  }

  function removeRow(i: number) {
    setQueries((prev) => prev.filter((_, idx) => idx !== i))
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (submitting) return
    const cleaned = queries.map((q) => q.trim()).filter(Boolean)
    if (!domain.trim() || cleaned.length === 0) return
    setSubmitting(true)
    setError(null)
    try {
      const check = await startAiVisibilityCheck(
        domain.trim(),
        cleaned,
        name.trim() || undefined,
      )
      router.push(`/ai-visibility/${check.id}`)
    } catch (e) {
      setError((e as Error).message)
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-1.5 block">
            Domaine cible
          </label>
          <input
            type="text"
            required
            disabled={submitting}
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            placeholder="monclient.com"
            className="w-full h-10 px-3 bg-bg-surface border border-[var(--border-default)] rounded-md text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-primary focus:ring-2 focus:ring-[var(--primary-dim)] disabled:opacity-60"
          />
        </div>
        <div>
          <label className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-1.5 block">
            Nom de marque (optionnel)
          </label>
          <input
            type="text"
            disabled={submitting}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Mon Client"
            className="w-full h-10 px-3 bg-bg-surface border border-[var(--border-default)] rounded-md text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-primary focus:ring-2 focus:ring-[var(--primary-dim)] disabled:opacity-60"
          />
        </div>
      </div>

      <div>
        <label className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-1.5 block">
          Requêtes à sonder (1 à 10)
        </label>
        <div className="space-y-2">
          {queries.map((q, i) => (
            <div key={i} className="flex gap-2">
              <input
                type="text"
                disabled={submitting}
                value={q}
                onChange={(e) => setQuery(i, e.target.value)}
                placeholder={`Question #${i + 1} (ex: "meilleure école de cuisine à Paris")`}
                className="flex-1 h-10 px-3 bg-bg-surface border border-[var(--border-default)] rounded-md text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-primary focus:ring-2 focus:ring-[var(--primary-dim)] disabled:opacity-60"
              />
              {queries.length > 1 && (
                <button
                  type="button"
                  onClick={() => removeRow(i)}
                  disabled={submitting}
                  className="h-10 px-3 bg-bg-surface text-text-tertiary border border-[var(--border-default)] rounded-md text-sm hover:text-[var(--status-critical-text)] hover:border-[var(--status-critical-border)] disabled:opacity-60"
                  aria-label="Retirer cette requête"
                >
                  ✕
                </button>
              )}
            </div>
          ))}
          {queries.length < 10 && (
            <button
              type="button"
              onClick={addRow}
              disabled={submitting}
              className="text-xs font-medium text-primary hover:underline underline-offset-4 disabled:opacity-60"
            >
              + Ajouter une requête
            </button>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-xs text-text-tertiary max-w-xl">
          Chaque requête prend 10 à 30 s. Pour 5 requêtes, prévoyez ~2-3 min.
          Vous pouvez quitter la page.
        </p>
        <button
          type="submit"
          disabled={submitting || !domain.trim() || queries.every((q) => !q.trim())}
          className="h-10 px-5 bg-primary hover:bg-primary-hover text-white rounded-md font-medium text-sm transition-colors disabled:opacity-60"
        >
          {submitting ? 'Création…' : 'Lancer la vérification'}
        </button>
      </div>

      {error && (
        <p className="text-xs text-[var(--status-critical-text)]">{error}</p>
      )}
    </form>
  )
}

function CheckTable({ checks }: { checks: AiVisibilityCheck[] }) {
  const router = useRouter()

  async function remove(id: string) {
    try {
      await deleteAiVisibilityCheck(id)
      router.refresh()
    } catch {
      /* swallow */
    }
  }

  if (checks.length === 0) {
    return (
      <div className="border border-dashed border-[var(--border-default)] rounded-md p-10 text-center bg-bg-surface">
        <p className="text-sm text-text-tertiary">
          Aucune vérification enregistrée pour le moment.
        </p>
      </div>
    )
  }
  return (
    <div className="border border-[var(--border-subtle)] rounded-md overflow-hidden bg-bg-surface">
      <div className="grid grid-cols-[1.5fr_80px_120px_80px_140px_60px] bg-bg-elevated border-b border-[var(--border-subtle)]">
        {['Domaine', 'Requêtes', 'Citation', 'Statut', 'Date', ''].map((h, i) => (
          <div
            key={i}
            className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary px-4 py-2.5"
          >
            {h}
          </div>
        ))}
      </div>
      {checks.map((c) => {
        const rate = c.report?.citationRate ?? 0
        return (
          <div
            key={c.id}
            className="grid grid-cols-[1.5fr_80px_120px_80px_140px_60px] border-b border-[var(--border-subtle)] last:border-0 items-center hover:bg-bg-elevated transition-colors"
          >
            <Link
              href={`/ai-visibility/${c.id}`}
              className="px-4 py-3 min-w-0 text-sm font-medium text-text-primary truncate"
            >
              {c.targetDomain}
            </Link>
            <Link
              href={`/ai-visibility/${c.id}`}
              className="px-4 py-3 text-sm tabular-nums text-text-secondary"
            >
              {c.queries.length}
            </Link>
            <Link
              href={`/ai-visibility/${c.id}`}
              className="px-4 py-3 text-sm tabular-nums text-text-secondary"
            >
              {c.status === 'done'
                ? `${Math.round(rate * 100)}%`
                : '—'}
            </Link>
            <Link href={`/ai-visibility/${c.id}`} className="px-4 py-3">
              <StatusPill status={c.status} />
            </Link>
            <Link
              href={`/ai-visibility/${c.id}`}
              className="px-4 py-3 font-mono text-[11px] text-text-tertiary"
            >
              {c.createdAt.slice(0, 16).replace('T', ' ')}
            </Link>
            <div className="px-4 py-3">
              <button
                onClick={() => remove(c.id)}
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

function StatusPill({ status }: { status: AiVisibilityStatus }) {
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
