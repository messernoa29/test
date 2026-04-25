'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { getAiVisibilityCheck } from '@/lib/api'
import type {
  AiQueryResult,
  AiVisibilityCheck,
  AiVisibilityReport,
} from '@/lib/types'

interface Props {
  initial: AiVisibilityCheck
}

export function AiVisibilityDetail({ initial }: Props) {
  const [check, setCheck] = useState<AiVisibilityCheck>(initial)

  useEffect(() => {
    if (check.status === 'done' || check.status === 'failed') return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const tick = async () => {
      try {
        const next = await getAiVisibilityCheck(check.id)
        if (!cancelled) setCheck(next)
        if (next.status === 'done' || next.status === 'failed') return
      } catch {
        // keep polling
      }
      if (!cancelled) timer = setTimeout(tick, 5000)
    }
    timer = setTimeout(tick, 5000)
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [check.id, check.status])

  const subtitle =
    check.targetName ?? `${check.queries.length} requêtes`

  return (
    <div>
      <div className="border-b border-[var(--border-subtle)] bg-bg-surface">
        <div className="max-w-5xl mx-auto px-8 py-5 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-xs text-text-tertiary mb-1">
              AI Visibility · {check.createdAt.slice(0, 10)}
            </p>
            <h1 className="text-xl font-semibold text-text-primary truncate">
              {check.targetDomain}
            </h1>
            <p className="text-xs text-text-tertiary mt-0.5">{subtitle}</p>
          </div>
          <Link
            href="/ai-visibility"
            className="inline-flex h-9 px-3 items-center bg-bg-surface text-text-secondary border border-[var(--border-default)] rounded-md font-medium text-sm hover:bg-bg-elevated hover:text-text-primary transition-colors"
          >
            ← Toutes les vérifications
          </Link>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-8 py-8 space-y-8">
        {check.status === 'failed' && (
          <div className="border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] rounded-md p-4">
            <div className="text-[11px] uppercase tracking-wider font-medium text-[var(--status-critical-text)] mb-1">
              Échec
            </div>
            <p className="text-sm text-text-primary">{check.error ?? 'Erreur inconnue.'}</p>
          </div>
        )}

        {check.status !== 'done' && (
          <div className="border border-dashed border-[var(--border-default)] rounded-md p-8 text-center bg-bg-surface">
            <p className="text-sm text-text-secondary">
              Sondage en cours, vous pouvez quitter la page.
            </p>
          </div>
        )}

        {check.report && <ReportSummary report={check.report} />}

        {check.probes.length > 0 && (
          <ProbesView probes={check.probes} domain={check.targetDomain} />
        )}
      </div>
    </div>
  )
}

function ReportSummary({ report }: { report: AiVisibilityReport }) {
  return (
    <section className="space-y-4">
      <h2 className="text-base font-semibold text-text-primary">
        Synthèse IA
      </h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <RateCard
          label="Taux de citation"
          value={report.citationRate}
          hint="% requêtes où votre domaine apparaît dans les sources"
        />
        <RateCard
          label="Taux de mention"
          value={report.mentionRate}
          hint="% requêtes où votre marque est nommée dans la réponse"
        />
      </div>

      {report.summary && (
        <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md p-5">
          <div className="text-[11px] uppercase tracking-wider font-medium text-primary mb-2">
            Résumé
          </div>
          <p className="text-sm text-text-primary leading-relaxed">{report.summary}</p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {report.strengths.length > 0 && (
          <Block label="Forces" items={report.strengths} tone="ok" />
        )}
        {report.weaknesses.length > 0 && (
          <Block
            label="Faiblesses"
            items={report.weaknesses}
            tone="critical"
          />
        )}
      </div>

      {report.actions.length > 0 && (
        <Block
          label="Actions GEO prioritaires"
          items={report.actions}
          tone="warning"
          numbered
        />
      )}
    </section>
  )
}

function RateCard({
  label,
  value,
  hint,
}: {
  label: string
  value: number
  hint: string
}) {
  const pct = Math.round((value || 0) * 100)
  const color =
    pct >= 60
      ? 'var(--status-ok-accent)'
      : pct >= 30
        ? 'var(--status-warning-accent)'
        : 'var(--status-critical-accent)'
  return (
    <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md p-4">
      <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-2">
        {label}
      </div>
      <div className="flex items-baseline gap-2 mb-1">
        <span
          className="text-3xl font-semibold tabular-nums leading-none"
          style={{ color }}
        >
          {pct}%
        </span>
      </div>
      <div className="text-xs text-text-tertiary mt-1">{hint}</div>
    </div>
  )
}

function Block({
  label,
  items,
  tone,
  numbered = false,
}: {
  label: string
  items: string[]
  tone: 'ok' | 'critical' | 'warning' | 'primary'
  numbered?: boolean
}) {
  const color = {
    ok: 'var(--status-ok-accent)',
    critical: 'var(--status-critical-accent)',
    warning: 'var(--status-warning-accent)',
    primary: 'var(--primary)',
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

function ProbesView({
  probes,
  domain,
}: {
  probes: AiQueryResult[]
  domain: string
}) {
  return (
    <section className="space-y-3">
      <h2 className="text-base font-semibold text-text-primary">
        Détail par requête
      </h2>
      <div className="space-y-3">
        {probes.map((p, i) => (
          <ProbeCard key={i} probe={p} domain={domain} />
        ))}
      </div>
    </section>
  )
}

function ProbeCard({
  probe,
  domain,
}: {
  probe: AiQueryResult
  domain: string
}) {
  const tone = probe.cited ? 'ok' : probe.error ? 'critical' : 'warning'
  const tag = probe.cited
    ? 'Cité'
    : probe.targetMentioned
      ? 'Mentionné'
      : probe.error
        ? 'Erreur'
        : 'Non cité'
  const accent = {
    ok: 'var(--status-ok-accent)',
    critical: 'var(--status-critical-accent)',
    warning: 'var(--status-warning-accent)',
  }[tone]
  return (
    <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md overflow-hidden">
      <div className="px-5 py-3 flex items-baseline justify-between border-b border-[var(--border-subtle)]">
        <div className="text-sm font-medium text-text-primary">
          {probe.query}
        </div>
        <span
          className="text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded"
          style={{
            color: accent,
            background:
              tone === 'ok'
                ? 'var(--status-ok-bg)'
                : tone === 'critical'
                  ? 'var(--status-critical-bg)'
                  : 'var(--status-warning-bg)',
          }}
        >
          {tag}
        </span>
      </div>
      <div className="px-5 py-3">
        {probe.error ? (
          <p className="text-xs text-[var(--status-critical-text)]">{probe.error}</p>
        ) : (
          <>
            {probe.answer && (
              <p className="text-sm text-text-secondary leading-relaxed whitespace-pre-line">
                {probe.answer.slice(0, 800)}
                {probe.answer.length > 800 ? '…' : ''}
              </p>
            )}
            {probe.citations.length > 0 && (
              <div className="mt-3">
                <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-1.5">
                  Sources citées ({probe.citations.length})
                </div>
                <ul className="space-y-1">
                  {probe.citations.map((c, j) => {
                    const isOurs =
                      c.url && c.url.toLowerCase().includes(domain.toLowerCase())
                    return (
                      <li
                        key={j}
                        className={`text-xs font-mono truncate ${
                          isOurs
                            ? 'text-primary font-semibold'
                            : 'text-text-tertiary'
                        }`}
                      >
                        {c.url}
                      </li>
                    )
                  })}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
