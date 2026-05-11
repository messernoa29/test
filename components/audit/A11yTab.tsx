'use client'

import type { AccessibilityAudit, ResponsiveAudit } from '@/lib/types'

interface Props {
  a11y?: AccessibilityAudit
  responsive?: ResponsiveAudit
}

export function A11yTab({ a11y, responsive }: Props) {
  if (!a11y && !responsive) {
    return (
      <div className="text-sm text-text-tertiary py-8">
        Audit accessibilité/responsive non disponible (audit antérieur — relancez
        l&apos;analyse).
      </div>
    )
  }
  return (
    <div className="space-y-8">
      {a11y && <AccessibilitySection a={a11y} />}
      {responsive && <ResponsiveSection r={responsive} />}
    </div>
  )
}

function scoreTone(n: number) {
  return n >= 80 ? 'ok' : n >= 50 ? 'warn' : 'bad'
}
function toneClass(t: string) {
  return t === 'ok'
    ? 'text-[var(--status-ok-text)]'
    : t === 'warn'
      ? 'text-[var(--status-warning-text)]'
      : 'text-[var(--status-critical-text)]'
}

function AccessibilitySection({ a }: { a: AccessibilityAudit }) {
  const stats: { label: string; value: number | string; warn?: boolean }[] = [
    { label: 'Pages sans <html lang>', value: a.pagesWithoutLang, warn: a.pagesWithoutLang > 0 },
    { label: 'Images sans alt (total)', value: a.imagesWithoutAlt, warn: a.imagesWithoutAlt > 0 },
    { label: 'Champs sans label (total)', value: a.formInputsWithoutLabel, warn: a.formInputsWithoutLabel > 0 },
    { label: 'Liens non descriptifs', value: a.linksGeneric, warn: a.linksGeneric > 0 },
    { label: '"Boutons" en <div>', value: a.buttonsAsDiv, warn: a.buttonsAsDiv > 0 },
    { label: 'Pages sans <main>', value: a.pagesWithoutLandmarks, warn: a.pagesWithoutLandmarks > 0 },
    { label: 'Pages — titres mal hiérarchisés', value: a.pagesWithHeadingIssues, warn: a.pagesWithHeadingIssues > 0 },
    { label: 'Pages — tabindex positif', value: a.pagesWithPositiveTabindex, warn: a.pagesWithPositiveTabindex > 0 },
  ]
  return (
    <section className="space-y-4">
      <div className="flex items-baseline gap-3">
        <h3 className="text-base font-semibold text-text-primary">Accessibilité (WCAG)</h3>
        <span className={`text-2xl font-semibold tabular-nums ${toneClass(scoreTone(a.averageScore))}`}>
          {a.averageScore}/100
        </span>
        <span className="text-xs text-text-tertiary">score automatique moyen</span>
      </div>

      {a.llmVerdict && (
        <div className="border border-[var(--border-subtle)] rounded-md bg-bg-surface p-4">
          <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-1.5">
            Verdict (analyse IA, {a.llmPagesEvaluated} page{a.llmPagesEvaluated > 1 ? 's' : ''})
          </div>
          <p className="text-sm text-text-secondary leading-relaxed mb-3">{a.llmVerdict}</p>
          {a.llmTopFixes.length > 0 && (
            <>
              <div className="text-[11px] uppercase tracking-wider font-medium text-primary mb-1.5">
                Actions prioritaires
              </div>
              <ol className="space-y-1.5">
                {a.llmTopFixes.map((f, i) => (
                  <li key={i} className="flex gap-2.5 text-sm text-text-primary leading-snug">
                    <span className="text-xs tabular-nums text-text-tertiary mt-[3px] w-5 flex-shrink-0">
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <span>{f}</span>
                  </li>
                ))}
              </ol>
            </>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {stats.map((s) => (
          <div key={s.label} className="px-3 py-2 rounded-md border border-[var(--border-subtle)] bg-bg-surface">
            <div className="text-[10px] uppercase tracking-wider text-text-tertiary mb-1 leading-tight">{s.label}</div>
            <div className={`text-lg font-semibold tabular-nums ${s.warn ? 'text-[var(--status-critical-text)]' : 'text-text-primary'}`}>
              {s.value}
            </div>
          </div>
        ))}
      </div>

      {a.pageScores.length > 0 && (
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-text-secondary mb-2">
            Pages les moins accessibles
          </div>
          <div className="space-y-2">
            {a.pageScores.slice(0, 15).map((p) => (
              <div key={p.url} className="border border-[var(--border-subtle)] rounded-md bg-bg-surface p-3">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <a href={p.url} target="_blank" rel="noreferrer" className="font-mono text-xs text-text-secondary hover:text-primary break-all">
                    {p.url}
                  </a>
                  <span className={`text-sm font-semibold tabular-nums ${toneClass(scoreTone(p.score))}`}>{p.score}/100</span>
                </div>
                {p.issues.length > 0 && (
                  <ul className="space-y-0.5 text-[11px] text-text-secondary">
                    {p.issues.map((i, idx) => (
                      <li key={idx}>· {i}</li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

function ResponsiveSection({ r }: { r: ResponsiveAudit }) {
  return (
    <section className="space-y-4">
      <h3 className="text-base font-semibold text-text-primary">Responsive / mobile</h3>
      <p className="text-xs text-text-secondary">{r.summary}</p>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <Stat label="Pages sans viewport" value={r.pagesWithoutViewport} warn={r.pagesWithoutViewport > 0} />
        <Stat label="Pages bloquant le zoom" value={r.pagesBlockingZoom} warn={r.pagesBlockingZoom > 0} />
        <Stat label="Pages avec media queries" value={r.pagesWithMediaQueries} />
        <Stat label="Images responsive (srcset)" value={`${Math.round(r.imagesWithSrcsetRatio * 100)}%`} />
        <Stat label="Pages rendues (375/768/1280)" value={r.renderedPagesTested} />
        <Stat label="Pages — scroll horizontal" value={r.pagesWithHorizontalScroll} warn={r.pagesWithHorizontalScroll > 0} />
      </div>
      {r.renderedPagesTested === 0 && (
        <p className="text-xs text-text-tertiary">
          Le rendu navigateur n&apos;a pas été effectué (Playwright désactivé) — seuls
          les signaux statiques sont disponibles. Activez PLAYWRIGHT_ENABLED pour le test
          de débordement réel à 375/768/1280px.
        </p>
      )}
      {r.pageResults.some((p) => p.issues.length > 0) && (
        <div className="space-y-2">
          {r.pageResults.filter((p) => p.issues.length > 0).map((p) => (
            <div key={p.url} className="border border-[var(--border-subtle)] rounded-md bg-bg-surface p-3">
              <a href={p.url} target="_blank" rel="noreferrer" className="font-mono text-xs text-text-secondary hover:text-primary break-all block mb-1">
                {p.url}
              </a>
              <ul className="space-y-0.5 text-[11px] text-text-secondary">
                {p.issues.map((i, idx) => (
                  <li key={idx}>· {i}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

function Stat({ label, value, warn }: { label: string; value: number | string; warn?: boolean }) {
  return (
    <div className="px-3 py-2 rounded-md border border-[var(--border-subtle)] bg-bg-surface">
      <div className="text-[10px] uppercase tracking-wider text-text-tertiary mb-1 leading-tight">{label}</div>
      <div className={`text-lg font-semibold tabular-nums ${warn ? 'text-[var(--status-critical-text)]' : 'text-text-primary'}`}>
        {value}
      </div>
    </div>
  )
}
