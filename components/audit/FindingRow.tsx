'use client'

import { useState } from 'react'
import type { Finding } from '@/lib/types'
import { EFFORT_LABEL, IMPACT_LABEL, SEVERITY_LABEL } from '@/lib/design'

interface FindingRowProps {
  finding: Finding
  index: number
}

const SEV_DOT: Record<Finding['severity'], string> = {
  critical: 'var(--status-critical-accent)',
  warning: 'var(--status-warning-accent)',
  ok: 'var(--status-ok-accent)',
  info: 'var(--status-info-accent)',
  missing: 'var(--status-missing-accent)',
}

const IMPACT_DOT: Record<NonNullable<Finding['impact']>, string> = {
  high: 'var(--status-critical-accent)',
  medium: 'var(--status-warning-accent)',
  low: 'var(--status-info-accent)',
}

export function FindingRow({ finding, index }: FindingRowProps) {
  const [open, setOpen] = useState(false)
  const f = finding

  return (
    <div className="border-b border-[var(--border-subtle)] last:border-0">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full grid grid-cols-[40px_140px_1fr_100px_100px_24px] items-center gap-3 px-4 py-2.5 text-left hover:bg-bg-elevated transition-colors"
      >
        <span className="text-xs tabular-nums text-text-tertiary">
          {String(index + 1).padStart(2, '0')}
        </span>
        <span className="flex items-center gap-2">
          <span
            className="w-1.5 h-1.5 rounded-full flex-shrink-0"
            style={{ background: SEV_DOT[f.severity] }}
          />
          <span className="text-xs font-medium text-text-secondary">
            {SEVERITY_LABEL[f.severity]}
          </span>
        </span>
        <span className="text-sm text-text-primary leading-snug truncate">
          {f.title}
        </span>
        <span className="flex items-center gap-1.5">
          {f.impact && (
            <>
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{ background: IMPACT_DOT[f.impact] }}
              />
              <span className="text-xs text-text-secondary">
                {IMPACT_LABEL[f.impact]}
              </span>
            </>
          )}
        </span>
        <span className="text-xs text-text-secondary">
          {f.effort ? EFFORT_LABEL[f.effort] : ''}
        </span>
        <span
          className="text-xs text-text-tertiary transition-transform"
          style={{ transform: open ? 'rotate(90deg)' : 'rotate(0)' }}
        >
          ›
        </span>
      </button>

      {open && (
        <div className="px-4 pb-5 pt-1 bg-bg-elevated/40 grid grid-cols-[40px_140px_1fr] gap-3">
          <div />
          <div />
          <div className="space-y-4 max-w-3xl">
            <p className="text-sm text-text-secondary leading-relaxed">
              {f.description}
            </p>

            {f.evidence && (
              <Block label="Extrait constaté">
                <pre className="font-mono text-xs text-text-secondary bg-bg-surface border border-[var(--border-subtle)] rounded-md px-3 py-2 whitespace-pre-wrap break-words">
                  {f.evidence}
                </pre>
              </Block>
            )}

            {f.recommendation && (
              <Block label="Recommandation" tone="primary">
                <p className="text-sm text-text-primary leading-relaxed">
                  {f.recommendation}
                </p>
              </Block>
            )}

            {f.actions && f.actions.length > 0 && (
              <Block label="Actions techniques" tone="primary">
                <ol className="space-y-1.5">
                  {f.actions.map((a, i) => (
                    <li
                      key={i}
                      className="flex gap-2.5 text-sm text-text-primary leading-snug"
                    >
                      <span className="text-xs tabular-nums text-text-tertiary mt-[3px] flex-shrink-0 w-5">
                        {String(i + 1).padStart(2, '0')}
                      </span>
                      <span>{a}</span>
                    </li>
                  ))}
                </ol>
              </Block>
            )}

            {f.reference && (
              <div className="text-xs text-text-tertiary">
                Référence :{' '}
                <a
                  href={f.reference}
                  target="_blank"
                  rel="noreferrer"
                  className="font-mono text-primary hover:underline underline-offset-2 break-all"
                >
                  {f.reference}
                </a>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function Block({
  label,
  tone = 'default',
  children,
}: {
  label: string
  tone?: 'default' | 'primary'
  children: React.ReactNode
}) {
  return (
    <div>
      <div
        className={`text-[11px] uppercase tracking-wider font-medium mb-1.5 ${
          tone === 'primary' ? 'text-primary' : 'text-text-tertiary'
        }`}
      >
        {label}
      </div>
      {children}
    </div>
  )
}
