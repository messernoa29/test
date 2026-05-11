'use client'

import { useMemo, useState } from 'react'
import type {
  CulturalAuditSummary,
  ProgrammaticAuditSummary,
  TechnicalCrawlSummary,
  TechnicalPageRow,
} from '@/lib/types'
import { useDebouncedValue } from '@/lib/useDebouncedValue'

interface Props {
  data?: TechnicalCrawlSummary
  cultural?: CulturalAuditSummary
  programmatic?: ProgrammaticAuditSummary
}

type StatusFilter = 'all' | '2xx' | '3xx' | '4xx' | '5xx' | 'issues'

export function TechnicalCrawlTab({ data, cultural, programmatic }: Props) {
  const [filterInput, setFilterInput] = useState('')
  const filter = useDebouncedValue(filterInput, 200)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')

  const rows = data?.rows ?? []

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase()
    return rows.filter((r) => {
      if (q && !r.url.toLowerCase().includes(q)) return false
      const s = r.statusCode ?? 0
      switch (statusFilter) {
        case '2xx':
          return s >= 200 && s < 300
        case '3xx':
          return s >= 300 && s < 400
        case '4xx':
          return s >= 400 && s < 500
        case '5xx':
          return s >= 500 && s < 600
        case 'issues':
          return r.issues.length > 0
        default:
          return true
      }
    })
  }, [rows, filter, statusFilter])

  if (!data || data.pagesCrawled === 0) {
    return (
      <div className="text-sm text-text-tertiary py-8">
        Aucune donnée de crawl technique pour cet audit (audit antérieur à
        cette fonctionnalité — relancez l&apos;analyse).
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label="URLs crawlées" value={data.pagesCrawled} />
        <Stat label="Indexables" value={data.indexablePages} />
        <Stat label="Non-indexables" value={data.nonIndexablePages} />
        <Stat label="Profondeur max" value={`${data.maxDepth} clics`} />
      </div>

      {/* Status code breakdown */}
      <div className="flex flex-wrap gap-2 text-xs">
        {Object.entries(data.statusCounts)
          .sort()
          .map(([code, n]) => (
            <span
              key={code}
              className="px-2 py-1 rounded border border-[var(--border-subtle)] bg-bg-surface tabular-nums"
            >
              <span className={statusColor(code)}>{code}</span> · {n}
            </span>
          ))}
      </div>

      {/* Issue groups */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <IssueGroup title="Titres dupliqués" groups={data.duplicateTitles} />
        <IssueGroup
          title="Meta descriptions dupliquées"
          groups={data.duplicateMetaDescriptions}
        />
        <IssueList title="Pages sans <title>" urls={data.missingTitles} />
        <IssueList
          title="Pages sans meta description"
          urls={data.missingMetaDescriptions}
        />
        <IssueList title="Pages sans H1" urls={data.missingH1} />
        <IssueList
          title="Titres trop longs (> 60 car.)"
          urls={data.titleTooLong}
        />
        <IssueList
          title="Titres trop courts (< 30 car.)"
          urls={data.titleTooShort}
        />
        <IssueList
          title="Ratio texte/HTML faible (< 10%)"
          urls={data.lowTextRatioPages}
        />
        <IssueList
          title="Liens internes cassés (cibles 4xx/5xx)"
          urls={data.brokenInternalLinks}
        />
      </div>

      {/* Full table */}
      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <input
            type="search"
            placeholder="Filtrer par URL"
            value={filterInput}
            onChange={(e) => setFilterInput(e.target.value)}
            className="h-8 px-2 text-xs bg-bg-surface border border-[var(--border-subtle)] rounded text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-primary"
          />
          {(['all', '2xx', '3xx', '4xx', '5xx', 'issues'] as StatusFilter[]).map(
            (f) => (
              <button
                key={f}
                onClick={() => setStatusFilter(f)}
                className={`h-8 px-2 text-xs rounded border transition-colors ${
                  statusFilter === f
                    ? 'border-primary text-primary bg-[var(--primary-bg)]'
                    : 'border-[var(--border-subtle)] text-text-secondary hover:text-text-primary'
                }`}
              >
                {f === 'all' ? 'Tout' : f === 'issues' ? 'Avec problèmes' : f}
              </button>
            ),
          )}
          <span className="text-xs text-text-tertiary ml-auto">
            {filtered.length} / {rows.length} URLs
          </span>
        </div>
        <div className="overflow-x-auto border border-[var(--border-subtle)] rounded-md">
          <table className="w-full text-xs">
            <thead className="bg-bg-elevated text-text-tertiary">
              <tr>
                <th className="text-left px-2 py-1.5 font-medium">URL</th>
                <th className="px-2 py-1.5 font-medium">Code</th>
                <th className="px-2 py-1.5 font-medium">Prof.</th>
                <th className="px-2 py-1.5 font-medium">Idx</th>
                <th className="px-2 py-1.5 font-medium">Title</th>
                <th className="px-2 py-1.5 font-medium">Meta</th>
                <th className="px-2 py-1.5 font-medium">H1</th>
                <th className="px-2 py-1.5 font-medium">Mots</th>
                <th className="px-2 py-1.5 font-medium">Liens int/ext</th>
                <th className="px-2 py-1.5 font-medium">Img (sans alt)</th>
                <th className="text-left px-2 py-1.5 font-medium">Problèmes</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <Row key={r.url} r={r} />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Cultural adaptation (multilingual sites) */}
      {cultural?.isMultilingual && (
        <CulturalSection cultural={cultural} />
      )}

      {/* Programmatic SEO quality gates */}
      {programmatic?.isProgrammatic && (
        <ProgrammaticSection programmatic={programmatic} />
      )}
    </div>
  )
}

