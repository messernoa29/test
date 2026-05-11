'use client'

import { useState } from 'react'
import type { GeoAuditSummary, GeoPageScore, GeoQueryVerdict } from '@/lib/types'

interface Props {
  data?: GeoAuditSummary
}

type Sub = 'citation' | 'crawlers' | 'pages'

export function GeoTab({ data }: Props) {
  const [sub, setSub] = useState<Sub>('citation')
  if (!data) {
    return (
      <div className="text-sm text-text-tertiary py-8">
        Audit GEO non disponible pour cet audit (antérieur à cette
        fonctionnalité — relancez l&apos;analyse).
      </div>
    )
  }
  const blockedCount = Object.entries(data.aiCrawlerStatus).filter(([, s]) =>
    s.startsWith('blocked'),
  ).length
  const subTabs: { id: Sub; label: string; count?: number }[] = [
    { id: 'citation', label: 'Citation par les IA', count: data.queriesTested || undefined },
    { id: 'crawlers', label: 'Crawlers & llms.txt', count: blockedCount || undefined },
    { id: 'pages', label: 'Citabilité par page', count: data.pageScores.length || undefined },
  ]
  return (
    <div className="space-y-5">
      <p className="text-xs text-text-tertiary">
        GEO = à quel point le site est <strong>citable</strong> par ChatGPT,
        Perplexity, Claude, Google AI Overviews. Différent du SEO : passages
        courts avec réponse directe, headings en questions, stats sourcées, HTML
        server-rendered, crawlers AI autorisés.
      </p>

      {/* Always-visible headline cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <Stat
          label="Score citabilité moyen"
          value={`${data.averagePageScore}/100`}
          tone={data.averagePageScore >= 70 ? 'ok' : data.averagePageScore >= 40 ? 'warn' : 'bad'}
        />
        <Stat
          label="/llms.txt"
          value={data.hasLlmsTxt ? 'présent ✓' : 'absent'}
          tone={data.hasLlmsTxt ? 'ok' : 'warn'}
        />
        <Stat label="Crawlers AI bloqués" value={String(blockedCount)} tone={blockedCount > 0 ? 'warn' : undefined} />
      </div>

      {/* Sub-tabs */}
      <div className="flex gap-1 border-b border-[var(--border-subtle)]">
        {subTabs.map((s) => (
          <button
            key={s.id}
            onClick={() => setSub(s.id)}
            className={`px-3 py-2 text-sm whitespace-nowrap border-b-2 transition-colors flex items-center gap-1.5 ${
              sub === s.id
                ? 'text-primary border-primary font-medium'
                : 'text-text-secondary border-transparent hover:text-text-primary'
            }`}
          >
            {s.label}
            {typeof s.count === 'number' && (
              <span
                className={`text-[10px] tabular-nums px-1.5 py-0.5 rounded ${
                  sub === s.id ? 'bg-[var(--primary-bg)] text-primary' : 'bg-bg-elevated text-text-tertiary'
                }`}
              >
                {s.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {sub === 'citation' && (
        data.queriesTested > 0 ? (
          <section>
            <p className="text-xs text-text-tertiary mb-3">
              {data.queriesTested} requêtes plausibles générées selon l&apos;intention —
              site probablement cité sur <strong>{data.citedCount}/{data.queriesTested}</strong>.
              Estimation IA + recherche web ; ChatGPT/Perplexity ne sont pas interrogeables
              directement, leurs verdicts sont des projections.
            </p>
            <div className="space-y-2">
              {data.queryVerdicts.map((v, i) => (
                <QueryVerdictRow key={i} v={v} />
              ))}
            </div>
          </section>
        ) : (
          <p className="text-sm text-text-tertiary py-6">
            Le test de citabilité par requête n&apos;a pas pu être réalisé pour cet
            audit (délai ou quota IA). Relancez l&apos;audit pour l&apos;obtenir.
          </p>
        )
      )}

      {sub === 'crawlers' && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {data.siteStrengths.length > 0 && (
              <Panel title="Points forts (site)" tone="ok">
                {data.siteStrengths.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </Panel>
            )}
            {data.siteWeaknesses.length > 0 && (
              <Panel title="À corriger (site)" tone="warn">
                {data.siteWeaknesses.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </Panel>
            )}
          </div>
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary mb-2">
              Statut des crawlers AI dans robots.txt
            </h3>
            <div className="flex flex-wrap gap-2 text-xs">
              {Object.entries(data.aiCrawlerStatus).map(([ua, status]) => (
                <span key={ua} className="px-2 py-1 rounded border border-[var(--border-subtle)] bg-bg-surface">
                  <span className="font-mono">{ua}</span>{' '}
                  <span className={statusColor(status)}>{statusLabel(status)}</span>
                </span>
              ))}
            </div>
          </section>
        </div>
      )}

      {sub === 'pages' && (
        data.pageScores.length > 0 ? (
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary mb-2">
              Citabilité par page (les plus faibles d&apos;abord)
            </h3>
            <div className="space-y-2 max-h-[70vh] overflow-y-auto pr-1">
              {data.pageScores.map((p) => (
                <PageRow key={p.url} p={p} />
              ))}
            </div>
          </section>
        ) : (
          <p className="text-sm text-text-tertiary py-6">Aucun score de page disponible.</p>
        )
      )}
    </div>
  )
}

function PageRow({ p }: { p: GeoPageScore }) {
  const tone = p.score >= 70 ? 'ok' : p.score >= 40 ? 'warn' : 'bad'
  return (
    <div className="border border-[var(--border-subtle)] rounded-md bg-bg-surface p-3">
      <div className="flex items-center justify-between gap-2 mb-1">
        <a
          href={p.url}
          target="_blank"
          rel="noreferrer"
          className="font-mono text-xs text-text-secondary hover:text-primary break-all"
        >
          {p.url}
        </a>
        <span className={`text-sm font-semibold tabular-nums ${toneClass(tone)}`}>
          {p.score}/100
        </span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
        {p.strengths.length > 0 && (
          <ul className="space-y-0.5 text-[var(--status-ok-text)]">
            {p.strengths.map((s, i) => (
              <li key={i}>+ {s}</li>
            ))}
          </ul>
        )}
        {p.weaknesses.length > 0 && (
          <ul className="space-y-0.5 text-text-secondary">
            {p.weaknesses.map((s, i) => (
              <li key={i}>− {s}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

function statusLabel(s: string): string {
  if (s === 'allowed') return 'autorisé'
  if (s.startsWith('blocked')) return s.includes('*') ? 'bloqué (via *)' : 'bloqué'
  return 'non mentionné'
}
function statusColor(s: string): string {
  if (s === 'allowed') return 'text-[var(--status-ok-text)]'
  if (s.startsWith('blocked')) return 'text-[var(--status-critical-text)]'
  return 'text-text-tertiary'
}
function toneClass(t: string): string {
  if (t === 'ok') return 'text-[var(--status-ok-text)]'
  if (t === 'warn') return 'text-[var(--status-warning-text)]'
  return 'text-[var(--status-critical-text)]'
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone?: 'ok' | 'warn' | 'bad'
}) {
  return (
    <div className="px-3 py-2 rounded-md border border-[var(--border-subtle)] bg-bg-surface">
      <div className="text-[10px] uppercase tracking-wider text-text-tertiary mb-1">
        {label}
      </div>
      <div
        className={`text-lg font-semibold tabular-nums ${tone ? toneClass(tone) : 'text-text-primary'}`}
      >
        {value}
      </div>
    </div>
  )
}

function Panel({
  title,
  tone,
  children,
}: {
  title: string
  tone: 'ok' | 'warn'
  children: React.ReactNode
}) {
  return (
    <div
      className={`border rounded-md p-3 ${
        tone === 'ok'
          ? 'border-[var(--status-ok-border)] bg-[var(--status-ok-bg)]'
          : 'border-[var(--status-warning-border)] bg-[var(--status-warning-bg)]'
      }`}
    >
      <div
        className={`text-xs font-medium mb-1.5 ${
          tone === 'ok'
            ? 'text-[var(--status-ok-text)]'
            : 'text-[var(--status-warning-text)]'
        }`}
      >
        {title}
      </div>
      <ul
        className={`space-y-1 text-[11px] ${
          tone === 'ok'
            ? 'text-[var(--status-ok-text)]'
            : 'text-[var(--status-warning-text)]'
        }`}
      >
        {children}
      </ul>
    </div>
  )
}

function QueryVerdictRow({ v }: { v: GeoQueryVerdict }) {
  const intentLabel: Record<string, string> = {
    informational: 'info',
    transactional: 'transactionnel',
    local: 'local',
    navigational: 'navigationnel',
  }
  const confColor =
    v.confidence === 'high'
      ? 'text-text-primary'
      : v.confidence === 'medium'
        ? 'text-text-secondary'
        : 'text-text-tertiary'
  return (
    <div className="border border-[var(--border-subtle)] rounded-md bg-bg-surface p-3">
      <div className="flex items-start justify-between gap-3 mb-1">
        <span className="text-sm text-text-primary">« {v.query} »</span>
        <span
          className={`text-xs font-medium flex-shrink-0 ${
            v.likelyCited
              ? 'text-[var(--status-ok-text)]'
              : 'text-[var(--status-warning-text)]'
          }`}
        >
          {v.likelyCited ? 'Probablement cité' : 'Pas cité'}
        </span>
      </div>
      <div className="text-[11px] text-text-tertiary mb-1.5">
        {intentLabel[v.intent] ?? v.intent} ·{' '}
        <span className={confColor}>confiance {v.confidence}</span>
        {v.citingEngines.length > 0 ? ` · ${v.citingEngines.join(', ')}` : ''}
      </div>
      {v.reason && (
        <p className="text-[11px] text-text-secondary mb-1">{v.reason}</p>
      )}
      {v.competitorsCitedInstead.length > 0 && (
        <p className="text-[11px] text-text-tertiary mb-1">
          Cités à la place : {v.competitorsCitedInstead.join(', ')}
        </p>
      )}
      {v.improvement && (
        <p className="text-[11px] text-[var(--primary)]">→ {v.improvement}</p>
      )}
    </div>
  )
}
