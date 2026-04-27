'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import type { AuditJobDetail } from '@/lib/types'

interface Props {
  initial: AuditJobDetail
}

const STEPS = [
  { id: 'crawl', label: 'Crawl du site', detail: 'Lecture des pages et balises SEO' },
  {
    id: 'analyze',
    label: 'Analyse des 6 axes',
    detail: 'Sécurité, SEO, UX, contenu, performance, business',
  },
  { id: 'render', label: 'Préparation du rapport', detail: 'Scores, quick wins, reco' },
] as const

export function AuditPendingView({ initial }: Props) {
  const job = initial
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const createdAtMs =
      new Date(initial.createdAt).getTime() || Date.now()
    const update = () =>
      setElapsed(Math.max(0, Math.floor((Date.now() - createdAtMs) / 1000)))
    update()
    const id = setInterval(update, 500)
    return () => clearInterval(id)
  }, [initial.createdAt])

  if (job.status === 'failed') {
    return <FailedView job={job} />
  }

  // Approximation: crawl ~60s (50 pages parallèles), analyse LLM ~3-5min, finalisation
  const activeIdx = elapsed < 60 ? 0 : elapsed < 240 ? 1 : 2

  const minutes = Math.floor(elapsed / 60)
  const seconds = elapsed % 60
  const elapsedDisplay =
    minutes > 0 ? `${minutes}min ${seconds.toString().padStart(2, '0')}s` : `${seconds}s`

  return (
    <div className="max-w-3xl mx-auto px-8 py-12">
      <div className="flex items-center gap-3 mb-6">
        <Spinner />
        <div>
          <div className="text-xs font-medium text-primary">Analyse en cours</div>
          <code className="font-mono text-xs text-text-secondary break-all">{job.url}</code>
        </div>
      </div>

      <ol className="space-y-3 mb-8">
        {STEPS.map((step, i) => {
          const state = i < activeIdx ? 'done' : i === activeIdx ? 'active' : 'pending'
          return (
            <li key={step.id} className="flex items-start gap-3">
              <StepGlyph state={state} />
              <div>
                <div
                  className={`text-sm ${
                    state === 'pending' ? 'text-text-tertiary' : 'text-text-primary'
                  }`}
                >
                  {step.label}
                </div>
                <div className="text-xs text-text-tertiary">{step.detail}</div>
              </div>
            </li>
          )
        })}
      </ol>

      <div className="grid grid-cols-2 gap-3 mb-6 text-sm">
        <Stat label="Temps écoulé" value={elapsedDisplay} />
        <Stat
          label="Durée estimée"
          value="3 à 8 min"
          hint="50 pages crawlées + analyse IA approfondie"
        />
      </div>

      <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md p-4 text-sm text-text-secondary leading-relaxed">
        Vous pouvez quitter cette page ou rafraîchir : l&apos;analyse tourne côté serveur
        et vous retrouverez le rapport ici dès qu&apos;il sera prêt.{' '}
        <Link
          href="/audit"
          className="text-primary font-medium hover:underline underline-offset-4"
        >
          Revenir à la liste des audits
        </Link>
      </div>

    </div>
  )
}

function FailedView({ job }: { job: AuditJobDetail }) {
  return (
    <div className="max-w-3xl mx-auto px-8 py-12">
      <div className="border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] rounded-md p-5 mb-6">
        <div className="text-[11px] uppercase tracking-wider font-medium text-[var(--status-critical-text)] mb-1.5">
          Analyse échouée
        </div>
        <h1 className="font-semibold text-text-primary mb-2">
          {job.domain}
        </h1>
        <p className="text-sm text-text-secondary mb-2">
          {job.error ?? "L'analyse n'a pas pu aboutir."}
        </p>
        <code className="font-mono text-xs text-text-tertiary break-all">{job.url}</code>
      </div>
      <div className="flex gap-2">
        <Link
          href="/audit"
          className="inline-flex h-10 px-4 items-center bg-bg-surface text-text-secondary border border-[var(--border-default)] rounded-md font-medium text-sm hover:bg-bg-elevated hover:text-text-primary transition-colors"
        >
          ← Retour aux audits
        </Link>
      </div>
    </div>
  )
}

function Spinner() {
  return (
    <span
      className="inline-block w-5 h-5 rounded-full border-2 border-[var(--border-default)] animate-spin"
      style={{ borderTopColor: 'var(--primary)', animationDuration: '0.7s' }}
    />
  )
}

function StepGlyph({ state }: { state: 'done' | 'active' | 'pending' }) {
  if (state === 'done') {
    return <span className="mt-[3px] text-xs text-primary">✓</span>
  }
  if (state === 'active') {
    return (
      <span
        className="mt-[5px] inline-block w-2 h-2 rounded-full bg-primary"
        style={{ animation: 'pulse-critical 1.5s ease-in-out infinite' }}
      />
    )
  }
  return (
    <span
      className="mt-[5px] inline-block w-2 h-2 rounded-full border"
      style={{ borderColor: 'var(--border-default)' }}
    />
  )
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string
  value: string
  hint?: string
}) {
  return (
    <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md p-3">
      <div className="text-[10px] uppercase tracking-wider font-medium text-text-tertiary mb-1">
        {label}
      </div>
      <div className="text-xl font-semibold tabular-nums text-text-primary">{value}</div>
      {hint && <div className="text-[11px] text-text-tertiary mt-0.5">{hint}</div>}
    </div>
  )
}
