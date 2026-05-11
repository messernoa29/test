'use client'

import { useMemo, useState } from 'react'
import type { AuditResult } from '@/lib/types'
import { DriftView } from './DriftView'
import { TechnicalCrawlTab } from './TechnicalCrawlTab'
import { VisibilityTab } from './VisibilityTab'
import { GeoTab } from './GeoTab'
import { OverviewTab } from './detail/OverviewTab'
import { PagesTab } from './detail/PagesTab'
import { MissingTab } from './detail/MissingTab'

// Axis-by-axis content now lives inside OverviewTab as accordions, so there
// are no per-axis tabs anymore — just the cross-cutting views.
type TabId = 'overview' | 'pages' | 'crawl' | 'visibility' | 'geo' | 'missing' | 'compare'

interface Props {
  audit: AuditResult
}

export function AuditDetailView({ audit }: Props) {
  const tabs: { id: TabId; label: string; count?: number }[] = useMemo(() => {
    const t: { id: TabId; label: string; count?: number }[] = [
      { id: 'overview', label: "Vue d'ensemble" },
    ]
    if ((audit.pages?.length ?? 0) > 0) {
      t.push({ id: 'pages', label: 'Pages', count: audit.pages!.length })
    }
    if ((audit.technicalCrawl?.pagesCrawled ?? 0) > 0) {
      t.push({
        id: 'crawl',
        label: 'Crawl technique',
        count: audit.technicalCrawl!.pagesCrawled,
      })
    }
    const vis = audit.visibilityEstimate
    if (vis && (vis.topKeywords.length > 0 || vis.opportunities.length > 0)) {
      t.push({ id: 'visibility', label: 'Visibilité', count: vis.topKeywords.length })
    }
    if (audit.geoAudit && audit.geoAudit.pageScores.length > 0) {
      t.push({ id: 'geo', label: 'GEO (IA)', count: audit.geoAudit.averagePageScore })
    }
    if ((audit.missingPages?.length ?? 0) > 0) {
      t.push({
        id: 'missing',
        label: 'Pages manquantes',
        count: audit.missingPages!.length,
      })
    }
    t.push({ id: 'compare', label: 'Comparaison' })
    return t
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
        {active === 'overview' && <OverviewTab audit={audit} />}
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
        {active === 'missing' && <MissingTab pages={audit.missingPages ?? []} />}
        {active === 'compare' && <DriftView currentId={audit.id} domain={audit.domain} />}
      </div>
    </div>
  )
}
