'use client'

import { useEffect, useState } from 'react'
import {
  deletePerfMonitor,
  listPerfMonitors,
  refreshPerfMonitor,
  watchPerf,
} from '@/lib/api'
import type { PerfMonitor, PerformanceMetric, PerformanceSnapshot } from '@/lib/types'

const METRICS_TO_PLOT = ['LCP', 'INP', 'CLS'] as const

export function PerfMonitorTool() {
  const [url, setUrl] = useState('')
  const [strategy, setStrategy] = useState<'mobile' | 'desktop'>('mobile')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [monitors, setMonitors] = useState<PerfMonitor[]>([])
  const [active, setActive] = useState<PerfMonitor | null>(null)

  useEffect(() => {
    listPerfMonitors()
      .then((data) => {
        setMonitors(data)
        if (data.length && !active) setActive(data[0] ?? null)
      })
      .catch(() => setMonitors([]))
  }, [active])

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!url || submitting) return
    setError(null)
    setSubmitting(true)
    try {
      const monitor = await watchPerf(url, strategy)
      setActive(monitor)
      const list = await listPerfMonitors()
      setMonitors(list)
      setUrl('')
    } catch (err) {
      setError((err as Error).message || 'Lancement impossible.')
    } finally {
      setSubmitting(false)
    }
  }

  async function onRefresh(id: string) {
    try {
      const fresh = await refreshPerfMonitor(id)
      setActive(fresh)
      const list = await listPerfMonitors()
      setMonitors(list)
    } catch (err) {
      alert((err as Error).message)
    }
  }

  async function onDelete(id: string) {
    if (!confirm('Supprimer ce monitoring et tout son historique ?')) return
    try {
      await deletePerfMonitor(id)
      const list = await listPerfMonitors()
      setMonitors(list)
      if (active?.id === id) setActive(list[0] ?? null)
    } catch (err) {
      alert((err as Error).message)
    }
  }

  return (
    <div className="max-w-5xl mx-auto py-8 px-6 flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold text-text-primary mb-1">
          Performance Monitor
        </h1>
        <p className="text-sm text-text-secondary">
          Mesure les Core Web Vitals (LCP, INP, CLS) d&apos;une URL via PageSpeed
          Insights et conserve un historique sur 90 mesures pour visualiser
          l&apos;évolution.
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
          placeholder="https://exemple.com/page"
          className="flex-1 h-10 px-3 bg-bg-page border border-[var(--border-default)] rounded-md text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-primary focus:ring-2 focus:ring-[var(--primary-dim)] transition text-sm disabled:opacity-60"
        />
        <select
          value={strategy}
          onChange={(e) => setStrategy(e.target.value as 'mobile' | 'desktop')}
          disabled={submitting}
          className="h-10 px-3 bg-bg-page border border-[var(--border-default)] rounded-md text-text-primary text-sm disabled:opacity-60"
        >
          <option value="mobile">Mobile</option>
          <option value="desktop">Desktop</option>
        </select>
        <button
          type="submit"
          disabled={submitting}
          className="h-10 px-5 bg-primary hover:bg-primary-hover text-white rounded-md font-medium text-sm transition-colors disabled:opacity-60"
        >
          {submitting ? 'Mesure…' : 'Mesurer'}
        </button>
      </form>

      {error && (
        <div className="px-4 py-3 rounded-md border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] text-sm text-[var(--status-critical-text)]">
          {error}
        </div>
      )}

      {monitors.length > 0 && (
        <section className="grid grid-cols-1 md:grid-cols-[280px_1fr] gap-4">
          <aside className="border border-[var(--border-subtle)] rounded-lg bg-bg-surface overflow-hidden">
            <ul className="divide-y divide-[var(--border-subtle)]">
              {monitors.map((m) => (
                <li key={m.id}>
                  <button
                    onClick={() => setActive(m)}
                    className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                      active?.id === m.id
                        ? 'bg-[var(--primary-bg)] text-primary'
                        : 'hover:bg-bg-elevated text-text-secondary'
                    }`}
                  >
                    <div className="font-medium truncate text-xs">{m.url}</div>
                    <div className="text-[11px] text-text-tertiary">
                      {m.strategy} · {m.history.length} mesures ·{' '}
                      {new Date(m.updatedAt).toLocaleDateString('fr-FR')}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </aside>

          {active && (
            <PerfDetail monitor={active} onRefresh={onRefresh} onDelete={onDelete} />
          )}
        </section>
      )}
    </div>
  )
}

function PerfDetail({
  monitor,
  onRefresh,
  onDelete,
}: {
  monitor: PerfMonitor
  onRefresh: (id: string) => void
  onDelete: (id: string) => void
}) {
  const last = monitor.history[monitor.history.length - 1]
  return (
    <div className="border border-[var(--border-subtle)] rounded-lg bg-bg-surface p-4 flex flex-col gap-4">
      <header className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-sm font-semibold text-text-primary truncate max-w-[60ch]">
            {monitor.url}
          </h2>
          <p className="text-xs text-text-tertiary">
            {monitor.strategy} · dernier relevé{' '}
            {last ? new Date(last.fetchedAt).toLocaleString('fr-FR') : '—'}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => onRefresh(monitor.id)}
            className="h-8 px-3 text-xs rounded-md bg-primary hover:bg-primary-hover text-white transition-colors"
          >
            Nouvelle mesure
          </button>
          <button
            onClick={() => onDelete(monitor.id)}
            className="h-8 px-3 text-xs rounded-md border border-[var(--border-default)] text-[var(--status-critical-text)] hover:bg-bg-elevated transition-colors"
          >
            Supprimer
          </button>
        </div>
      </header>

      {last?.error && (
        <div className="px-3 py-2 rounded-md border border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] text-xs text-[var(--status-warning-text)]">
          PageSpeed Insights indisponible : {last.error}
        </div>
      )}

      {last && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <ScoreCard label="Score Lighthouse" value={last.performanceScore} />
          {METRICS_TO_PLOT.map((name) => (
            <MetricCard
              key={name}
              name={name}
              metric={last.metrics.find((m) => m.name === name) ?? null}
            />
          ))}
        </div>
      )}

      {monitor.history.length > 1 && (
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary mb-2">
            Évolution
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {METRICS_TO_PLOT.map((name) => (
              <Sparkline
                key={name}
                name={name}
                history={monitor.history}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

function ScoreCard({ label, value }: { label: string; value: number | null | undefined }) {
  const color =
    value == null
      ? 'var(--text-tertiary)'
      : value >= 90
        ? 'var(--status-ok-text)'
        : value >= 50
          ? 'var(--status-warning-text)'
          : 'var(--status-critical-text)'
  return (
    <div className="px-3 py-2 rounded-md border border-[var(--border-subtle)] bg-bg-page">
      <div className="text-[11px] uppercase tracking-wider text-text-tertiary mb-1">
        {label}
      </div>
      <div className="text-2xl font-semibold tabular-nums" style={{ color }}>
        {value ?? '—'}
      </div>
    </div>
  )
}

function MetricCard({
  name,
  metric,
}: {
  name: string
  metric: PerformanceMetric | null
}) {
  const display = formatMetric(name, metric)
  const color = ratingColor(metric?.rating)
  return (
    <div className="px-3 py-2 rounded-md border border-[var(--border-subtle)] bg-bg-page">
      <div className="text-[11px] uppercase tracking-wider text-text-tertiary mb-1">
        {name}
        {metric?.threshold && (
          <span className="ml-1 text-text-tertiary normal-case tracking-normal">
            ({metric.threshold})
          </span>
        )}
      </div>
      <div className="text-xl font-semibold tabular-nums" style={{ color }}>
        {display}
      </div>
    </div>
  )
}

function ratingColor(rating?: string): string {
  if (rating === 'good') return 'var(--status-ok-text)'
  if (rating === 'needs-improvement') return 'var(--status-warning-text)'
  if (rating === 'poor') return 'var(--status-critical-text)'
  return 'var(--text-primary)'
}

function formatMetric(name: string, metric: PerformanceMetric | null): string {
  if (!metric) return '—'
  const value = metric.fieldValue ?? metric.labValue
  if (value == null) return '—'
  if (name === 'CLS') return value.toFixed(3)
  if (value >= 1000) return `${(value / 1000).toFixed(2)}s`
  return `${Math.round(value)}ms`
}

function Sparkline({
  name,
  history,
}: {
  name: string
  history: PerformanceSnapshot[]
}) {
  const points = history
    .map((snap) => snap.metrics.find((m) => m.name === name))
    .map((m) => (m ? (m.fieldValue ?? m.labValue ?? null) : null))
  const filtered = points.filter((p): p is number => typeof p === 'number')
  if (filtered.length < 2) {
    return (
      <div className="px-3 py-2 rounded-md border border-[var(--border-subtle)] bg-bg-page">
        <div className="text-[11px] uppercase tracking-wider text-text-tertiary mb-1">
          {name}
        </div>
        <div className="text-xs text-text-tertiary">Pas assez de données.</div>
      </div>
    )
  }
  const min = Math.min(...filtered)
  const max = Math.max(...filtered)
  const w = 120
  const h = 36
  const range = max - min || 1
  const stepX = points.length > 1 ? w / (points.length - 1) : w
  const path = points
    .map((p, i) => {
      if (typeof p !== 'number') return null
      const x = i * stepX
      const y = h - ((p - min) / range) * (h - 4) - 2
      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`
    })
    .filter(Boolean)
    .join(' ')

  const last = filtered[filtered.length - 1] ?? 0
  const first = filtered[0] ?? 0
  const trend = last - first
  const trendColor =
    trend > 0
      ? name === 'CLS'
        ? 'var(--status-critical-text)'
        : 'var(--status-critical-text)'
      : 'var(--status-ok-text)'

  return (
    <div className="px-3 py-2 rounded-md border border-[var(--border-subtle)] bg-bg-page">
      <div className="flex items-center justify-between mb-1">
        <div className="text-[11px] uppercase tracking-wider text-text-tertiary">
          {name}
        </div>
        <div className="text-[11px] tabular-nums" style={{ color: trendColor }}>
          {trend > 0 ? '▲' : trend < 0 ? '▼' : '—'}{' '}
          {Math.abs(trend) >= 1 ? Math.round(Math.abs(trend)) : Math.abs(trend).toFixed(2)}
        </div>
      </div>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="w-full">
        <path
          d={path}
          fill="none"
          stroke="var(--primary)"
          strokeWidth="1.5"
        />
      </svg>
    </div>
  )
}
