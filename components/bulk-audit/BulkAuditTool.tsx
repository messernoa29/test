'use client'

import Link from 'next/link'
import { useEffect, useRef, useState } from 'react'
import {
  bulkCsvUrl,
  deleteBulk,
  getBulk,
  listBulks,
  startBulkAudit,
} from '@/lib/api'
import type { BulkAudit, BulkAuditItem } from '@/lib/types'

const MAX_URLS = 50

interface ParsedRow {
  url: string
  label?: string
}

export function BulkAuditTool() {
  const [csvText, setCsvText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [active, setActive] = useState<BulkAudit | null>(null)
  const [history, setHistory] = useState<BulkAudit[]>([])
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    listBulks().then(setHistory).catch(() => setHistory([]))
  }, [])

  // Poll active bulk while running.
  useEffect(() => {
    if (!active || active.status === 'done' || active.status === 'failed') return
    const t = setInterval(async () => {
      try {
        const fresh = await getBulk(active.id)
        setActive(fresh)
        if (fresh.status === 'done' || fresh.status === 'failed') {
          listBulks().then(setHistory).catch(() => undefined)
        }
      } catch {
        /* ignore polling errors */
      }
    }, 4000)
    return () => clearInterval(t)
  }, [active])

  function handleFile(file: File) {
    const reader = new FileReader()
    reader.onload = () => setCsvText(String(reader.result || ''))
    reader.readAsText(file)
  }

  function parseCsv(raw: string): ParsedRow[] {
    const rows: ParsedRow[] = []
    const lines = raw.split(/\r?\n/)
    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed) continue
      // Skip header row when first cell is "url" (case-insensitive)
      const cells = trimmed.split(/[,;\t]/).map((c) => c.trim())
      const first = cells[0]
      if (!first) continue
      if (rows.length === 0 && first.toLowerCase() === 'url') continue
      if (!/^https?:\/\//i.test(first)) continue
      rows.push({ url: first, label: cells[1] || undefined })
    }
    return rows
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    const rows = parseCsv(csvText)
    if (rows.length === 0) {
      setError('Aucune URL valide trouvée. Une URL par ligne (http/https).')
      return
    }
    if (rows.length > MAX_URLS) {
      setError(`Maximum ${MAX_URLS} URLs par lot. ${rows.length} fournies.`)
      return
    }
    setSubmitting(true)
    try {
      const bulk = await startBulkAudit(
        rows.map((r) => r.url),
        rows.map((r) => r.label || ''),
      )
      setActive(bulk)
      setCsvText('')
      if (fileRef.current) fileRef.current.value = ''
    } catch (err) {
      setError((err as Error).message || 'Lancement impossible.')
    } finally {
      setSubmitting(false)
    }
  }

  async function onDelete(id: string) {
    if (!confirm('Supprimer ce lot ? Les audits associés restent disponibles.')) return
    try {
      await deleteBulk(id)
      setHistory((h) => h.filter((b) => b.id !== id))
      if (active?.id === id) setActive(null)
    } catch (err) {
      alert((err as Error).message)
    }
  }

  return (
    <div className="max-w-5xl mx-auto py-8 px-6 flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold text-text-primary mb-1">
          Bulk Audit CSV
        </h1>
        <p className="text-sm text-text-secondary">
          Colle ou téléverse un CSV (1ʳᵉ colonne&nbsp;: URL, 2ᵉ colonne
          optionnelle&nbsp;: libellé). Maximum {MAX_URLS} URLs par lot. Les
          audits tournent en parallèle&nbsp;; un export CSV consolidé est
          généré.
        </p>
      </header>

      <form
        onSubmit={onSubmit}
        className="flex flex-col gap-3 p-4 rounded-lg border border-[var(--border-subtle)] bg-bg-surface"
      >
        <div className="flex items-center gap-3 flex-wrap">
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) handleFile(f)
            }}
            className="text-xs text-text-secondary"
          />
          <span className="text-xs text-text-tertiary">
            ou collez les URLs ci-dessous
          </span>
        </div>
        <textarea
          value={csvText}
          onChange={(e) => setCsvText(e.target.value)}
          disabled={submitting}
          placeholder={'https://exemple.com,Site principal\nhttps://blog.exemple.com,Blog'}
          rows={8}
          className="w-full p-3 bg-bg-page border border-[var(--border-default)] rounded-md text-text-primary placeholder:text-text-tertiary font-mono text-xs focus:outline-none focus:border-primary focus:ring-2 focus:ring-[var(--primary-dim)] transition disabled:opacity-60"
        />
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-text-tertiary">
            Une URL par ligne. Séparateurs acceptés&nbsp;: virgule, point-virgule, tab.
          </p>
          <button
            type="submit"
            disabled={submitting || !csvText.trim()}
            className="h-10 px-5 bg-primary hover:bg-primary-hover text-white rounded-md font-medium text-sm transition-colors disabled:opacity-60"
          >
            {submitting ? 'Lancement…' : 'Lancer le lot'}
          </button>
        </div>
        {error && (
          <p className="text-xs text-[var(--status-critical-text)]">{error}</p>
        )}
      </form>

      {active && <BulkProgress bulk={active} />}

      {history.length > 0 && (
        <section>
          <h2 className="text-sm font-medium text-text-primary mb-2">
            Lots récents
          </h2>
          <ul className="flex flex-col divide-y divide-[var(--border-subtle)] border border-[var(--border-subtle)] rounded-lg overflow-hidden bg-bg-surface">
            {history.map((b) => (
              <li
                key={b.id}
                className="flex items-center gap-4 px-4 py-3 text-sm"
              >
                <button
                  onClick={() => setActive(b)}
                  className="text-primary hover:underline font-mono text-xs"
                >
                  {b.id.slice(0, 12)}
                </button>
                <span className="text-text-tertiary text-xs flex-shrink-0">
                  {new Date(b.createdAt).toLocaleString('fr-FR')}
                </span>
                <span className="text-text-secondary text-xs">
                  {b.items.length} URLs · {b.status}
                </span>
                <div className="ml-auto flex items-center gap-2">
                  <a
                    href={bulkCsvUrl(b.id)}
                    className="text-xs text-text-secondary hover:text-text-primary"
                  >
                    Export CSV
                  </a>
                  <button
                    onClick={() => onDelete(b.id)}
                    className="text-xs text-[var(--status-critical-text)] hover:underline"
                  >
                    Supprimer
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

function BulkProgress({ bulk }: { bulk: BulkAudit }) {
  const total = bulk.items.length
  const done = bulk.items.filter((i) => i.auditId).length // can't know per-item without fetching
  const pct = total === 0 ? 0 : Math.round((done / total) * 100)

  return (
    <section className="p-4 rounded-lg border border-[var(--border-subtle)] bg-bg-surface">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-medium text-text-primary">
          Lot{' '}
          <span className="font-mono text-xs text-text-secondary">
            {bulk.id.slice(0, 12)}
          </span>{' '}
          — <span className="text-text-secondary">{bulk.status}</span>
        </h2>
        <a
          href={bulkCsvUrl(bulk.id)}
          className="h-8 px-3 text-xs rounded-md bg-primary hover:bg-primary-hover text-white inline-flex items-center transition-colors"
        >
          Export CSV
        </a>
      </div>
      <div className="mb-3">
        <div className="h-1.5 rounded-full bg-bg-elevated overflow-hidden">
          <div
            className="h-full bg-primary transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
      <ul className="flex flex-col text-xs divide-y divide-[var(--border-subtle)] max-h-[40vh] overflow-auto">
        {bulk.items.map((item) => (
          <BulkRow key={item.url + (item.auditId ?? '')} item={item} />
        ))}
      </ul>
    </section>
  )
}

function BulkRow({ item }: { item: BulkAuditItem }) {
  return (
    <li className="flex items-center gap-3 py-2">
      <span className="font-mono truncate flex-1 text-text-secondary">
        {item.url}
      </span>
      {item.label && (
        <span className="text-text-tertiary truncate max-w-[160px]">
          {item.label}
        </span>
      )}
      {item.auditId ? (
        <Link
          href={`/audit/${item.auditId}`}
          className="text-primary hover:underline"
        >
          Voir audit
        </Link>
      ) : (
        <span className="text-text-tertiary">—</span>
      )}
    </li>
  )
}
