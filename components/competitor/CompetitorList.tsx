'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'
import {
  deleteCompetitorBattle,
  listCompetitorBattles,
  startCompetitorBattle,
} from '@/lib/api'
import type {
  CompetitorBattle,
  CompetitorBattleStatus,
} from '@/lib/types'
import { usePolling } from '@/lib/usePolling'

interface Props {
  initial: CompetitorBattle[]
}

export function CompetitorList({ initial }: Props) {
  const hasPending = initial.some(
    (b) => b.status === 'pending' || b.status === 'running',
  )
  const { data } = usePolling(() => listCompetitorBattles(), hasPending, 4000)
  const battles = data ?? initial

  return (
    <div className="max-w-6xl mx-auto px-8 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-text-primary mb-1">
          Competitor Watch
        </h1>
        <p className="text-sm text-text-secondary max-w-2xl">
          Audit comparatif entre le site d&apos;un client et jusqu&apos;à 5 concurrents.
          Chaque site est analysé indépendamment, puis une synthèse IA identifie
          les axes gagnants, les forces et les actions prioritaires.
        </p>
      </div>

      <section className="mb-10">
        <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md p-5">
          <NewBattleForm />
        </div>
      </section>

      <section>
        <div className="flex items-end justify-between mb-4">
          <div>
            <h2 className="text-base font-semibold text-text-primary">
              Comparaisons précédentes
            </h2>
            <p className="text-xs text-text-tertiary mt-0.5">
              {battles.length} comparaison{battles.length > 1 ? 's' : ''} conservée
              {battles.length > 1 ? 's' : ''}
            </p>
          </div>
        </div>
        <BattleTable battles={battles} />
      </section>
    </div>
  )
}

