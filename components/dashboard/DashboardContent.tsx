'use client'

import Link from 'next/link'
import { listRecent } from '@/lib/api'
import type { AuditJobSummary } from '@/lib/types'
import { usePolling } from '@/lib/usePolling'
import { RecentAuditsTable } from './RecentAuditsTable'
import { StatCard } from './StatCard'
import { ToolGrid } from './ToolGrid'

interface Props {
  initial: AuditJobSummary[]
}

export function DashboardContent({ initial }: Props) {
  const hasPending = initial.some((a) => a.status === 'pending')
  const { data } = usePolling(() => listRecent(), hasPending, 3000)
  const audits = data ?? initial

  const done = audits.filter((a) => a.status === 'done')
  const total = audits.length
  const totalDone = done.length
  const avgScore =
    totalDone > 0
      ? Math.round(done.reduce((s, a) => s + (a.globalScore ?? 0), 0) / totalDone)
      : 0
  const criticals = done.reduce((s, a) => s + (a.criticalCount ?? 0), 0)
  const warnings = done.reduce((s, a) => s + (a.warningCount ?? 0), 0)
  const pending = audits.filter((a) => a.status === 'pending').length

  return (
    <div className="max-w-6xl mx-auto px-8 py-8">
      <div className="flex items-start justify-between mb-8 gap-6">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary mb-1">Dashboard</h1>
          <p className="text-sm text-text-secondary">
            {total > 0
              ? `${total} audit${total > 1 ? 's' : ''} en session${pending > 0 ? ` · ${pending} en cours` : ''}.`
              : 'Aucun audit pour le moment. Lancez votre premier rapport.'}
          </p>
        </div>
        <Link
          href="/audit"
          className="inline-flex h-10 px-4 items-center bg-primary hover:bg-primary-hover text-white rounded-md font-medium text-sm transition-colors"
        >
          Nouvel audit
        </Link>
      </div>

      <section className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-10">
        <StatCard label="Audits" value={total} hint={`${totalDone} terminés`} />
        <StatCard
          label="Score moyen"
          value={totalDone > 0 ? avgScore : '—'}
          hint={totalDone > 0 ? 'Tous axes confondus' : 'En attente du premier rapport'}
          tone={
            totalDone === 0
              ? 'default'
              : avgScore < 40
                ? 'critical'
                : avgScore < 60
                  ? 'warning'
                  : 'ok'
          }
        />
        <StatCard
          label="Points critiques"
          value={criticals}
          hint="Cumul des audits terminés"
          tone="critical"
        />
        <StatCard
          label="Avertissements"
          value={warnings}
          hint="Cumul des audits terminés"
          tone="warning"
        />
      </section>

      <section className="mb-10">
        <div className="mb-4">
          <h2 className="text-base font-semibold text-text-primary">Suite agence</h2>
          <p className="text-xs text-text-tertiary mt-0.5">Outils disponibles</p>
        </div>
        <ToolGrid />
      </section>

      <section>
        <div className="flex items-end justify-between mb-4">
          <div>
            <h2 className="text-base font-semibold text-text-primary">Derniers audits</h2>
            <p className="text-xs text-text-tertiary mt-0.5">Historique récent</p>
          </div>
          {total > 0 && (
            <Link
              href="/audit"
              className="text-xs font-medium text-primary hover:underline underline-offset-4"
            >
              Voir tout →
            </Link>
          )}
        </div>
        <RecentAuditsTable audits={audits.slice(0, 8)} />
      </section>
    </div>
  )
}
