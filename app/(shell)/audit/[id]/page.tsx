'use client'

import { useEffect, useState } from 'react'
import { notFound, useParams } from 'next/navigation'
import Link from 'next/link'
import { AuthRequiredError, getAudit, markdownUrl, pdfUrl, xlsxUrl } from '@/lib/api'
import type { AuditJobDetail } from '@/lib/types'
import { AuditActions } from '@/components/audit/AuditActions'
import { AuditDetailView } from '@/components/audit/AuditDetailView'
import { AuditPendingView } from '@/components/audit/AuditPendingView'

export default function AuditDetailPage() {
  const params = useParams<{ id: string }>()
  const id = params?.id
  const [job, setJob] = useState<AuditJobDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const tick = async () => {
      try {
        const next = await getAudit(id)
        if (cancelled) return
        setJob(next)
        if (next.status === 'pending') {
          timer = setTimeout(tick, 1500)
        }
      } catch (e) {
        if (cancelled) return
        if (e instanceof AuthRequiredError) return
        const msg = (e as Error).message ?? ''
        if (msg.includes('not found') || msg.includes('404')) {
          notFound()
          return
        }
        setError(msg || 'Erreur de chargement')
      }
    }

    tick()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [id])

  if (error) {
    return (
      <div className="max-w-2xl mx-auto px-8 py-16 text-text-secondary">
        <h1 className="text-xl font-semibold text-text-primary mb-2">
          Impossible de charger l&apos;audit
        </h1>
        <p className="text-sm">{error}</p>
      </div>
    )
  }

  if (!job) {
    return (
      <div className="max-w-2xl mx-auto px-8 py-16 text-text-secondary text-sm">
        Chargement…
      </div>
    )
  }

  const archived = job.archived === true
  const isDone = job.status === 'done' && job.result

  return (
    <div>
      <div className="border-b border-[var(--border-subtle)] bg-bg-surface">
        <div className="max-w-6xl mx-auto px-8 py-5 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <p className="text-xs text-text-tertiary">
                Rapport d&apos;audit · {job.createdAt.slice(0, 10)}
              </p>
              <StatusBadge status={job.status} />
              {archived && (
                <span className="text-[10px] uppercase tracking-wider font-medium text-text-tertiary bg-bg-elevated border border-[var(--border-subtle)] px-1.5 py-0.5 rounded">
                  Archivé
                </span>
              )}
            </div>
            <h1 className="text-xl font-semibold text-text-primary leading-tight truncate">
              {job.domain}
            </h1>
            <a
              href={job.url}
              target="_blank"
              rel="noreferrer"
              className="font-mono text-xs text-text-secondary hover:text-primary transition-colors break-all"
            >
              {job.url}
            </a>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0 flex-wrap">
            <Link
              href="/audit"
              className="inline-flex h-9 px-3 items-center bg-bg-surface text-text-secondary border border-[var(--border-default)] rounded-md font-medium text-sm hover:bg-bg-elevated hover:text-text-primary transition-colors"
            >
              ← Tous les audits
            </Link>
            <AuditActions
              auditId={job.id}
              archived={archived}
              rerunUrl={job.url}
              redirectTo="/audit"
            />
            {isDone && (
              <>
                <a
                  href={markdownUrl(job.id)}
                  className="inline-flex h-9 px-3 items-center bg-bg-surface text-text-primary border border-[var(--border-default)] rounded-md font-medium text-sm hover:bg-bg-elevated transition-colors"
                  title="Fichier .md prêt à importer dans Notion / Obsidian (cases à cocher pour chaque action)"
                >
                  Markdown / Notion
                </a>
                <a
                  href={xlsxUrl(job.id)}
                  className="inline-flex h-9 px-3 items-center bg-bg-surface text-text-primary border border-[var(--border-default)] rounded-md font-medium text-sm hover:bg-bg-elevated transition-colors"
                >
                  Excel
                </a>
                <a
                  href={pdfUrl(job.id)}
                  className="inline-flex h-9 px-3 items-center bg-primary hover:bg-primary-hover text-white rounded-md font-medium text-sm transition-colors"
                >
                  Télécharger le PDF
                </a>
              </>
            )}
          </div>
        </div>
      </div>

      {isDone && job.result ? (
        <AuditDetailView audit={job.result} />
      ) : (
        <AuditPendingView initial={job} />
      )}
    </div>
  )
}

function StatusBadge({ status }: { status: 'pending' | 'done' | 'failed' }) {
  if (status === 'pending') {
    return (
      <span className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-medium text-[var(--status-info-text)] bg-[var(--status-info-bg)] border border-[var(--status-info-border)] px-1.5 py-0.5 rounded">
        <span
          className="w-1.5 h-1.5 rounded-full bg-[var(--status-info-accent)]"
          style={{ animation: 'pulse-critical 1.5s ease-in-out infinite' }}
        />
        En cours
      </span>
    )
  }
  if (status === 'failed') {
    return (
      <span className="text-[10px] uppercase tracking-wider font-medium text-[var(--status-critical-text)] bg-[var(--status-critical-bg)] border border-[var(--status-critical-border)] px-1.5 py-0.5 rounded">
        Échec
      </span>
    )
  }
  return null
}
