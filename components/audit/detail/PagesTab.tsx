'use client'

import { useMemo, useState } from 'react'
import type { AuditResult } from '@/lib/types'
import { useDebouncedValue } from '@/lib/useDebouncedValue'
import { PageSheet } from '../PageSheet'
import { EmptyState, SectionHeader } from './shared'

export function PagesTab({ pages }: { pages: NonNullable<AuditResult['pages']> }) {
  const [selectedUrl, setSelectedUrl] = useState<string | null>(pages[0]?.url ?? null)
  const [filterInput, setFilterInput] = useState('')
  const filter = useDebouncedValue(filterInput, 200)

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase()
    if (!q) return pages
    return pages.filter(
      (p) => p.url.toLowerCase().includes(q) || (p.title || '').toLowerCase().includes(q),
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
                value={filterInput}
                onChange={(e) => setFilterInput(e.target.value)}
                className="w-full h-8 px-2 text-xs bg-bg-elevated border border-[var(--border-subtle)] rounded text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-primary"
              />
            </div>
            <ul className="overflow-y-auto flex-1 max-h-[60vh] lg:max-h-none">
              {filtered.length === 0 ? (
                <li className="px-3 py-4 text-xs text-text-tertiary">Aucune page ne correspond.</li>
              ) : (
                filtered.map((p) => {
                  const isActive = p.url === selected?.url
                  const accent = p.status === 'improve' ? 'warning' : p.status
                  return (
                    <li key={p.url}>
                      <button
                        type="button"
                        onClick={() => setSelectedUrl(p.url)}
                        className={`w-full text-left px-3 py-2 border-l-[3px] transition-colors flex items-start gap-2 ${
                          isActive ? 'bg-bg-elevated' : 'hover:bg-bg-elevated'
                        }`}
                        style={{ borderLeftColor: `var(--status-${accent}-accent)` }}
                      >
                        <span
                          className="mt-1 inline-block w-1.5 h-1.5 rounded-full flex-shrink-0"
                          style={{ backgroundColor: `var(--status-${accent}-accent)` }}
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
