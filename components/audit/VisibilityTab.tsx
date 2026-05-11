'use client'

import type { SxoAuditSummary, VisibilityEstimate } from '@/lib/types'

interface Props {
  data?: VisibilityEstimate
  sxo?: SxoAuditSummary
}

export function VisibilityTab({ data, sxo }: Props) {
  if (!data && !sxo) {
    return (
      <div className="text-sm text-text-tertiary py-8">
        Estimation de visibilité non disponible pour cet audit (audit antérieur
        à cette fonctionnalité, ou l&apos;estimation a échoué — relancez
        l&apos;analyse).
      </div>
    )
  }
  if (!data) {
    return (
      <div className="space-y-6">
        {sxo && <SxoSection sxo={sxo} />}
      </div>
    )
  }

  const fmtNum = (n: number | null) =>
    n == null ? '—' : n.toLocaleString('fr-FR')

  return (
    <div className="space-y-6">
      {sxo && <SxoSection sxo={sxo} />}

      {/* Disclaimer */}
      <div className="px-4 py-2.5 rounded-md border border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] text-xs text-[var(--status-warning-text)]">
        {data.disclaimer}
      </div>

      {/* Headline numbers */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <Stat
          label="Trafic organique estimé"
          value={
            data.trafficRange ||
            (data.estimatedMonthlyOrganicTraffic != null
              ? `~${fmtNum(data.estimatedMonthlyOrganicTraffic)} / mois`
              : '—')
          }
        />
        <Stat
          label="Mots-clés positionnés (est.)"
          value={fmtNum(data.estimatedRankingKeywordsCount)}
        />
        <Stat
          label="Concurrents dominants"
          value={String(data.competitorsLikelyOutranking.length || '—')}
        />
      </div>

      {data.summary && (
        <p className="text-sm text-text-secondary leading-relaxed">
          {data.summary}
        </p>
      )}

      {/* Top keywords */}
      {data.topKeywords.length > 0 && (
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary mb-2">
            Mots-clés probablement positionnés
          </h3>
          <div className="overflow-x-auto border border-[var(--border-subtle)] rounded-md">
            <table className="w-full text-xs">
              <thead className="bg-bg-elevated text-text-tertiary">
                <tr>
                  <th className="text-left px-3 py-1.5 font-medium">Mot-clé</th>
                  <th className="px-3 py-1.5 font-medium">Volume est.</th>
                  <th className="px-3 py-1.5 font-medium">Position est.</th>
                  <th className="px-3 py-1.5 font-medium">Intention</th>
                  <th className="text-left px-3 py-1.5 font-medium">Page</th>
                  <th className="text-left px-3 py-1.5 font-medium">Note</th>
                </tr>
              </thead>
              <tbody>
                {data.topKeywords.map((k, i) => (
                  <tr
                    key={i}
                    className="border-t border-[var(--border-subtle)] hover:bg-bg-elevated align-top"
                  >
                    <td className="px-3 py-1.5 text-text-primary font-medium">
                      {k.keyword}
                    </td>
                    <td className="px-3 py-1.5 text-center tabular-nums">
                      {fmtNum(k.estimatedMonthlyVolume)}
                    </td>
                    <td className="px-3 py-1.5 text-center tabular-nums">
                      {k.estimatedPosition ?? '—'}
                    </td>
                    <td className="px-3 py-1.5 text-center text-text-tertiary">
                      {k.intent || '—'}
                    </td>
                    <td className="px-3 py-1.5">
                      {k.rankingUrl ? (
                        <a
                          href={k.rankingUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="font-mono text-text-secondary hover:text-primary break-all"
                        >
                          {k.rankingUrl}
                        </a>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="px-3 py-1.5 text-text-secondary">
                      {k.note || ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Opportunities */}
      {data.opportunities.length > 0 && (
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary mb-2">
            Opportunités de mots-clés (non couverts ou mal couverts)
          </h3>
          <div className="overflow-x-auto border border-[var(--border-subtle)] rounded-md">
            <table className="w-full text-xs">
              <thead className="bg-bg-elevated text-text-tertiary">
                <tr>
                  <th className="text-left px-3 py-1.5 font-medium">Mot-clé</th>
                  <th className="px-3 py-1.5 font-medium">Volume est.</th>
                  <th className="px-3 py-1.5 font-medium">Difficulté</th>
                  <th className="text-left px-3 py-1.5 font-medium">
                    Page à viser
                  </th>
                  <th className="text-left px-3 py-1.5 font-medium">Pourquoi</th>
                </tr>
              </thead>
              <tbody>
                {data.opportunities.map((k, i) => (
                  <tr
                    key={i}
                    className="border-t border-[var(--border-subtle)] hover:bg-bg-elevated align-top"
                  >
                    <td className="px-3 py-1.5 text-text-primary font-medium">
                      {k.keyword}
                    </td>
                    <td className="px-3 py-1.5 text-center tabular-nums">
                      {fmtNum(k.estimatedMonthlyVolume)}
                    </td>
                    <td className="px-3 py-1.5 text-center">
                      <span className={difficultyColor(k.difficulty)}>
                        {k.difficulty || '—'}
                      </span>
                    </td>
                    <td className="px-3 py-1.5 text-text-secondary break-all">
                      {k.suggestedPage || '—'}
                    </td>
                    <td className="px-3 py-1.5 text-text-secondary">
                      {k.rationale || ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Competitors */}
      {data.competitorsLikelyOutranking.length > 0 && (
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary mb-2">
            Concurrents qui dominent probablement ces SERP
          </h3>
          <div className="flex flex-wrap gap-2">
            {data.competitorsLikelyOutranking.map((c, i) => (
              <span
                key={i}
                className="px-2 py-1 rounded border border-[var(--border-subtle)] bg-bg-surface text-xs font-mono text-text-secondary"
              >
                {c}
              </span>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

function difficultyColor(d: string): string {
  if (d === 'low') return 'text-[var(--status-ok-text)]'
  if (d === 'medium') return 'text-[var(--status-warning-text)]'
  if (d === 'high') return 'text-[var(--status-critical-text)]'
  return 'text-text-tertiary'
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="px-3 py-2 rounded-md border border-[var(--border-subtle)] bg-bg-surface">
      <div className="text-[10px] uppercase tracking-wider text-text-tertiary mb-1">
        {label}
      </div>
      <div className="text-lg font-semibold tabular-nums text-text-primary">
        {value}
      </div>
    </div>
  )
}

function SxoSection({ sxo }: { sxo: SxoAuditSummary }) {
  const sevColor = (s: string) =>
    s === 'critical'
      ? 'text-[var(--status-critical-text)]'
      : s === 'warning'
        ? 'text-[var(--status-warning-text)]'
        : s === 'info'
          ? 'text-[var(--status-warning-text)]'
          : 'text-[var(--status-ok-text)]'
  const sevLabel = (s: string) =>
    s === 'critical'
      ? 'Mauvais format'
      : s === 'warning'
        ? 'Mismatch'
        : s === 'info'
          ? 'Léger écart'
          : 'OK'
  return (
    <section>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary mb-1.5">
        SXO — type de page vs intention SERP
      </h3>
      <p className="text-xs text-text-tertiary mb-3">{sxo.note}</p>
      <div className="mb-3 text-sm">
        <span className="text-text-secondary">{sxo.evaluated} pages évaluées · </span>
        <span
          className={
            sxo.mismatches > 0
              ? 'text-[var(--status-warning-text)] font-medium'
              : 'text-[var(--status-ok-text)] font-medium'
          }
        >
          {sxo.mismatches} mismatch{sxo.mismatches > 1 ? 'es' : ''}
        </span>
      </div>
      {sxo.verdicts.length === 0 ? (
        <p className="text-xs text-text-tertiary">Aucune page exploitable pour le SXO.</p>
      ) : (
        <div className="space-y-2">
          {sxo.verdicts.map((v, i) => (
            <div
              key={i}
              className="border border-[var(--border-subtle)] rounded-md bg-bg-surface p-3"
            >
              <div className="flex items-center justify-between gap-2 mb-1">
                <a
                  href={v.url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-mono text-xs text-text-secondary hover:text-primary break-all"
                >
                  {v.url}
                </a>
                <span className={`text-xs font-medium ${sevColor(v.severity)}`}>
                  {sevLabel(v.severity)}
                </span>
              </div>
              <div className="text-[11px] text-text-tertiary mb-1">
                Requête : « {v.keyword} » · votre page : {v.pageType} · SERP
                dominante : {v.serpDominantType || '—'}
              </div>
              {v.recommendation && (
                <p className="text-[11px] text-text-secondary">
                  → {v.recommendation}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
