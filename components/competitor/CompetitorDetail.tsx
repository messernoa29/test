'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { getAudit, getCompetitorBattle } from '@/lib/api'
import type {
  AuditJobDetail,
  CompetitorBattle,
  CompetitorSite,
} from '@/lib/types'
import { scoreHexColor } from '@/lib/design'

interface Props {
  initial: CompetitorBattle
}

const AXIS_LABEL: Record<string, string> = {
  security: 'Sécurité',
  seo: 'SEO',
  ux: 'UX',
  content: 'Contenu',
  performance: 'Performance',
  business: 'Business',
}

export function CompetitorDetail({ initial }: Props) {
  const [battle, setBattle] = useState<CompetitorBattle>(initial)
  const [audits, setAudits] = useState<Record<string, AuditJobDetail>>({})

  // Poll the battle while it's running.
  useEffect(() => {
    if (battle.status === 'done' || battle.status === 'failed') return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const tick = async () => {
      try {
        const next = await getCompetitorBattle(battle.id)
        if (!cancelled) setBattle(next)
        if (next.status === 'done' || next.status === 'failed') return
      } catch {
        // keep polling
      }
      if (!cancelled) timer = setTimeout(tick, 4000)
    }
    timer = setTimeout(tick, 4000)
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [battle.id, battle.status])

  // Fetch each linked audit once its id is known so we can display scores.
  useEffect(() => {
    let cancelled = false
    battle.competitors.forEach(async (site) => {
      if (!site.auditId || audits[site.auditId]) return
      try {
        const detail = await getAudit(site.auditId)
        if (!cancelled) setAudits((prev) => ({ ...prev, [site.auditId!]: detail }))
      } catch {
        // ignore, the poll will catch up when it retries
      }
    })
    return () => {
      cancelled = true
    }
  }, [battle.competitors, audits])

  const targetSite = battle.competitors.find((s) => s.url === battle.targetUrl)
  const competitorSites = battle.competitors.filter(
    (s) => s.url !== battle.targetUrl,
  )

  return (
    <div>
      <div className="border-b border-[var(--border-subtle)] bg-bg-surface">
        <div className="max-w-6xl mx-auto px-8 py-5 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-xs text-text-tertiary mb-1">
              Competitor Watch · {battle.createdAt.slice(0, 10)}
            </p>
            <h1 className="text-xl font-semibold text-text-primary truncate">
              {safeHost(battle.targetUrl)}
            </h1>
            <p className="text-xs text-text-tertiary mt-0.5">
              vs {competitorSites.length} concurrent
              {competitorSites.length > 1 ? 's' : ''}
            </p>
          </div>
          <Link
            href="/competitor-watch"
            className="inline-flex h-9 px-3 items-center bg-bg-surface text-text-secondary border border-[var(--border-default)] rounded-md font-medium text-sm hover:bg-bg-elevated hover:text-text-primary transition-colors"
          >
            ← Toutes les comparaisons
          </Link>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-8 py-8 space-y-8">
        {battle.status === 'failed' && (
          <div className="border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] rounded-md p-4">
            <div className="text-[11px] uppercase tracking-wider font-medium text-[var(--status-critical-text)] mb-1">
              Échec
            </div>
            <p className="text-sm text-text-primary">{battle.error ?? 'Erreur inconnue.'}</p>
          </div>
        )}

        <SitesGrid battle={battle} audits={audits} />

        <ScoresTable battle={battle} audits={audits} />

        {battle.report && <ReportView report={battle.report} />}

        {battle.status !== 'done' && !battle.report && (
          <div className="border border-dashed border-[var(--border-default)] rounded-md p-8 text-center bg-bg-surface">
            <p className="text-sm text-text-secondary">
              Les audits tournent en parallèle. La synthèse IA apparaîtra ici dès
              que tous les sites auront été analysés.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

function SitesGrid({
  battle,
  audits,
}: {
  battle: CompetitorBattle
  audits: Record<string, AuditJobDetail>
}) {
  return (
    <section>
      <h2 className="text-base font-semibold text-text-primary mb-3">Sites</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {battle.competitors.map((site) => {
          const audit = site.auditId ? audits[site.auditId] : undefined
          const isTarget = site.url === battle.targetUrl
          return (
            <SiteCard
              key={site.url}
              site={site}
              audit={audit}
              isTarget={isTarget}
            />
          )
        })}
      </div>
    </section>
  )
}

function SiteCard({
  site,
  audit,
  isTarget,
}: {
  site: CompetitorSite
  audit?: AuditJobDetail
  isTarget: boolean
}) {
  const status = audit?.status ?? 'pending'
  const score = audit?.result?.globalScore
  return (
    <div
      className={`bg-bg-surface border rounded-md p-4 ${
        isTarget
          ? 'border-[var(--primary-border)] ring-1 ring-[var(--primary-border)]'
          : 'border-[var(--border-subtle)]'
      }`}
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] uppercase tracking-wider font-medium text-text-tertiary">
          {isTarget ? 'Site cible' : 'Concurrent'}
        </span>
        {status === 'pending' && (
          <span
            className="w-1.5 h-1.5 rounded-full bg-[var(--status-info-accent)]"
            style={{ animation: 'pulse-critical 1.5s ease-in-out infinite' }}
          />
        )}
        {status === 'failed' && (
          <span className="text-[10px] font-medium text-[var(--status-critical-text)]">
            Échec
          </span>
        )}
      </div>
      <div className="text-sm font-medium text-text-primary truncate">
        {safeHost(site.url)}
      </div>
      <div className="font-mono text-[11px] text-text-tertiary truncate mb-3">
        {site.url}
      </div>
      {typeof score === 'number' ? (
        <div className="flex items-baseline gap-1.5">
          <span
            className="text-2xl font-semibold tabular-nums leading-none"
            style={{ color: scoreHexColor(score) }}
          >
            {score}
          </span>
          <span className="text-xs text-text-tertiary">/100</span>
          {audit?.id && (
            <Link
              href={`/audit/${audit.id}`}
              className="ml-auto text-[11px] font-medium text-primary hover:underline underline-offset-4"
            >
              Ouvrir →
            </Link>
          )}
        </div>
      ) : (
        <div className="text-sm text-text-tertiary">—</div>
      )}
    </div>
  )
}

function ScoresTable({
  battle,
  audits,
}: {
  battle: CompetitorBattle
  audits: Record<string, AuditJobDetail>
}) {
  const axes = ['security', 'seo', 'ux', 'content', 'performance', 'business']
  const sites = battle.competitors

  const scoresBySite = sites.map((site) => {
    const audit = site.auditId ? audits[site.auditId] : undefined
    const scores: Record<string, number> = (audit?.result?.scores ?? {}) as Record<
      string,
      number
    >
    return {
      site,
      scores,
      global: audit?.result?.globalScore,
      status: audit?.status,
    }
  })

  const winners = battle.report?.winnersByAxis ?? {}

  return (
    <section>
      <h2 className="text-base font-semibold text-text-primary mb-3">
        Scores par axe
      </h2>
      <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md overflow-hidden">
        <div
          className="grid bg-bg-elevated border-b border-[var(--border-subtle)]"
          style={{ gridTemplateColumns: `140px repeat(${sites.length}, 1fr)` }}
        >
          <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary px-4 py-2.5">
            Axe
          </div>
          {sites.map((site) => (
            <div
              key={site.url}
              className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary px-3 py-2.5 truncate"
              title={site.url}
            >
              {safeHost(site.url)}
            </div>
          ))}
        </div>

        <div
          className="grid border-b border-[var(--border-subtle)]"
          style={{ gridTemplateColumns: `140px repeat(${sites.length}, 1fr)` }}
        >
          <div className="text-sm font-medium text-text-primary px-4 py-3">
            Score global
          </div>
          {scoresBySite.map(({ site, global, status }) => (
            <div key={site.url} className="px-3 py-3 flex items-baseline gap-1">
              {typeof global === 'number' ? (
                <>
                  <span
                    className="text-lg font-semibold tabular-nums leading-none"
                    style={{ color: scoreHexColor(global) }}
                  >
                    {global}
                  </span>
                  <span className="text-xs text-text-tertiary">/100</span>
                </>
              ) : (
                <span className="text-sm text-text-tertiary">
                  {status === 'failed' ? 'échec' : '…'}
                </span>
              )}
            </div>
          ))}
        </div>

        {axes.map((axis) => (
          <div
            key={axis}
            className="grid border-b border-[var(--border-subtle)] last:border-0 items-center"
            style={{ gridTemplateColumns: `140px repeat(${sites.length}, 1fr)` }}
          >
            <div className="text-sm text-text-secondary px-4 py-2.5">
              {AXIS_LABEL[axis] ?? axis}
            </div>
            {scoresBySite.map(({ site, scores }) => {
              const val = scores?.[axis]
              const isWinner = winners[axis] === site.url
              return (
                <div
                  key={site.url}
                  className="px-3 py-2.5 text-sm tabular-nums flex items-center gap-2"
                >
                  {typeof val === 'number' ? (
                    <>
                      <span style={{ color: scoreHexColor(val) }} className="font-medium">
                        {val}
                      </span>
                      {isWinner && (
                        <span
                          className="text-[10px] uppercase tracking-wider font-semibold text-primary bg-[var(--primary-bg)] px-1.5 py-0.5 rounded"
                          title="Meilleur sur cet axe"
                        >
                          top
                        </span>
                      )}
                    </>
                  ) : (
                    <span className="text-text-tertiary">—</span>
                  )}
                </div>
              )
            })}
          </div>
        ))}
      </div>
    </section>
  )
}

function ReportView({ report }: { report: CompetitorBattle['report'] }) {
  if (!report) return null
  return (
    <section className="space-y-6">
      <h2 className="text-base font-semibold text-text-primary">
        Synthèse IA
      </h2>

      {report.verdict && (
        <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md p-5">
          <div className="text-[11px] uppercase tracking-wider font-medium text-primary mb-2">
            Verdict
          </div>
          <p className="text-sm text-text-primary leading-relaxed">
            {report.verdict}
          </p>
        </div>
      )}

      {report.keyInsights.length > 0 && (
        <InsightBlock
          label="Observations clés"
          items={report.keyInsights}
          tone="primary"
        />
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <InsightBlock
          label="Nos forces"
          items={report.ourStrengths}
          tone="ok"
        />
        <InsightBlock
          label="Nos faiblesses"
          items={report.ourWeaknesses}
          tone="critical"
        />
      </div>

      {report.priorityActions.length > 0 && (
        <InsightBlock
          label="Actions prioritaires"
          items={report.priorityActions}
          tone="warning"
          numbered
        />
      )}
    </section>
  )
}

function InsightBlock({
  label,
  items,
  tone,
  numbered = false,
}: {
  label: string
  items: string[]
  tone: 'primary' | 'ok' | 'critical' | 'warning'
  numbered?: boolean
}) {
  if (items.length === 0) return null
  const color = {
    primary: 'var(--primary)',
    ok: 'var(--status-ok-accent)',
    critical: 'var(--status-critical-accent)',
    warning: 'var(--status-warning-accent)',
  }[tone]
  return (
    <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md">
      <div
        className="text-[11px] uppercase tracking-wider font-medium px-5 pt-4 pb-2"
        style={{ color }}
      >
        {label}
      </div>
      <ul>
        {items.map((item, i) => (
          <li
            key={i}
            className="flex items-start gap-3 px-5 py-2.5 border-t border-[var(--border-subtle)] first:border-0"
          >
            {numbered ? (
              <span className="text-xs tabular-nums text-text-tertiary mt-[3px] w-5">
                {String(i + 1).padStart(2, '0')}
              </span>
            ) : (
              <span
                className="inline-block w-1.5 h-1.5 rounded-full mt-[7px]"
                style={{ background: color }}
              />
            )}
            <span className="text-sm text-text-primary leading-relaxed">
              {item}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function safeHost(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}
