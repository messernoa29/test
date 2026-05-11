'use client'

import type { GeoAuditSummary, GeoPageScore } from '@/lib/types'

interface Props {
  data?: GeoAuditSummary
}

export function GeoTab({ data }: Props) {
  if (!data) {
    return (
      <div className="text-sm text-text-tertiary py-8">
        Audit GEO non disponible pour cet audit (antérieur à cette
        fonctionnalité — relancez l&apos;analyse).
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <p className="text-xs text-text-tertiary">
        GEO (Generative Engine Optimization) = à quel point le site est{' '}
        <strong>citable</strong> par ChatGPT, Perplexity, Claude, Google AI
        Overviews. Différent du SEO classique : il faut des passages courts
        avec réponse directe, des headings en questions, des stats sourcées,
        du HTML server-rendered, et les crawlers AI autorisés.
      </p>

      {/* Headline */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <Stat
          label="Score citabilité moyen"
          value={`${data.averagePageScore}/100`}
          tone={
            data.averagePageScore >= 70
              ? 'ok'
              : data.averagePageScore >= 40
                ? 'warn'
                : 'bad'
          }
        />
        <Stat
          label="/llms.txt"
          value={data.hasLlmsTxt ? 'présent ✓' : 'absent'}
          tone={data.hasLlmsTxt ? 'ok' : 'warn'}
        />
        <Stat
          label="Crawlers AI bloqués"
          value={String(
            Object.entries(data.aiCrawlerStatus).filter(([, s]) =>
              s.startsWith('blocked'),
            ).length,
          )}
        />
      </div>

      {/* Site-level */}
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

      {/* AI crawler status */}
      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary mb-2">
          Statut des crawlers AI dans robots.txt
        </h3>
        <div className="flex flex-wrap gap-2 text-xs">
          {Object.entries(data.aiCrawlerStatus).map(([ua, status]) => (
            <span
              key={ua}
              className="px-2 py-1 rounded border border-[var(--border-subtle)] bg-bg-surface"
            >
              <span className="font-mono">{ua}</span>{' '}
              <span className={statusColor(status)}>{statusLabel(status)}</span>
            </span>
          ))}
        </div>
      </section>

      {/* Per-page (worst first) */}
      {data.pageScores.length > 0 && (
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary mb-2">
            Citabilité par page (les plus faibles d&apos;abord)
          </h3>
          <div className="space-y-2">
            {data.pageScores.map((p) => (
              <PageRow key={p.url} p={p} />
            ))}
          </div>
        </section>
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