function ProgrammaticSection({
  programmatic,
}: {
  programmatic: ProgrammaticAuditSummary
}) {
  const gateColor = (g: string) =>
    g === 'PASS'
      ? 'text-[var(--status-ok-text)]'
      : g === 'WARNING'
        ? 'text-[var(--status-warning-text)]'
        : 'text-[var(--status-critical-text)]'
  const gateLabel = (g: string) =>
    g === 'PASS' ? 'OK' : g === 'WARNING' ? 'À renforcer' : 'Risque pénalité'
  return (
    <section>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary mb-2">
        Pages générées en masse (quality gates)
      </h3>
      <p className="text-xs text-text-tertiary mb-3">
        Groupes d&apos;URLs au même motif (pages ville, fiches templatées…).
        Google sanctionne le contenu généré à grande échelle sans valeur propre
        (Scaled Content Abuse, mars 2024).
      </p>
      <div className="space-y-3">
        {programmatic.groups.map((g) => (
          <div
            key={g.pattern}
            className="border border-[var(--border-subtle)] rounded-md bg-bg-surface p-3"
          >
            <div className="flex items-center justify-between gap-2 mb-1">
              <code className="text-xs text-text-primary">{g.pattern}</code>
              <span className={`text-xs font-medium ${gateColor(g.gate)}`}>
                {gateLabel(g.gate)}
              </span>
            </div>
            <div className="text-[11px] text-text-tertiary mb-1.5">
              {g.pageCount} pages · ~{g.avgWordCount} mots/page · contenu unique
              estimé {Math.round(g.uniquenessRatio * 100)}% (boilerplate{' '}
              {Math.round(g.boilerplateRatio * 100)}%)
            </div>
            {g.notes.length > 0 && (
              <ul className="space-y-0.5 text-[11px] text-text-secondary mb-1.5">
                {g.notes.map((n, i) => (
                  <li key={i}>· {n}</li>
                ))}
              </ul>
            )}
            <div className="text-[10px] font-mono text-text-tertiary break-all">
              {g.sampleUrls.slice(0, 4).join(' · ')}
              {g.sampleUrls.length > 4 && ' …'}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function CulturalSection({ cultural }: { cultural: CulturalAuditSummary }) {
  return (
    <section>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary mb-2">
        Adaptation culturelle (site multilingue)
      </h3>
      <p className="text-xs text-text-tertiary mb-3">
        Langues détectées : {cultural.detectedLocales.join(', ')}. On vérifie
        que les formats de date/nombre/devise et les CTA correspondent à chaque
        audience.
      </p>
      <div className="space-y-3">
        {cultural.locales.map((loc) => (
          <div
            key={loc.locale}
            className="border border-[var(--border-subtle)] rounded-md bg-bg-surface p-3"
          >
            <div className="flex items-center justify-between gap-2 mb-1.5">
              <span className="text-sm font-medium text-text-primary">
                {loc.label} <span className="text-text-tertiary">({loc.locale})</span>
              </span>
              <span
                className={`text-xs ${loc.pagesWithIssues > 0 ? 'text-[var(--status-warning-text)]' : 'text-[var(--status-ok-text)]'}`}
              >
                {loc.pagesWithIssues} / {loc.pagesCount} pages avec écart
              </span>
            </div>
            <div className="text-[11px] text-text-tertiary mb-2">
              Format nombre attendu : {loc.expectedNumberFormat} · Date :{' '}
              {loc.expectedDateFormat}
            </div>
            {loc.issueExamples.length === 0 ? (
              <p className="text-[11px] text-[var(--status-ok-text)]">
                Aucun écart détecté.
              </p>
            ) : (
              <ul className="space-y-1.5 text-[11px]">
                {loc.issueExamples.map((pi, i) => (
                  <li key={i}>
                    <a
                      href={pi.url}
                      target="_blank"
                      rel="noreferrer"
                      className="font-mono text-text-secondary hover:text-primary break-all"
                    >
                      {pi.url}
                    </a>
                    <ul className="ml-3 mt-0.5 space-y-0.5 text-text-secondary">
                      {pi.issues.map((iss, j) => (
                        <li key={j}>· {iss}</li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </section>
  )
}

function Row({ r }: { r: TechnicalPageRow }) {
  return (
    <tr className="border-t border-[var(--border-subtle)] hover:bg-bg-elevated align-top">
      <td className="px-2 py-1.5 max-w-[280px]">
        <a
          href={r.url}
          target="_blank"
          rel="noreferrer"
          className="font-mono text-text-secondary hover:text-primary break-all"
        >
          {r.url}
        </a>
      </td>
      <td className={`px-2 py-1.5 text-center tabular-nums ${statusColor(String(r.statusCode ?? ''))}`}>
        {r.statusCode ?? 'ERR'}
      </td>
      <td className="px-2 py-1.5 text-center tabular-nums text-text-tertiary">
        {r.depth ?? '—'}
      </td>
      <td className="px-2 py-1.5 text-center">
        {r.isIndexable ? '✓' : <span title={r.indexabilityReason}>✗</span>}
      </td>
      <td className="px-2 py-1.5 text-center tabular-nums">{r.titleLength || '—'}</td>
      <td className="px-2 py-1.5 text-center tabular-nums">{r.metaDescLength || '—'}</td>
      <td className="px-2 py-1.5 text-center tabular-nums">{r.h1Count}</td>
      <td className="px-2 py-1.5 text-center tabular-nums">{r.wordCount || '—'}</td>
      <td className="px-2 py-1.5 text-center tabular-nums text-text-tertiary">
        {r.internalLinksOut}/{r.externalLinksOut}
      </td>
      <td className="px-2 py-1.5 text-center tabular-nums">
        {r.imagesCount} {r.imagesWithoutAlt > 0 && (
          <span className="text-[var(--status-critical-text)]">({r.imagesWithoutAlt})</span>
        )}
      </td>
      <td className="px-2 py-1.5 text-text-secondary">
        {r.issues.length === 0 ? (
          <span className="text-[var(--status-ok-text)]">OK</span>
        ) : (
          <ul className="space-y-0.5">
            {r.issues.map((i, idx) => (
              <li key={idx}>{i}</li>
            ))}
          </ul>
        )}
      </td>
    </tr>
  )
}

function statusColor(code: string): string {
  const n = parseInt(code, 10)
  if (Number.isNaN(n)) return 'text-[var(--status-critical-text)]'
  if (n >= 200 && n < 300) return 'text-[var(--status-ok-text)]'
  if (n >= 300 && n < 400) return 'text-[var(--status-warning-text)]'
  return 'text-[var(--status-critical-text)]'
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="px-3 py-2 rounded-md border border-[var(--border-subtle)] bg-bg-surface">
      <div className="text-[10px] uppercase tracking-wider text-text-tertiary mb-1">
        {label}
      </div>
      <div className="text-xl font-semibold tabular-nums text-text-primary">
        {value}
      </div>
    </div>
  )
}

function IssueGroup({ title, groups }: { title: string; groups: string[][] }) {
  if (!groups || groups.length === 0) return null
  return (
    <div className="border border-[var(--border-subtle)] rounded-md bg-bg-surface p-3">
      <div className="text-xs font-medium text-text-primary mb-2">
        {title}{' '}
        <span className="text-text-tertiary">({groups.length})</span>
      </div>
      <ul className="space-y-1 text-[11px] text-text-secondary">
        {groups.slice(0, 6).map((g, i) => (
          <li key={i}>
            <span className="text-text-tertiary">{g.length} pages :</span>{' '}
            {g.slice(0, 3).join(', ')}
            {g.length > 3 && ' …'}
          </li>
        ))}
        {groups.length > 6 && (
          <li className="text-text-tertiary">… +{groups.length - 6} groupes</li>
        )}
      </ul>
    </div>
  )
}

function IssueList({ title, urls }: { title: string; urls: string[] }) {
  if (!urls || urls.length === 0) return null
  return (
    <div className="border border-[var(--border-subtle)] rounded-md bg-bg-surface p-3">
      <div className="text-xs font-medium text-text-primary mb-2">
        {title}{' '}
        <span className="text-text-tertiary">({urls.length})</span>
      </div>
      <ul className="space-y-1 text-[11px] font-mono text-text-secondary">
        {urls.slice(0, 10).map((u, i) => (
          <li key={i} className="break-all">
            {u}
          </li>
        ))}
        {urls.length > 10 && (
          <li className="text-text-tertiary">… +{urls.length - 10}</li>
        )}
      </ul>
    </div>
  )
}