function NewBattleForm() {
  const router = useRouter()
  const [target, setTarget] = useState('')
  const [competitors, setCompetitors] = useState<string[]>(['', ''])
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const valid = useMemo(() => {
    const cleanedCompetitors = competitors.map((c) => c.trim()).filter(Boolean)
    return target.trim().length > 0 && cleanedCompetitors.length >= 1
  }, [target, competitors])

  function updateCompetitor(index: number, value: string) {
    setCompetitors((prev) => {
      const next = [...prev]
      next[index] = value
      return next
    })
  }

  function addCompetitorRow() {
    if (competitors.length >= 5) return
    setCompetitors((prev) => [...prev, ''])
  }

  function removeCompetitorRow(index: number) {
    setCompetitors((prev) => prev.filter((_, i) => i !== index))
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!valid || submitting) return
    setError(null)
    setSubmitting(true)
    try {
      const cleaned = competitors.map((c) => c.trim()).filter(Boolean)
      const battle = await startCompetitorBattle(target.trim(), cleaned)
      router.push(`/competitor-watch/${battle.id}`)
    } catch (err) {
      setError((err as Error).message || 'Impossible de lancer la comparaison.')
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <div>
        <label className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-1.5 block">
          URL du site cible (votre client)
        </label>
        <input
          type="url"
          required
          disabled={submitting}
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          placeholder="https://monclient.com"
          className="w-full h-10 px-3 bg-bg-surface border border-[var(--border-default)] rounded-md text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-primary focus:ring-2 focus:ring-[var(--primary-dim)] disabled:opacity-60"
        />
      </div>

      <div>
        <label className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-1.5 block">
          Concurrents (1 à 5)
        </label>
        <div className="space-y-2">
          {competitors.map((url, i) => (
            <div key={i} className="flex gap-2">
              <input
                type="url"
                disabled={submitting}
                value={url}
                onChange={(e) => updateCompetitor(i, e.target.value)}
                placeholder={`https://concurrent-${i + 1}.com`}
                className="flex-1 h-10 px-3 bg-bg-surface border border-[var(--border-default)] rounded-md text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-primary focus:ring-2 focus:ring-[var(--primary-dim)] disabled:opacity-60"
              />
              {competitors.length > 1 && (
                <button
                  type="button"
                  onClick={() => removeCompetitorRow(i)}
                  disabled={submitting}
                  className="h-10 px-3 bg-bg-surface text-text-tertiary border border-[var(--border-default)] rounded-md text-sm hover:text-[var(--status-critical-text)] hover:border-[var(--status-critical-border)] disabled:opacity-60"
                  aria-label="Retirer ce concurrent"
                >
                  ✕
                </button>
              )}
            </div>
          ))}
          {competitors.length < 5 && (
            <button
              type="button"
              onClick={addCompetitorRow}
              disabled={submitting}
              className="text-xs font-medium text-primary hover:underline underline-offset-4 disabled:opacity-60"
            >
              + Ajouter un concurrent
            </button>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="text-xs text-text-tertiary max-w-xl">
          Chaque site prend 40 à 90 s. Le total est séquentiel côté LLM mais en
          parallèle côté crawl — prévoir 2 à 5 min. Vous pouvez quitter la page.
        </div>
        <button
          type="submit"
          disabled={!valid || submitting}
          className="inline-flex h-10 px-5 items-center bg-primary text-white rounded-md font-medium text-sm hover:bg-primary-hover disabled:opacity-60 transition-colors"
        >
          {submitting ? 'Création…' : 'Lancer la comparaison'}
        </button>
      </div>

      {error && (
        <p className="text-xs text-[var(--status-critical-text)]">{error}</p>
      )}
    </form>
  )
}

function BattleTable({ battles }: { battles: CompetitorBattle[] }) {
  const router = useRouter()

  async function remove(id: string) {
    try {
      await deleteCompetitorBattle(id)
      router.refresh()
    } catch {
      // Rare — swallow.
    }
  }

  if (battles.length === 0) {
    return (
      <div className="border border-dashed border-[var(--border-default)] rounded-md p-10 text-center bg-bg-surface">
        <p className="text-sm text-text-tertiary">
          Aucune comparaison enregistrée pour le moment.
        </p>
      </div>
    )
  }
  return (
    <div className="border border-[var(--border-subtle)] rounded-md overflow-hidden bg-bg-surface">
      <div className="grid grid-cols-[1.7fr_80px_80px_140px_60px] bg-bg-elevated border-b border-[var(--border-subtle)]">
        {['Site cible', 'Concurrents', 'Statut', 'Date', ''].map((h, i) => (
          <div
            key={i}
            className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary px-4 py-2.5"
          >
            {h}
          </div>
        ))}
      </div>
      {battles.map((b) => (
        <div
          key={b.id}
          className="grid grid-cols-[1.7fr_80px_80px_140px_60px] border-b border-[var(--border-subtle)] last:border-0 items-center hover:bg-bg-elevated transition-colors"
        >
          <Link href={`/competitor-watch/${b.id}`} className="px-4 py-3 min-w-0">
            <div className="text-sm font-medium text-text-primary truncate">
              {new URL(b.targetUrl).hostname.replace(/^www\./, '')}
            </div>
            <div className="font-mono text-[11px] text-text-tertiary truncate">
              {b.targetUrl}
            </div>
          </Link>
          <Link href={`/competitor-watch/${b.id}`} className="px-4 py-3 tabular-nums text-sm text-text-secondary">
            {Math.max(0, b.competitors.length - 1)}
          </Link>
          <Link href={`/competitor-watch/${b.id}`} className="px-4 py-3">
            <StatusPill status={b.status} />
          </Link>
          <Link href={`/competitor-watch/${b.id}`} className="px-4 py-3 font-mono text-[11px] text-text-tertiary">
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

function StatusPill({ status }: { status: CompetitorBattleStatus }) {
  const label =
    status === 'pending'
      ? 'En file'
      : status === 'running'
        ? 'En cours'
        : status === 'done'
          ? 'Prêt'
          : 'Échec'
  const kind: 'info' | 'ok' | 'critical' | 'warning' =
    status === 'done'
      ? 'ok'
      : status === 'failed'
        ? 'critical'
        : status === 'pending'
          ? 'info'
          : 'warning'
  const classes = {
    info: 'bg-[var(--status-info-bg)] text-[var(--status-info-text)] border-[var(--status-info-border)]',
    ok: 'bg-[var(--status-ok-bg)] text-[var(--status-ok-text)] border-[var(--status-ok-border)]',
    critical:
      'bg-[var(--status-critical-bg)] text-[var(--status-critical-text)] border-[var(--status-critical-border)]',
    warning:
      'bg-[var(--status-warning-bg)] text-[var(--status-warning-text)] border-[var(--status-warning-border)]',
  }[kind]
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
      {label}
    </span>
  )
}
