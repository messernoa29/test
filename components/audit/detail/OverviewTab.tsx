'use client'

import { useState } from 'react'
import type { AuditResult, Finding, SectionResult } from '@/lib/types'
import { ScoreBar } from '@/components/ui/ScoreBar'
import { scoreHexColor } from '@/lib/design'
import { FindingRow } from '../FindingRow'
import { MiniStat, SectionHeader } from './shared'

const actionable = (findings: Finding[]): Finding[] =>
  findings.filter((f) => f.severity === 'critical' || f.severity === 'warning')

export function OverviewTab({ audit }: { audit: AuditResult }) {
  const wins = (audit.quickWins ?? []).filter(
    (w): w is string => typeof w === 'string' && w.trim().length > 0,
  )
  const cov = audit.crawlCoverage
  // Sections worth showing: at least one actionable finding.
  const sections = audit.sections.filter((s) => actionable(s.findings).length > 0)
  const cleanSections = audit.sections.filter((s) => actionable(s.findings).length === 0)

  return (
    <div className="space-y-10">
      {cov && cov.requestedMaxPages > 0 && (
        <div
          className={`px-4 py-2.5 rounded-md border text-xs ${
            cov.cappedByLimit
              ? 'border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] text-[var(--status-warning-text)]'
              : 'border-[var(--border-subtle)] bg-bg-surface text-text-secondary'
          }`}
        >
          <strong>Couverture du crawl :</strong>{' '}
          {cov.crawledPageCount} page{cov.crawledPageCount > 1 ? 's' : ''} crawlée
          {cov.crawledPageCount > 1 ? 's' : ''} techniquement
          {cov.discoveredUrlCount > cov.crawledPageCount
            ? ` sur ${cov.discoveredUrlCount} URLs trouvées`
            : ''}
          {cov.detailedPageCount > 0 && cov.detailedPageCount < cov.crawledPageCount
            ? ` · ${cov.detailedPageCount} analysées en détail par l'IA`
            : ''}
          {' · '}profondeur demandée : {cov.requestedMaxPages} pages.
          {cov.cappedByLimit
            ? ` Le site a plus de pages que la limite — relancez avec une profondeur supérieure pour un crawl technique complet.`
            : cov.cappedBySite
              ? ` Le site n'a pas plus de pages : crawl complet.`
              : ''}
        </div>
      )}

      <section className="grid grid-cols-1 md:grid-cols-[280px_1fr] gap-4 items-start">
        <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md p-5">
          <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-3">
            Score global
          </div>
          <div className="flex items-baseline gap-2 mb-1.5">
            <span
              className="text-5xl font-semibold tracking-tight leading-none tabular-nums"
              style={{ color: scoreHexColor(audit.globalScore) }}
            >
              {audit.globalScore}
            </span>
            <span className="text-base font-normal text-text-tertiary">/100</span>
          </div>
          <p className="text-sm text-text-secondary mb-3">{audit.globalVerdict}</p>
          <ScoreBar score={audit.globalScore} height={6} />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <MiniStat label="Points critiques" value={audit.criticalCount} tone="critical" />
          <MiniStat label="Avertissements" value={audit.warningCount} tone="warning" />
          <MiniStat label="Pages analysées" value={audit.pages?.length ?? 0} tone="default" />
          <MiniStat label="Pages manquantes" value={audit.missingPages?.length ?? 0} tone="default" />
        </div>
      </section>

      {wins.length > 0 && (
        <section>
          <SectionHeader title="Quick wins" sub="Actions à haute priorité" />
          <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md">
            {wins.map((w, i) => (
              <div
                key={i}
                className="flex items-start gap-3 px-5 py-3 border-b border-[var(--border-subtle)] last:border-0"
              >
                <span className="text-xs tabular-nums text-text-tertiary mt-[3px] w-5">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span className="text-sm text-text-primary leading-relaxed">{w}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <section>
        <SectionHeader
          title="Recommandations par axe"
          sub="Cliquez sur un axe pour dérouler les actions à faire"
        />
        {sections.length === 0 ? (
          <div className="border border-dashed border-[var(--border-default)] rounded-md p-8 text-center text-sm text-text-tertiary bg-bg-surface">
            Aucune recommandation actionnable — le site est globalement sain sur les 6 axes.
          </div>
        ) : (
          <div className="space-y-3">
            {sections.map((s) => (
              <AxisAccordion key={s.section} section={s} defaultOpen={sections.length <= 2} />
            ))}
          </div>
        )}
        {cleanSections.length > 0 && (
          <p className="mt-3 text-xs text-text-tertiary">
            Axes sans point à corriger :{' '}
            {cleanSections.map((s) => s.title).join(', ')}.
          </p>
        )}
      </section>
    </div>
  )
}

function AxisAccordion({
  section,
  defaultOpen = false,
}: {
  section: SectionResult
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  const acts = actionable(section.findings)
  const crit = acts.filter((f) => f.severity === 'critical').length
  const warn = acts.filter((f) => f.severity === 'warning').length
  // Show actionable findings first, then any "ok"/"info" notes.
  const ordered = [
    ...acts,
    ...section.findings.filter((f) => f.severity !== 'critical' && f.severity !== 'warning'),
  ]
  return (
    <div className="border border-[var(--border-subtle)] rounded-md bg-bg-surface overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-4 px-5 py-3.5 text-left hover:bg-bg-elevated transition-colors"
      >
        <span
          className="text-2xl font-semibold tabular-nums leading-none w-12 text-center flex-shrink-0"
          style={{ color: scoreHexColor(section.score) }}
        >
          {section.score}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium text-text-primary">{section.title}</span>
          <span className="block text-xs text-text-secondary leading-snug mt-0.5">
            {section.verdict}
          </span>
        </span>
        <span className="flex items-center gap-2 flex-shrink-0 text-xs">
          {crit > 0 && (
            <span className="px-1.5 py-0.5 rounded bg-[var(--status-critical-bg)] text-[var(--status-critical-text)] tabular-nums">
              {crit} critique{crit > 1 ? 's' : ''}
            </span>
          )}
          {warn > 0 && (
            <span className="px-1.5 py-0.5 rounded bg-[var(--status-warning-bg)] text-[var(--status-warning-text)] tabular-nums">
              {warn} à corriger
            </span>
          )}
        </span>
        <span
          className="text-text-tertiary transition-transform flex-shrink-0"
          style={{ transform: open ? 'rotate(90deg)' : 'rotate(0)' }}
        >
          ›
        </span>
      </button>
      {open && (
        <div className="border-t border-[var(--border-subtle)]">
          <div className="grid grid-cols-[40px_140px_1fr_100px_100px_24px] gap-3 px-4 py-2.5 bg-bg-elevated text-[11px] uppercase tracking-wider font-medium text-text-tertiary">
            <div>#</div>
            <div>Sévérité</div>
            <div>Point</div>
            <div>Impact</div>
            <div>Effort</div>
            <div />
          </div>
          {ordered.map((f, i) => (
            <FindingRow key={i} finding={f} index={i} />
          ))}
        </div>
      )}
    </div>
  )
}
