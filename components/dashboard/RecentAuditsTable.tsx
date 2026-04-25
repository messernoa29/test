'use client'

import Link from 'next/link'
import type { AuditJobSummary } from '@/lib/types'
import { scoreHexColor } from '@/lib/design'
import { AuditActions } from '@/components/audit/AuditActions'

interface Props {
  audits: AuditJobSummary[]
  emptyCta?: boolean
}

export function RecentAuditsTable({ audits, emptyCta = true }: Props) {
  if (audits.length === 0) {
    return (
      <div className="border border-dashed border-[var(--border-default)] rounded-md p-10 text-center bg-bg-surface">
        <p className="text-sm text-text-tertiary">Aucun audit pour le moment</p>
        {emptyCta && (
          <Link
            href="/audit"
            className="inline-block mt-3 text-xs font-medium text-primary hover:underline underline-offset-4"
          >
            Lancer le premier audit →
          </Link>
        )}
      </div>
    )
  }
  return (
    <div className="border border-[var(--border-subtle)] rounded-md overflow-hidden bg-bg-surface">
      <div className="grid grid-cols-[1.6fr_70px_80px_80px_120px_140px] bg-bg-elevated border-b border-[var(--border-subtle)]">
        {['Domaine', 'Score', 'Critiques', 'Warnings', 'Date', ''].map((h, i) => (
          <div
            key={i}
            className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary px-4 py-2.5"
          >
            {h}
          </div>
        ))}
      </div>
      {audits.map((a) => (
        <AuditRow key={a.id} audit={a} />
      ))}
    </div>
  )
}

function AuditRow({ audit: a }: { audit: AuditJobSummary }) {
  const href = `/audit/${a.id}`
  const pending = a.status === 'pending'
  const failed = a.status === 'failed'

  return (
    <div className="group grid grid-cols-[1.6fr_70px_80px_80px_120px_140px] border-b border-[var(--border-subtle)] last:border-0 items-center hover:bg-bg-elevated transition-colors">
      <Link href={href} className="px-4 py-3 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="text-sm font-medium text-text-primary truncate">
            {a.domain}
          </div>
          {pending && (
            <span className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-medium text-[var(--status-info-text)] bg-[var(--status-info-bg)] border border-[var(--status-info-border)] px-1.5 py-0.5 rounded">
              <span
                className="w-1.5 h-1.5 rounded-full bg-[var(--status-info-accent)]"
                style={{ animation: 'pulse-critical 1.5s ease-in-out infinite' }}
              />
              En cours
            </span>
          )}
          {failed && (
            <span className="text-[10px] uppercase tracking-wider font-medium text-[var(--status-critical-text)] bg-[var(--status-critical-bg)] border border-[var(--status-critical-border)] px-1.5 py-0.5 rounded">
              Échec
            </span>
          )}
          {a.archived && (
            <span className="text-[9px] uppercase tracking-wider font-medium text-text-tertiary bg-bg-elevated border border-[var(--border-subtle)] px-1.5 py-0.5 rounded">
              Archivé
            </span>
          )}
        </div>
        <div className="font-mono text-[11px] text-text-tertiary truncate">
          {a.url}
        </div>
      </Link>
      <Link href={href} className="px-4 py-3">
        {typeof a.globalScore === 'number' ? (
          <span
            className="text-base font-semibold tabular-nums"
            style={{ color: scoreHexColor(a.globalScore) }}
          >
            {a.globalScore}
          </span>
        ) : (
          <span className="text-sm text-text-tertiary">—</span>
        )}
      </Link>
      <Link href={href} className="text-sm tabular-nums text-text-primary px-4 py-3">
        {typeof a.criticalCount === 'number' ? a.criticalCount : '—'}
      </Link>
      <Link
        href={href}
        className="text-sm tabular-nums text-text-secondary px-4 py-3"
      >
        {typeof a.warningCount === 'number' ? a.warningCount : '—'}
      </Link>
      <Link
        href={href}
        className="font-mono text-[11px] text-text-tertiary px-4 py-3"
      >
        {a.createdAt.slice(0, 10)}
      </Link>
      <div className="px-4 py-3 flex items-center">
        <AuditActions
          auditId={a.id}
          archived={a.archived === true}
          rerunUrl={a.url}
          variant="compact"
        />
      </div>
    </div>
  )
}
