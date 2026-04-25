'use client'

import { useEffect, useState } from 'react'
import {
  deleteSitemapWatch,
  listSitemapWatches,
  refreshSitemapWatch,
  watchSitemap,
} from '@/lib/api'
import type { SitemapWatch } from '@/lib/types'

export function SitemapWatcherTool() {
  const [url, setUrl] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [watches, setWatches] = useState<SitemapWatch[]>([])
  const [active, setActive] = useState<SitemapWatch | null>(null)

  useEffect(() => {
    listSitemapWatches()
      .then((data) => {
        setWatches(data)
        if (data.length && !active) setActive(data[0] ?? null)
      })
      .catch(() => setWatches([]))
  }, [active])

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!url || submitting) return
    setError(null)
    setSubmitting(true)
    try {
      const watch = await watchSitemap(url)
      setActive(watch)
      const list = await listSitemapWatches()
      setWatches(list)
      setUrl('')
    } catch (err) {
      setError((err as Error).message || 'Impossible de récupérer le sitemap.')
    } finally {
      setSubmitting(false)
    }
  }

  async function onRefresh(id: string) {
    try {
      const fresh = await refreshSitemapWatch(id)
      setActive(fresh)
      const list = await listSitemapWatches()
      setWatches(list)
    } catch (err) {
      alert((err as Error).message)
    }
  }

  async function onDelete(id: string) {
    if (!confirm('Supprimer ce suivi de sitemap ?')) return
    try {
      await deleteSitemapWatch(id)
      const list = await listSitemapWatches()
      setWatches(list)
      if (active?.id === id) setActive(list[0] ?? null)
    } catch (err) {
      alert((err as Error).message)
    }
  }

  return (
    <div className="max-w-5xl mx-auto py-8 px-6 flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold text-text-primary mb-1">
          Sitemap Watcher
        </h1>
        <p className="text-sm text-text-secondary">
          Surveille le <code className="font-mono text-xs">/sitemap.xml</code>{' '}
          d&apos;un site. Chaque rafraîchissement compare les URLs détectées au
          dernier instantané et liste les ajouts et suppressions.
        </p>
      </header>

      <form
        onSubmit={onSubmit}
        className="flex flex-col sm:flex-row gap-2 p-4 rounded-lg border border-[var(--border-subtle)] bg-bg-surface"
      >
        <input
          type="url"
          required
          disabled={submitting}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://exemple.com"
          className="flex-1 h-10 px-3 bg-bg-page border border-[var(--border-default)] rounded-md text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-primary focus:ring-2 focus:ring-[var(--primary-dim)] transition text-sm disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={submitting}
          className="h-10 px-5 bg-primary hover:bg-primary-hover text-white rounded-md font-medium text-sm transition-colors disabled:opacity-60"
        >
          {submitting ? 'Récupération…' : 'Surveiller'}
        </button>
      </form>

      {error && (
        <div className="px-4 py-3 rounded-md border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] text-sm text-[var(--status-critical-text)]">
          {error}
        </div>
      )}

      {watches.length > 0 && (
        <section className="grid grid-cols-1 md:grid-cols-[280px_1fr] gap-4">
          <aside className="border border-[var(--border-subtle)] rounded-lg bg-bg-surface overflow-hidden">
            <ul className="divide-y divide-[var(--border-subtle)]">
              {watches.map((w) => (
                <li key={w.id}>
                  <button
                    onClick={() => setActive(w)}
                    className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                      active?.id === w.id
                        ? 'bg-[var(--primary-bg)] text-primary'
                        : 'hover:bg-bg-elevated text-text-secondary'
                    }`}
                  >
                    <div className="font-medium truncate">{w.domain}</div>
                    <div className="text-[11px] text-text-tertiary">
                      {w.snapshotUrls.length} URLs ·{' '}
                      {new Date(w.updatedAt).toLocaleDateString('fr-FR')}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </aside>

          {active && <WatchDetail watch={active} onRefresh={onRefresh} onDelete={onDelete} />}
        </section>
      )}
    </div>
  )
}

function WatchDetail({
  watch,
  onRefresh,
  onDelete,
}: {
  watch: SitemapWatch
  onRefresh: (id: string) => void
  onDelete: (id: string) => void
}) {
  const diff = watch.lastDiff
  return (
    <div className="border border-[var(--border-subtle)] rounded-lg bg-bg-surface p-4 flex flex-col gap-4">
      <header className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-sm font-semibold text-text-primary">
            {watch.domain}
          </h2>
          <p className="text-xs text-text-tertiary">
            Sitemap&nbsp;:{' '}
            <a
              href={watch.sitemapUrl}
              target="_blank"
              rel="noreferrer"
              className="text-primary hover:underline"
            >
              {watch.sitemapUrl}
            </a>
          </p>
          <p className="text-xs text-text-tertiary">
            Dernier snapshot : {new Date(watch.updatedAt).toLocaleString('fr-FR')}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => onRefresh(watch.id)}
            className="h-8 px-3 text-xs rounded-md bg-primary hover:bg-primary-hover text-white transition-colors"
          >
            Rafraîchir
          </button>
          <button
            onClick={() => onDelete(watch.id)}
            className="h-8 px-3 text-xs rounded-md border border-[var(--border-default)] text-[var(--status-critical-text)] hover:bg-bg-elevated transition-colors"
          >
            Supprimer
          </button>
        </div>
      </header>

      {diff && (
        <div className="grid grid-cols-3 gap-3 text-center">
          <Stat label="URLs actuelles" value={diff.currentCount} />
          <Stat label="Ajoutées" value={diff.added.length} accent="ok" />
          <Stat label="Supprimées" value={diff.removed.length} accent="critical" />
        </div>
      )}

      {diff && (diff.added.length > 0 || diff.removed.length > 0) ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <DiffList title="Ajoutées" urls={diff.added} accent="ok" />
          <DiffList title="Supprimées" urls={diff.removed} accent="critical" />
        </div>
      ) : (
        <p className="text-xs text-text-tertiary">
          {diff?.previousFetchedAt
            ? 'Aucun changement depuis le dernier snapshot.'
            : 'Premier snapshot enregistré. Rafraîchis pour comparer.'}
        </p>
      )}

      <details className="text-xs">
        <summary className="cursor-pointer text-text-secondary">
          Voir toutes les URLs ({watch.snapshotUrls.length})
        </summary>
        <ul className="mt-2 max-h-[40vh] overflow-auto font-mono text-text-tertiary space-y-1">
          {watch.snapshotUrls.map((u) => (
            <li key={u} className="truncate">
              {u}
            </li>
          ))}
        </ul>
      </details>
    </div>
  )
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string
  value: number
  accent?: 'ok' | 'critical'
}) {
  const color =
    accent === 'ok'
      ? 'var(--status-ok-text)'
      : accent === 'critical'
        ? 'var(--status-critical-text)'
        : 'var(--text-primary)'
  return (
    <div className="px-3 py-2 rounded-md border border-[var(--border-subtle)] bg-bg-page">
      <div className="text-[11px] uppercase tracking-wider text-text-tertiary mb-1">
        {label}
      </div>
      <div className="text-xl font-semibold tabular-nums" style={{ color }}>
        {value}
      </div>
    </div>
  )
}

function DiffList({
  title,
  urls,
  accent,
}: {
  title: string
  urls: string[]
  accent: 'ok' | 'critical'
}) {
  if (urls.length === 0) {
    return (
      <div className="text-xs text-text-tertiary">
        <div className="font-medium text-text-secondary mb-1">{title}</div>
        Aucune.
      </div>
    )
  }
  const color =
    accent === 'ok' ? 'var(--status-ok-text)' : 'var(--status-critical-text)'
  return (
    <div>
      <div
        className="text-xs font-semibold mb-1 uppercase tracking-wider"
        style={{ color }}
      >
        {title} ({urls.length})
      </div>
      <ul className="text-xs font-mono space-y-1 max-h-[50vh] overflow-auto">
        {urls.map((u) => (
          <li key={u} className="truncate text-text-secondary">
            {u}
          </li>
        ))}
      </ul>
    </div>
  )
}
