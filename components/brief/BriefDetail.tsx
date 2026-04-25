'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { getContentBrief } from '@/lib/api'
import type {
  ContentBrief,
  ContentBriefOutline,
  SerpResult,
} from '@/lib/types'

interface Props {
  initial: ContentBrief
}

export function BriefDetail({ initial }: Props) {
  const [brief, setBrief] = useState<ContentBrief>(initial)

  useEffect(() => {
    if (brief.status === 'done' || brief.status === 'failed') return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const tick = async () => {
      try {
        const next = await getContentBrief(brief.id)
        if (!cancelled) setBrief(next)
        if (next.status === 'done' || next.status === 'failed') return
      } catch {
        // keep polling
      }
      if (!cancelled) timer = setTimeout(tick, 4000)
    }
    timer = setTimeout(tick, 4000)
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [brief.id, brief.status])

  return (
    <div>
      <div className="border-b border-[var(--border-subtle)] bg-bg-surface">
        <div className="max-w-5xl mx-auto px-8 py-5 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-xs text-text-tertiary mb-1">
              Content Brief · {brief.createdAt.slice(0, 10)}
            </p>
            <h1 className="text-xl font-semibold text-text-primary truncate">
              {brief.query}
            </h1>
            <p className="text-xs text-text-tertiary mt-0.5">
              Locale {brief.locale}
            </p>
          </div>
          <Link
            href="/content-brief"
            className="inline-flex h-9 px-3 items-center bg-bg-surface text-text-secondary border border-[var(--border-default)] rounded-md font-medium text-sm hover:bg-bg-elevated hover:text-text-primary transition-colors"
          >
            ← Tous les briefs
          </Link>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-8 py-8 space-y-8">
        {brief.status === 'failed' && (
          <ErrorBox message={brief.error ?? 'Erreur inconnue'} />
        )}

        {brief.status !== 'done' && (
          <PendingBox status={brief.status} />
        )}

        {brief.result && <ResultView brief={brief} />}

        {brief.serpResults.length > 0 && (
          <SerpView serp={brief.serpResults} />
        )}
      </div>
    </div>
  )
}

function PendingBox({ status }: { status: ContentBrief['status'] }) {
  const label =
    status === 'pending' ? 'En file d\'attente' : status === 'running' ? 'Génération en cours' : 'Statut inconnu'
  return (
    <div className="border border-dashed border-[var(--border-default)] rounded-md p-8 text-center bg-bg-surface">
      <p className="text-sm text-text-secondary">
        {label} — vous pouvez quitter la page, le brief s'affichera ici dès que
        prêt.
      </p>
    </div>
  )
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] rounded-md p-4">
      <div className="text-[11px] uppercase tracking-wider font-medium text-[var(--status-critical-text)] mb-1">
        Échec
      </div>
      <p className="text-sm text-text-primary">{message}</p>
    </div>
  )
}

