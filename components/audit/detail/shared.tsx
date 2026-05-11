'use client'

export function SectionHeader({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="mb-4">
      <h2 className="text-base font-semibold text-text-primary">{title}</h2>
      {sub && <p className="text-xs text-text-tertiary mt-0.5">{sub}</p>}
    </div>
  )
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="border border-dashed border-[var(--border-default)] rounded-md p-10 text-center bg-bg-surface">
      <p className="text-sm text-text-tertiary max-w-md mx-auto">{message}</p>
    </div>
  )
}

export function MiniStat({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone: 'critical' | 'warning' | 'default'
}) {
  const color =
    tone === 'critical'
      ? 'var(--status-critical-accent)'
      : tone === 'warning'
        ? 'var(--status-warning-accent)'
        : 'var(--text-primary)'
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
    </div>
  )
}
