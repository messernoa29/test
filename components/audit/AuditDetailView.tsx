'use client'

import { useMemo, useState } from 'react'
import type { AuditResult, AuditSection, SectionResult } from '@/lib/types'
import { ScoreBar } from '@/components/ui/ScoreBar'
import { scoreHexColor } from '@/lib/design'
import { DriftView } from './DriftView'
import { FindingRow } from './FindingRow'
import { PageSheet } from './PageSheet'
import { MissingPagesTable } from './MissingPagesTable'
import { TechnicalCrawlTab } from './TechnicalCrawlTab'
import { VisibilityTab } from './VisibilityTab'
import { GeoTab } from './GeoTab'

type TabId =
  | 'overview'
  | AuditSection
  | 'pages'
  | 'crawl'
  | 'visibility'
  | 'geo'
  | 'missing'
  | 'compare'

interface Props {
  audit: AuditResult
}

export function AuditDetailView({ audit }: Props) {
  const tabs: { id: TabId; label: string; count?: number }[] = useMemo(() => {
    const base: { id: TabId; label: string; count?: number }[] = [
      { id: 'overview', label: "Vue d'ensemble" },
      ...audit.sections.map((s) => ({
        id: s.section as TabId,
        label: s.title,
        count: s.findings.length,
      })),
      { id: 'pages', label: 'Pages', count: audit.pages?.length ?? 0 },
      {
        id: 'crawl',
        label: 'Crawl technique',
        count: audit.technicalCrawl?.pagesCrawled ?? 0,
      },
      {
        id: 'visibility',
        label: 'Visibilité (est.)',
        count: audit.visibilityEstimate?.topKeywords?.length ?? 0,
      },
      {
        id: 'geo',
        label: 'GEO (IA)',
        count: audit.geoAudit?.averagePageScore ?? 0,
      },
      {
        id: 'missing',
        label: 'Pages manquantes',
        count: audit.missingPages?.length ?? 0,
      },
      { id: 'compare', label: 'Comparaison' },
    ]
    return base
  }, [audit])

  const [active, setActive] = useState<TabId>('overview')

  return (
    <div>
      <nav className="sticky top-14 z-[5] bg-bg-surface border-b border-[var(--border-subtle)]">
        <div className="max-w-6xl mx-auto px-8 flex overflow-x-auto">
          {tabs.map((tab) => {
            const isActive = active === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => setActive(tab.id)}
                className={`flex items-center gap-2 px-3 py-3 text-sm whitespace-nowrap transition-colors border-b-2 ${
                  isActive
                    ? 'text-primary border-primary font-medium'
                    : 'text-text-secondary border-transparent hover:text-text-primary'
                }`}
              >
                <span>{tab.label}</span>
                {typeof tab.count === 'number' && (
                  <span
                    className={`text-[11px] tabular-nums px-1.5 py-0.5 rounded ${
                      isActive
                        ? 'bg-[var(--primary-bg)] text-primary'
                        : 'bg-bg-elevated text-text-tertiary'
                    }`}
                  >
                    {tab.count}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </nav>

      <div className="max-w-6xl mx-auto px-8 py-8">
        {active === 'overview' && <OverviewTab audit={audit} onOpenSection={setActive} />}
        {audit.sections.map((s) =>
          active === s.section ? <AxisTab key={s.section} section={s} /> : null,
        )}
        {active === 'pages' && <PagesTab pages={audit.pages ?? []} />}
        {active === 'crawl' && (
          <TechnicalCrawlTab
            data={audit.technicalCrawl}
            cultural={audit.culturalAudit}
            programmatic={audit.programmaticAudit}
          />
        )}
        {active === 'visibility' && (
          <VisibilityTab data={audit.visibilityEstimate} sxo={audit.sxoAudit} />
        )}
        {active === 'geo' && <GeoTab data={audit.geoAudit} />}
        {active === 'missing' && (
          <MissingTab pages={audit.missingPages ?? []} />
        )}
        {active === 'compare' && (
          <DriftView currentId={audit.id} domain={audit.domain} />
        )}
      </div>
    </div>
  )
}

function OverviewTab({
  audit,
  onOpenSection,
}: {
  audit: AuditResult
  onOpenSection: (tab: TabId) => void
}) {
  return (
    <div className="space-y-10">
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
          <MiniStat
            label="Points critiques"
            value={audit.criticalCount}
            tone="critical"
          />
          <MiniStat
            label="Avertissements"
            value={audit.warningCount}
            tone="warning"
          />
          <MiniStat
            label="Pages analysées"
            value={audit.pages?.length ?? 0}
            tone="default"
          />
          <MiniStat
            label="Pages manquantes"
            value={audit.missingPages?.length ?? 0}
            tone="default"
          />
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
              <div className="text-sm font-medium text-text-primary px-4 py-3">
                {s.title}
              </div>
              <div
                className="text-lg font-semibold tabular-nums leading-none px-4 py-3"
                style={{ color: scoreHexColor(s.score) }}
              >
                {s.score}
              </div>
              <div className="px-4 py-3">
                <ScoreBar score={s.score} height={6} />
              </div>
              <div className="text-xs text-text-secondary px-4 py-3 leading-snug">
                {s.verdict}
              </div>
              <div className="text-xs tabular-nums text-text-secondary px-4 py-3">
                {s.findings.length}
              </div>
            </button>
          ))}
        </div>
      </section>

      {(() => {
        const wins = (audit.quickWins ?? []).filter(
          (w): w is string => typeof w === 'string' && w.trim().length > 0,
        )
        if (wins.length === 0) return null
        return (
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
                  <span className="text-sm text-text-primary leading-relaxed">
                    {w}
                  </span>
                </div>
              ))}
            </div>
          </section>
        )
      })()}
    </div>
  )
}

