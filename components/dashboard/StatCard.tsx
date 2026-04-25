interface StatCardProps {
  label: string
  value: string | number
  hint?: string
  tone?: 'default' | 'critical' | 'warning' | 'ok'
}

const TONE: Record<NonNullable<StatCardProps['tone']>, string> = {
  default: 'var(--text-primary)',
  critical: 'var(--status-critical-accent)',
  warning: 'var(--status-warning-accent)',
  ok: 'var(--status-ok-accent)',
}

export function StatCard({ label, value, hint, tone = 'default' }: StatCardProps) {
  return (
    <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md p-5">
      <div className="text-[11px] uppercase tracking-wider text-text-tertiary font-medium mb-2">
        {label}
      </div>
      <div
        className="text-3xl font-semibold tracking-tight tabular-nums"
        style={{ color: TONE[tone] }}
      >
        {value}
      </div>
      {hint && (
        <div className="mt-2 text-xs text-text-secondary">{hint}</div>
      )}
    </div>
  )
}