function ResultView({ brief }: { brief: ContentBrief }) {
  const r = brief.result!
  return (
    <div className="space-y-6">
      {r.summary && (
        <Card label="Synthèse">
          <p className="text-sm text-text-primary leading-relaxed">{r.summary}</p>
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <KeyValue label="Intent" value={r.intent} />
        <KeyValue label="Audience" value={r.targetAudience} />
        <KeyValue
          label="Volume cible"
          value={r.targetWordCount ? `${r.targetWordCount} mots` : undefined}
        />
      </div>

      <Card label="Title & Meta proposés">
        <div className="space-y-3">
          <Field
            label="Title"
            value={r.suggestedTitle}
            extra={r.suggestedTitle ? `${r.suggestedTitle.length} car.` : undefined}
          />
          <Field label="H1" value={r.h1} />
          <Field
            label="Meta description"
            value={r.suggestedMeta}
            extra={r.suggestedMeta ? `${r.suggestedMeta.length} car.` : undefined}
            multiline
          />
        </div>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {r.primaryKeywords.length > 0 && (
          <KeywordsBlock label="Mots-clés principaux" items={r.primaryKeywords} />
        )}
        {r.semanticKeywords.length > 0 && (
          <KeywordsBlock label="Mots-clés sémantiques" items={r.semanticKeywords} />
        )}
      </div>

      {r.outline.length > 0 && <OutlineView outline={r.outline} />}

      {r.faq.length > 0 && (
        <Card label="FAQ suggérée">
          <ul className="space-y-2">
            {r.faq.map((q, i) => (
              <li key={i} className="flex gap-3 text-sm text-text-primary">
                <span className="text-xs tabular-nums text-text-tertiary mt-[3px] w-5">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span>{q}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {r.quickWins.length > 0 && (
        <Card label="Quick wins éditoriaux" tone="primary">
          <ul className="space-y-2">
            {r.quickWins.map((w, i) => (
              <li key={i} className="flex gap-3 text-sm text-text-primary">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-primary mt-[7px]" />
                <span>{w}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {r.notes && (
        <Card label="Notes">
          <p className="text-sm text-text-secondary">{r.notes}</p>
        </Card>
      )}
    </div>
  )
}

function OutlineView({ outline }: { outline: ContentBriefOutline[] }) {
  return (
    <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md overflow-hidden">
      <div className="px-5 pt-4 pb-2 text-[11px] uppercase tracking-wider font-medium text-primary">
        Plan H2 / H3 proposé
      </div>
      <ol className="divide-y divide-[var(--border-subtle)]">
        {outline.map((section, i) => (
          <li key={i} className="px-5 py-3">
            <div className="flex items-baseline gap-3">
              <span className="text-xs tabular-nums text-text-tertiary w-6">
                H2 · {String(i + 1).padStart(2, '0')}
              </span>
              <span className="text-sm font-semibold text-text-primary">
                {section.title}
              </span>
              {section.targetWords && (
                <span className="ml-auto text-xs text-text-tertiary tabular-nums">
                  ~{section.targetWords} mots
                </span>
              )}
            </div>
            {section.intent && (
              <p className="text-xs text-text-secondary mt-1 ml-9">
                {section.intent}
              </p>
            )}
            {section.bullets.length > 0 && (
              <ul className="mt-2 ml-9 space-y-1">
                {section.bullets.map((b, j) => (
                  <li
                    key={j}
                    className="text-xs text-text-primary flex gap-2"
                  >
                    <span className="text-text-tertiary">·</span>
                    <span>{b}</span>
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>
    </div>
  )
}

function SerpView({ serp }: { serp: SerpResult[] }) {
  return (
    <Card label={`SERP analysée — ${serp.length} résultats`}>
      <ol className="space-y-3">
        {serp.map((r) => (
          <li key={r.rank} className="border-b border-[var(--border-subtle)] last:border-0 pb-3 last:pb-0">
            <div className="flex items-baseline gap-3">
              <span className="text-xs tabular-nums text-text-tertiary w-5">
                #{r.rank}
              </span>
              <a
                href={r.url}
                target="_blank"
                rel="noreferrer"
                className="text-sm text-primary hover:underline truncate"
              >
                {r.title || r.url}
              </a>
            </div>
            <code className="block ml-8 font-mono text-[11px] text-text-tertiary truncate">
              {r.url}
            </code>
            {r.headings.length > 0 && (
              <div className="ml-8 mt-1 text-xs text-text-secondary">
                <span className="text-text-tertiary">Plan : </span>
                {r.headings.slice(0, 5).join(' · ')}
              </div>
            )}
          </li>
        ))}
      </ol>
    </Card>
  )
}

function Card({
  label,
  tone,
  children,
}: {
  label: string
  tone?: 'primary'
  children: React.ReactNode
}) {
  return (
    <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md">
      <div
        className={`px-5 pt-4 pb-2 text-[11px] uppercase tracking-wider font-medium ${
          tone === 'primary' ? 'text-primary' : 'text-text-tertiary'
        }`}
      >
        {label}
      </div>
      <div className="px-5 pb-4">{children}</div>
    </div>
  )
}

function KeyValue({
  label,
  value,
}: {
  label: string
  value?: string
}) {
  return (
    <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md p-4">
      <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-2">
        {label}
      </div>
      <div className="text-sm font-medium text-text-primary">
        {value || <span className="text-text-tertiary">—</span>}
      </div>
    </div>
  )
}

function Field({
  label,
  value,
  extra,
  multiline,
}: {
  label: string
  value?: string
  extra?: string
  multiline?: boolean
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary">
          {label}
        </span>
        {extra && (
          <span className="text-[11px] text-text-tertiary tabular-nums">
            {extra}
          </span>
        )}
      </div>
      <div
        className={`text-sm text-text-primary leading-snug ${
          multiline ? '' : 'truncate'
        }`}
      >
        {value || <span className="text-text-tertiary">—</span>}
      </div>
    </div>
  )
}

function KeywordsBlock({
  label,
  items,
}: {
  label: string
  items: string[]
}) {
  return (
    <Card label={label}>
      <div className="flex flex-wrap gap-1.5">
        {items.map((k, i) => (
          <span
            key={i}
            className="inline-flex items-center px-2 py-0.5 rounded border border-[var(--border-default)] bg-bg-elevated text-xs text-text-primary"
          >
            {k}
          </span>
        ))}
      </div>
    </Card>
  )
}
