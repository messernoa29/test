'use client'

import { useState } from 'react'
import { generateLlmsTxt, type LlmsTxtResult } from '@/lib/api'

export function LlmsTxtTool() {
  const [url, setUrl] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<LlmsTxtResult | null>(null)
  const [copied, setCopied] = useState(false)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!url || submitting) return
    setError(null)
    setSubmitting(true)
    setResult(null)
    try {
      const data = await generateLlmsTxt(url)
      setResult(data)
    } catch (err) {
      setError((err as Error).message || 'Génération impossible.')
    } finally {
      setSubmitting(false)
    }
  }

  async function copy() {
    if (!result) return
    try {
      await navigator.clipboard.writeText(result.content)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard blocked */
    }
  }

  function download() {
    if (!result) return
    const blob = new Blob([result.content], { type: 'text/plain;charset=utf-8' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = 'llms.txt'
    link.click()
    URL.revokeObjectURL(link.href)
  }

  return (
    <div className="max-w-4xl mx-auto py-8 px-6 flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold text-text-primary mb-1">
          llms.txt Generator
        </h1>
        <p className="text-sm text-text-secondary">
          Génère le fichier <code className="font-mono text-xs">llms.txt</code>{' '}
          recommandé par{' '}
          <a
            href="https://llmstxt.org"
            target="_blank"
            rel="noreferrer"
            className="text-primary hover:underline"
          >
            llmstxt.org
          </a>{' '}
          pour exposer un plan de site lisible aux moteurs IA. À placer à la
          racine du domaine.
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
          {submitting ? 'Crawl en cours…' : 'Générer'}
        </button>
      </form>

      {error && (
        <div className="px-4 py-3 rounded-md border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] text-sm text-[var(--status-critical-text)]">
          {error}
        </div>
      )}

      {submitting && !result && (
        <p className="text-xs text-text-tertiary">
          Le crawl peut durer 30 à 90 s selon la taille du site.
        </p>
      )}

      {result && (
        <section className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-text-primary">
              Résultat — <span className="text-text-secondary">{result.domain}</span>
            </h2>
            <div className="flex gap-2">
              <button
                onClick={copy}
                className="h-8 px-3 text-xs rounded-md border border-[var(--border-default)] text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors"
              >
                {copied ? 'Copié ✓' : 'Copier'}
              </button>
              <button
                onClick={download}
                className="h-8 px-3 text-xs rounded-md bg-primary hover:bg-primary-hover text-white transition-colors"
              >
                Télécharger
              </button>
            </div>
          </div>
          <pre className="text-xs font-mono p-4 rounded-lg border border-[var(--border-subtle)] bg-bg-surface text-text-primary overflow-auto max-h-[60vh] whitespace-pre-wrap">
            {result.content}
          </pre>
          <p className="text-xs text-text-tertiary">
            Téléverser ce fichier sur{' '}
            <code className="font-mono">https://{result.domain}/llms.txt</code>.
          </p>
        </section>
      )}
    </div>
  )
}
