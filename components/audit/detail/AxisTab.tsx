'use client'

import type { SectionResult } from '@/lib/types'
import { ScoreBar } from '@/components/ui/ScoreBar'
import { scoreHexColor } from '@/lib/design'
import { FindingRow } from '../FindingRow'

export function AxisTab({ section }: { section: SectionResult }) {
  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-6">
        <div>
          <p className="text-xs text-text-tertiary mb-1">Axe d&apos;audit</p>
          <h1 className="text-xl font-semibold text-text-primary">{section.title}</h1>
          <p className="text-sm text-text-secondary mt-1">{section.verdict}</p>
        </div>
        <div className="text-right flex-shrink-0">
          <div className="flex items-baseline justify-end gap-1">
            <span
              className="text-4xl font-semibold tabular-nums leading-none"
              style={{ color: scoreHexColor(section.score) }}
            >
              {section.score}
            </span>
            <span className="text-sm text-text-tertiary">/100</span>
          </div>
          <div className="w-40 mt-2">
            <ScoreBar score={section.score} height={5} />
          </div>
        </div>
      </header>

      {section.findings.length === 0 ? (
        <div className="border border-dashed border-[var(--border-default)] rounded-md p-10 text-center text-sm text-text-tertiary">
          Aucun point remonté sur cet axe.
        </div>
      ) : (
        <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md overflow-hidden">
          <div className="grid grid-cols-[40px_140px_1fr_100px_100px_24px] gap-3 px-4 py-2.5 bg-bg-elevated border-b border-[var(--border-subtle)]">
            {['#', 'Sévérité', 'Titre', 'Impact', 'Effort', ''].map((h, i) => (
              <div
                key={i}
                className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary"
              >
                {h}
              </div>
            ))}
          </div>
          {section.findings.map((f, i) => (
            <FindingRow key={i} finding={f} index={i} />
          ))}
        </div>
      )}
    </div>
  )
}