function AxisTab({ section }: { section: SectionResult }) {
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

      <FindingsTable findings={section.findings} />
    </div>
  )
}

function FindingsTable({ findings }: { findings: SectionResult['findings'] }) {
  if (findings.length === 0) {
    return (
      <div className="border border-dashed border-[var(--border-default)] rounded-md p-10 text-center text-sm text-text-tertiary">
        Aucun point remonté sur cet axe.
      </div>
    )
  }
  return (
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
      {findings.map((f, i) => (
        <FindingRow key={i} finding={f} index={i} />
      ))}
    </div>
  )
}

function PagesTab({ pages }: { pages: NonNullable<AuditResult['pages']> }) {
  const [selectedUrl, setSelectedUrl] = useState<string | null>(
    pages[0]?.url ?? null,
  )
  const [filter, setFilter] = useState('')

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase()
    if (!q) return pages
    return pages.filter(
      (p) =>
        p.url.toLowerCase().includes(q) ||
        (p.title || '').toLowerCase().includes(q),
    )
  }, [pages, filter])

  const selected = pages.find((p) => p.url === selectedUrl) ?? pages[0] ?? null

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Analyse page par page"
        sub={
          pages.length > 0
            ? `${pages.length} pages analysées`
            : 'Aucune analyse page par page disponible'
        }
      />
      {pages.length === 0 ? (
        <EmptyState message="L'analyse page par page n'a pas pu être produite pour cet audit. Relancez l'analyse depuis l'en-tête ou réessayez plus tard." />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-5">
          <aside className="bg-bg-surface border border-[var(--border-subtle)] rounded-md overflow-hidden lg:sticky lg:top-4 lg:self-start lg:max-h-[calc(100vh-2rem)] flex flex-col">
            <div className="px-3 py-2 border-b border-[var(--border-subtle)]">
              <input
                type="search"
                placeholder="Filtrer par URL ou titre"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="w-full h-8 px-2 text-xs bg-bg-elevated border border-[var(--border-subtle)] rounded text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-primary"
              />
            </div>
            <ul className="overflow-y-auto flex-1 max-h-[60vh] lg:max-h-none">
              {filtered.length === 0 ? (
                <li className="px-3 py-4 text-xs text-text-tertiary">
                  Aucune page ne correspond.
                </li>
              ) : (
                filtered.map((p) => {
                  const isActive = p.url === selected?.url
                  const accent =
                    p.status === 'improve' ? 'warning' : p.status
                  return (
                    <li key={p.url}>
                      <button
                        type="button"
                        onClick={() => setSelectedUrl(p.url)}
                        className={`w-full text-left px-3 py-2 border-l-[3px] transition-colors flex items-start gap-2 ${
                          isActive
                            ? 'bg-bg-elevated'
                            : 'hover:bg-bg-elevated'
                        }`}
                        style={{
                          borderLeftColor: `var(--status-${accent}-accent)`,
                        }}
                      >
                        <span
                          className="mt-1 inline-block w-1.5 h-1.5 rounded-full flex-shrink-0"
                          style={{
                            backgroundColor: `var(--status-${accent}-accent)`,
                          }}
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block text-xs font-medium text-text-primary truncate">
                            {p.title || p.url}
                          </span>
                          <span className="block font-mono text-[10px] text-text-tertiary truncate">
                            {p.url}
                          </span>
                        </span>
                      </button>
                    </li>
                  )
                })
              )}
            </ul>
          </aside>
          <div>
            {selected ? (
              <PageSheet key={selected.url} page={selected} />
            ) : (
              <EmptyState message="Sélectionnez une page dans la liste." />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function MissingTab({ pages }: { pages: NonNullable<AuditResult['missingPages']> }) {
  return (
    <div className="space-y-5">
      <SectionHeader
        title="Pages stratégiques manquantes"
        sub={
          pages.length > 0
            ? `${pages.length} pages à créer`
            : 'Aucune page manquante détectée'
        }
      />
      {pages.length === 0 ? (
        <EmptyState message="L'IA n'a identifié aucune page stratégique manquante pour ce site, ou la détection n'a pas pu aboutir." />
      ) : (
        <MissingPagesTable pages={pages} />
      )}
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="border border-dashed border-[var(--border-default)] rounded-md p-10 text-center bg-bg-surface">
      <p className="text-sm text-text-tertiary max-w-md mx-auto">{message}</p>
    </div>
  )
}

function MiniStat({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone: 'critical' | 'warning' | 'default'
}) {
  const color =
    tone === 'critical'
      ? 'var(--status-critical-accent)'
      : tone === 'warning'
        ? 'var(--status-warning-accent)'
        : 'var(--text-primary)'
  return (
    <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md p-4">
      <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-2">
        {label}
      </div>
      <div
        className="text-2xl font-semibold tabular-nums leading-none"
        style={{ color }}
      >
        {value}
      </div>
    </div>
  )
}

function SectionHeader({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="mb-4">
      <h2 className="text-base font-semibold text-text-primary">{title}</h2>
      {sub && <p className="text-xs text-text-tertiary mt-0.5">{sub}</p>}
    </div>
  )
}
