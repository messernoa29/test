'use client'

import { useEffect, useState } from 'react'
import {
  addSeoKeywords,
  createSeoCampaign,
  deleteSeoCampaign,
  listSeoCampaigns,
  runSeoCheck,
} from '@/lib/api'
import type { SeoCampaign, TrackedKeyword } from '@/lib/types'

export function SeoTrackerTool() {
  const [domain, setDomain] = useState('')
  const [keywordsRaw, setKeywordsRaw] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [campaigns, setCampaigns] = useState<SeoCampaign[]>([])
  const [active, setActive] = useState<SeoCampaign | null>(null)
  const [checking, setChecking] = useState(false)

  useEffect(() => {
    listSeoCampaigns()
      .then((data) => {
        setCampaigns(data)
        if (data.length && !active) setActive(data[0] ?? null)
      })
      .catch(() => setCampaigns([]))
  }, [active])

  async function onCreate(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    const kws = keywordsRaw
      .split(/[\n,;]/)
      .map((k) => k.trim())
      .filter(Boolean)
    if (!domain.trim() || kws.length === 0) {
      setError('Renseigne un domaine et au moins un mot-clé.')
      return
    }
    setSubmitting(true)
    try {
      const created = await createSeoCampaign(domain.trim(), kws)
      const list = await listSeoCampaigns()
      setCampaigns(list)
      setActive(created)
      setDomain('')
      setKeywordsRaw('')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  async function onCheck(id: string) {
    setChecking(true)
    try {
      const fresh = await runSeoCheck(id)
      setActive(fresh)
      const list = await listSeoCampaigns()
      setCampaigns(list)
    } catch (err) {
      alert((err as Error).message)
    } finally {
      setChecking(false)
    }
  }

  async function onAddKeywords(id: string) {
    const raw = prompt('Nouveaux mots-clés (un par ligne ou séparés par des virgules) :')
    if (!raw) return
    const kws = raw.split(/[\n,;]/).map((k) => k.trim()).filter(Boolean)
    if (!kws.length) return
    try {
      const updated = await addSeoKeywords(id, kws)
      setActive(updated)
      const list = await listSeoCampaigns()
      setCampaigns(list)
    } catch (err) {
      alert((err as Error).message)
    }
  }

  async function onDelete(id: string) {
    if (!confirm('Supprimer cette campagne et tout son historique ?')) return
    try {
      await deleteSeoCampaign(id)
      const list = await listSeoCampaigns()
      setCampaigns(list)
      if (active?.id === id) setActive(list[0] ?? null)
    } catch (err) {
      alert((err as Error).message)
    }
  }

  return (
    <div className="max-w-6xl mx-auto py-8 px-6 flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold text-text-primary mb-1">
          SEO Tracker
        </h1>
        <p className="text-sm text-text-secondary">
          Suivi de positionnement par mot-clé via DuckDuckGo. Lance un check à
          la demande&nbsp;: l&apos;outil scanne les 100 premiers résultats et
          enregistre la position du domaine pour chaque requête.
        </p>
      </header>

      <form
        onSubmit={onCreate}
        className="grid grid-cols-1 sm:grid-cols-[1fr_2fr_auto] gap-2 p-4 rounded-lg border border-[var(--border-subtle)] bg-bg-surface items-start"
      >
        <input
          required
          disabled={submitting}
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          placeholder="exemple.com"
          className="h-10 px-3 bg-bg-page border border-[var(--border-default)] rounded-md text-text-primary placeholder:text-text-tertiary text-sm focus:outline-none focus:border-primary focus:ring-2 focus:ring-[var(--primary-dim)] transition disabled:opacity-60"
        />
        <textarea
          rows={3}
          disabled={submitting}
          value={keywordsRaw}
          onChange={(e) => setKeywordsRaw(e.target.value)}
          placeholder={'mot-clé 1\nmot-clé 2\nmot-clé 3'}
          className="px-3 py-2 bg-bg-page border border-[var(--border-default)] rounded-md text-text-primary placeholder:text-text-tertiary text-sm font-mono focus:outline-none focus:border-primary focus:ring-2 focus:ring-[var(--primary-dim)] transition disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={submitting}
          className="h-10 px-5 bg-primary hover:bg-primary-hover text-white rounded-md font-medium text-sm transition-colors disabled:opacity-60 self-start"
        >
          {submitting ? 'Création…' : 'Créer la campagne'}
        </button>
      </form>

      {error && (
        <div className="px-4 py-3 rounded-md border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] text-sm text-[var(--status-critical-text)]">
          {error}
        </div>
      )}

      {campaigns.length > 0 && (
        <section className="grid grid-cols-1 md:grid-cols-[280px_1fr] gap-4">
          <aside className="border border-[var(--border-subtle)] rounded-lg bg-bg-surface overflow-hidden">
            <ul className="divide-y divide-[var(--border-subtle)]">
              {campaigns.map((c) => (
                <li key={c.id}>
                  <button
                    onClick={() => setActive(c)}
                    className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                      active?.id === c.id
                        ? 'bg-[var(--primary-bg)] text-primary'
                        : 'hover:bg-bg-elevated text-text-secondary'
                    }`}
                  >
                    <div className="font-medium truncate">{c.domain}</div>
                    <div className="text-[11px] text-text-tertiary">
                      {c.keywords.length} mots-clés ·{' '}
                      {new Date(c.updatedAt).toLocaleDateString('fr-FR')}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </aside>

          {active && (
            <CampaignDetail
              campaign={active}
              checking={checking}
              onCheck={onCheck}
              onAddKeywords={onAddKeywords}
              onDelete={onDelete}
            />
          )}
        </section>
      )}
    </div>
  )
}

function CampaignDetail({
  campaign,
  checking,
  onCheck,
  onAddKeywords,
  onDelete,
}: {
  campaign: SeoCampaign
  checking: boolean
  onCheck: (id: string) => void
  onAddKeywords: (id: string) => void
  onDelete: (id: string) => void
}) {
  const lastCheck = campaign.keywords
    .flatMap((k) => k.history)
    .map((r) => r.checkedAt)
    .sort()
    .pop()

  return (
    <div className="border border-[var(--border-subtle)] rounded-lg bg-bg-surface p-4 flex flex-col gap-4">
      <header className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-sm font-semibold text-text-primary">
            {campaign.domain}
          </h2>
          <p className="text-xs text-text-tertiary">
            {campaign.keywords.length} mots-clés ·{' '}
            {lastCheck
              ? `dernier relevé ${new Date(lastCheck).toLocaleString('fr-FR')}`
              : 'aucun relevé'}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => onCheck(campaign.id)}
            disabled={checking}
            className="h-8 px-3 text-xs rounded-md bg-primary hover:bg-primary-hover text-white transition-colors disabled:opacity-60"
          >
            {checking ? 'Relevé en cours…' : 'Lancer un relevé'}
          </button>
          <button
            onClick={() => onAddKeywords(campaign.id)}
            className="h-8 px-3 text-xs rounded-md border border-[var(--border-default)] text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors"
          >
            + Mots-clés
          </button>
          <button
            onClick={() => onDelete(campaign.id)}
            className="h-8 px-3 text-xs rounded-md border border-[var(--border-default)] text-[var(--status-critical-text)] hover:bg-bg-elevated transition-colors"
          >
            Supprimer
          </button>
        </div>
      </header>

      <table className="w-full text-xs">
        <thead>
          <tr className="text-left border-b border-[var(--border-subtle)]">
            <th className="py-2 font-medium text-text-tertiary uppercase tracking-wider">Mot-clé</th>
            <th className="py-2 font-medium text-text-tertiary uppercase tracking-wider">Position</th>
            <th className="py-2 font-medium text-text-tertiary uppercase tracking-wider">Δ</th>
            <th className="py-2 font-medium text-text-tertiary uppercase tracking-wider">Tendance</th>
            <th className="py-2 font-medium text-text-tertiary uppercase tracking-wider">URL</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--border-subtle)]">
          {campaign.keywords.map((tk) => (
            <KeywordRow key={tk.keyword} tk={tk} />
          ))}
        </tbody>
      </table>

      <p className="text-[11px] text-text-tertiary">
        Résultats issus de DuckDuckGo (top 100). Les positions diffèrent de
        Google&nbsp;: utilisez ces données comme indicateur de tendance.
      </p>
    </div>
  )
}

function KeywordRow({ tk }: { tk: TrackedKeyword }) {
  const last = tk.history[tk.history.length - 1]
  const previous = tk.history[tk.history.length - 2]
  const delta =
    last?.position != null && previous?.position != null
      ? previous.position - last.position
      : null
  const deltaColor =
    delta == null
      ? 'var(--text-tertiary)'
      : delta > 0
        ? 'var(--status-ok-text)'
        : delta < 0
          ? 'var(--status-critical-text)'
          : 'var(--text-tertiary)'

  return (
    <tr>
      <td className="py-2 font-medium text-text-primary truncate max-w-[28ch]">
        {tk.keyword}
      </td>
      <td className="py-2 tabular-nums">
        {last?.position != null ? (
          <span className="text-text-primary font-semibold">{last.position}</span>
        ) : last ? (
          <span className="text-text-tertiary">&gt; 100</span>
        ) : (
          <span className="text-text-tertiary">—</span>
        )}
      </td>
      <td className="py-2 tabular-nums" style={{ color: deltaColor }}>
        {delta == null ? '—' : delta > 0 ? `+${delta}` : delta}
      </td>
      <td className="py-2">
        <Trend history={tk.history} />
      </td>
      <td className="py-2 truncate max-w-[36ch]">
        {last?.url ? (
          <a
            href={last.url}
            target="_blank"
            rel="noreferrer"
            className="text-primary hover:underline"
          >
            {last.url}
          </a>
        ) : (
          <span className="text-text-tertiary">—</span>
        )}
      </td>
    </tr>
  )
}

function Trend({ history }: { history: TrackedKeyword['history'] }) {
  const points = history.map((r) => r.position)
  const numeric = points.filter((p): p is number => typeof p === 'number')
  if (numeric.length < 2) {
    return <span className="text-text-tertiary text-[11px]">—</span>
  }
  const w = 80
  const h = 18
  // Lower position = better → invert Y
  const min = Math.min(...numeric)
  const max = Math.max(...numeric)
  const range = max - min || 1
  const stepX = points.length > 1 ? w / (points.length - 1) : w
  const path = points
    .map((p, i) => {
      if (typeof p !== 'number') return null
      const x = i * stepX
      const y = ((p - min) / range) * (h - 4) + 2
      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`
    })
    .filter(Boolean)
    .join(' ')
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <path d={path} fill="none" stroke="var(--primary)" strokeWidth="1.2" />
    </svg>
  )
}
