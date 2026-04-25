'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { compareAudits, listByDomain } from '@/lib/api'
import type {
  AuditJobSummary,
  DriftFinding,
  DriftReport,
  FindingsBucket,
  ScoreDelta,
  Severity,
} from '@/lib/types'
import { scoreHexColor } from '@/lib/design'

interface Props {
  currentId: string
  domain: string
}

const AXIS_LABEL: Record<string, string> = {
  global: 'Score global',
  security: 'Sécurité',
  seo: 'SEO',
  ux: 'UX',
  content: 'Contenu',
  performance: 'Performance',
  business: 'Business',
}

const SEV_DOT: Record<Severity, string> = {
  critical: 'var(--status-critical-accent)',
  warning: 'var(--status-warning-accent)',
  ok: 'var(--status-ok-accent)',
  info: 'var(--status-info-accent)',
  missing: 'var(--status-missing-accent)',
}

export function DriftView({ currentId, domain }: Props) {
  const [siblings, setSiblings] = useState<AuditJobSummary[]>([])
  const [selectedBaseline, setSelectedBaseline] = useState<string | null>(null)
  const [report, setReport] = useState<DriftReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    listByDomain(domain)
      .then((list) => {
        if (cancelled) return
        const others = list.filter(
          (a) => a.id !== currentId && a.status === 'done',
        )
        setSiblings(others)
        if (others.length === 0) {
          setLoading(false)
          return
        }
        const baseline = others[0]!.id
        setSelectedBaseline(baseline)
        return compareAudits(currentId, baseline).then((r) => {
          if (!cancelled) setReport(r)
        })
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [currentId, domain])

  async function onSelectBaseline(id: string) {
    setSelectedBaseline(id)
    setLoading(true)
    setError(null)
    try {
      const r = await compareAudits(currentId, id)
      setReport(r)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  if (loading && !report) {
    return <Empty message="Chargement de la comparaison…" />
  }

  if (error) {
    return (
      <Empty
        message={error}
        hint="Lancez deux audits sur le même domaine puis revenez ici."
      />
    )
  }

  if (siblings.length === 0) {
    return (
      <Empty
        message="Aucun audit précédent disponible pour ce domaine."
        hint={
          <>
            Lancez un nouvel audit sur <span className="font-mono">{domain}</span>{' '}
            pour créer un point de comparaison.
          </>
        }
      />
    )
  }

  if (!report) return null

  return (
    <div className="space-y-8">
      <HeaderBar
        report={report}
        siblings={siblings}
        selected={selectedBaseline}
        onSelect={onSelectBaseline}
      />

      <section>
        <SectionTitle title="Évolution des scores" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <GlobalDeltaCard delta={report.globalDelta} />
          {report.axisDeltas
            .filter((d) => d.axis !== 'global')
            .map((d) => (
              <AxisDeltaCard key={d.axis} delta={d} />
            ))}
        </div>
      </section>

      <section>
        <SectionTitle title="Synthèse des findings" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <StatTile
            label="Résolus"
            value={report.resolvedCount}
            tone="ok"
            hint="Présents avant, plus présents"
          />
          <StatTile
            label="Nouveaux"
            value={report.appearedCount}
            tone="critical"
            hint="Apparus entre les deux audits"
          />
          <StatTile
            label="Persistants"
            value={report.persistentCount}
            tone="warning"
            hint="Présents dans les deux"
          />
        </div>
      </section>

      <section>
        <SectionTitle title="Détails par axe" />
        <div className="space-y-3">
          {Object.entries(report.perAxisFindings).map(([axis, bucket]) => (
            <AxisDriftCard
              key={axis}
              axis={axis}
              bucket={bucket}
            />
          ))}
        </div>
      </section>
    </div>
  )
}

function HeaderBar({
  report,
  siblings,
  selected,
  onSelect,
}: {
  report: DriftReport
  siblings: AuditJobSummary[]
  selected: string | null
  onSelect: (id: string) => void
}) {
  return (
    <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 bg-bg-surface border border-[var(--border-subtle)] rounded-md p-4">
      <div className="min-w-0">
        <p className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-1">
          Comparaison
        </p>
        <div className="text-sm text-text-primary">
          Audit du{' '}
          <span className="font-medium">
            {report.currentDate.slice(0, 10)}
          </span>{' '}
          vs baseline du{' '}
          <span className="font-medium">
            {report.baselineDate.slice(0, 10)}
          </span>
        </div>
      </div>
      {siblings.length > 1 && (
        <label className="flex items-center gap-2 text-xs text-text-tertiary">
          Baseline&nbsp;:
          <select
            value={selected ?? ''}
            onChange={(e) => onSelect(e.target.value)}
            className="bg-bg-surface border border-[var(--border-default)] rounded-md px-2 py-1.5 text-sm text-text-primary"
          >
            {siblings.map((a) => (
              <option key={a.id} value={a.id}>
                {a.createdAt.slice(0, 16).replace('T', ' ')}
                {typeof a.globalScore === 'number' ? ` — ${a.globalScore}/100` : ''}
              </option>
            ))}
          </select>
          <Link
            href={`/audit/${selected}`}
            className="text-primary hover:underline underline-offset-4"
          >
            Ouvrir →
          </Link>
        </label>
      )}
    </div>
  )
}

function GlobalDeltaCard({ delta }: { delta: ScoreDelta }) {
  return (
    <DeltaCard
      label="Score global"
      delta={delta}
      scoreColor={scoreHexColor(delta.current)}
      prominent
    />
  )
}

function AxisDeltaCard({ delta }: { delta: ScoreDelta }) {
  return (
    <DeltaCard
      label={AXIS_LABEL[delta.axis] ?? delta.axis}
      delta={delta}
      scoreColor={scoreHexColor(delta.current)}
    />
  )
}

function DeltaCard({
  label,
  delta,
  scoreColor,
  prominent = false,
}: {
  label: string
  delta: ScoreDelta
  scoreColor: string
  prominent?: boolean
}) {
  const arrow = delta.direction === 'up' ? '↑' : delta.direction === 'down' ? '↓' : '→'
  const tone =
    delta.direction === 'up'
      ? 'var(--status-ok-accent)'
      : delta.direction === 'down'
        ? 'var(--status-critical-accent)'
        : 'var(--text-tertiary)'
  return (
    <div
      className={`bg-bg-surface border border-[var(--border-subtle)] rounded-md p-4 ${
        prominent ? 'ring-1 ring-[var(--border-default)]' : ''
      }`}
    >
      <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-2">
        {label}
      </div>
      <div className="flex items-baseline gap-2 mb-1.5">
        <span
          className="text-3xl font-semibold tabular-nums leading-none"
          style={{ color: scoreColor }}
        >
          {delta.current}
        </span>
        <span className="text-sm text-text-tertiary">/100</span>
      </div>
      <div className="flex items-center gap-1.5 text-xs">
        <span style={{ color: tone }} className="font-medium tabular-nums">
          {arrow} {delta.delta >= 0 ? '+' : ''}
          {delta.delta}
        </span>
        <span className="text-text-tertiary">
          (avant {delta.baseline})
        </span>
      </div>
    </div>
  )
}

function StatTile({
  label,
  value,
  tone,
  hint,
}: {
  label: string
  value: number
  tone: 'ok' | 'critical' | 'warning'
  hint: string
}) {
  const color = `var(--status-${tone}-accent)`
  return (
    <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md p-4">
      <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-2">
        {label}
      </div>
      <div
        className="text-2xl font-semibold tabular-nums leading-none"
        style={{ color }}
      >
        {value}
      </div>
      <div className="mt-2 text-xs text-text-tertiary">{hint}</div>
    </div>
  )
}

function AxisDriftCard({
  axis,
  bucket,
}: {
  axis: string
  bucket: FindingsBucket
}) {
  const total =
    bucket.resolved.length + bucket.appeared.length + bucket.persistent.length
  if (total === 0) return null

  return (
    <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md overflow-hidden">
      <div className="flex items-baseline justify-between px-4 py-3 bg-bg-elevated border-b border-[var(--border-subtle)]">
        <h3 className="text-sm font-semibold text-text-primary">
          {AXIS_LABEL[axis] ?? axis}
        </h3>
        <div className="flex items-center gap-3 text-[11px] tabular-nums text-text-tertiary">
          <span>
            <span className="text-[var(--status-ok-accent)] font-medium">
              {bucket.resolved.length}
            </span>{' '}
            résolus
          </span>
          <span>
            <span className="text-[var(--status-critical-accent)] font-medium">
              {bucket.appeared.length}
            </span>{' '}
            nouveaux
          </span>
          <span>
            <span className="text-[var(--status-warning-accent)] font-medium">
              {bucket.persistent.length}
            </span>{' '}
            persistants
          </span>
        </div>
      </div>
      <div className="divide-y divide-[var(--border-subtle)]">
        {bucket.resolved.map((f, i) => (
          <FindingRowSimple key={`r-${i}`} finding={f} bucket="resolved" />
        ))}
        {bucket.appeared.map((f, i) => (
          <FindingRowSimple key={`a-${i}`} finding={f} bucket="appeared" />
        ))}
        {bucket.persistent.map((f, i) => (
          <FindingRowSimple key={`p-${i}`} finding={f} bucket="persistent" />
        ))}
      </div>
    </div>
  )
}

function FindingRowSimple({
  finding,
  bucket,
}: {
  finding: DriftFinding
  bucket: 'resolved' | 'appeared' | 'persistent'
}) {
  const glyph = bucket === 'resolved' ? '✓' : bucket === 'appeared' ? '●' : '○'
  const tone =
    bucket === 'resolved'
      ? 'var(--status-ok-accent)'
      : bucket === 'appeared'
        ? 'var(--status-critical-accent)'
        : 'var(--status-warning-accent)'
  const label =
    bucket === 'resolved' ? 'Résolu' : bucket === 'appeared' ? 'Nouveau' : 'Persistant'
  const strike = bucket === 'resolved' ? 'line-through decoration-[var(--border-default)]' : ''
  return (
    <div className="flex items-start gap-3 px-4 py-2.5">
      <span className="text-sm mt-[2px]" style={{ color: tone }}>
        {glyph}
      </span>
      <span
        className="text-[10px] uppercase tracking-wider font-medium w-20 flex-shrink-0 pt-1"
        style={{ color: tone }}
      >
        {label}
      </span>
      <span className="flex items-center gap-2 flex-shrink-0 pt-1">
        <span
          className="w-1.5 h-1.5 rounded-full"
          style={{ background: SEV_DOT[finding.severity] }}
        />
        <span className="text-[10px] uppercase tracking-wider font-medium text-text-tertiary w-16">
          {finding.severity}
        </span>
      </span>
      <span className={`text-sm text-text-primary leading-snug flex-1 ${strike}`}>
        {finding.title}
      </span>
    </div>
  )
}

function SectionTitle({ title }: { title: string }) {
  return (
    <h2 className="text-base font-semibold text-text-primary mb-3">{title}</h2>
  )
}

function Empty({
  message,
  hint,
}: {
  message: string
  hint?: React.ReactNode
}) {
  return (
    <div className="border border-dashed border-[var(--border-default)] rounded-md p-10 text-center bg-bg-surface">
      <p className="text-sm text-text-primary mb-2">{message}</p>
      {hint && <p className="text-xs text-text-tertiary">{hint}</p>}
    </div>
  )
}
