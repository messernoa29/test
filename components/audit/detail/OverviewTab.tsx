'use client'

import type { AuditResult, AuditSection } from '@/lib/types'
import { ScoreBar } from '@/components/ui/ScoreBar'
import { scoreHexColor } from '@/lib/design'
import { MiniStat, SectionHeader } from './shared'

export function OverviewTab({
  audit,
  onOpenSection,
}: {
  audit: AuditResult
  onOpenSection: (section: AuditSection) => void
}) {
  const wins = (audit.quickWins ?? []).filter(
    (w): w is string => typeof w === 'string' && w.trim().length > 0,
  )
  const cov = audit.crawlCoverage
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
          {cov.crawledPageCount} page{cov.crawledPageCount > 1 ? 's' : ''} analysée
          {cov.crawledPageCount > 1 ? 's' : ''}
          {cov.discoveredUrlCount > cov.crawledPageCount
            ? ` sur ${cov.discoveredUrlCount} URLs trouvées`
            : ''}
          {' · '}profondeur demandée : {cov.requestedMaxPages} pages.
          {cov.cappedByLimit
            ? ` Le site a plus de pages que la limite — relancez avec une profondeur supérieure pour tout couvrir.`
            : cov.cappedBySite
              ? ` Le site n'a pas plus de pages : couverture complète.`
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

      <section>
        <SectionHeader title="Scores par domaine" sub="6 axes analysés" />
        <div className="border border-[var(--border-subtle)] rounded-md overflow-hidden bg-bg-surface">
          <div className="grid grid-cols-[1.4fr_70px_1fr_1.8fr_90px] bg-bg-elevated border-b border-[var(--border-subtle)]">
            {['Axe', 'Score', 'Progression', 'Verdict', 'Points'].map((h) => (
              <div
                key={h}
                className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary px-4 py-2.5"
              >
                {h}
              </div>
            ))}
          </div>
          {audit.sections.map((s) => (
            <button
              key={s.section}
              onClick={() => onOpenSection(s.section)}
              className="w-full grid grid-cols-[1.4fr_70px_1fr_1.8fr_90px] border-b border-[var(--border-subtle)] last:border-0 items-center hover:bg-bg-elevated text-left transition-colors"
            >
              <div className="text-sm font-medium text-text-primary px-4 py-3">{s.title}</div>
              <div
                className="text-lg font-semibold tabular-nums leading-none px-4 py-3"
                style={{ color: scoreHexColor(s.score) }}
              >
                {s.score}
              </div>
              <div className="px-4 py-3">
                <ScoreBar score={s.score} height={6} />
              </div>
              <div className="text-xs text-text-secondary px-4 py-3 leading-snug">{s.verdict}</div>
              <div className="text-xs tabular-nums text-text-secondary px-4 py-3">
                {s.findings.length}
              </div>
            </button>
          ))}
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
    </div>
  )
}
