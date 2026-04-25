import type { StatusKind } from '@/lib/design'

const STYLES: Record<StatusKind | 'high' | 'medium' | 'low', string> = {
  critical:
    'bg-[var(--status-critical-bg)] text-[var(--status-critical-text)] border-[var(--status-critical-border)]',
  warning:
    'bg-[var(--status-warning-bg)] text-[var(--status-warning-text)] border-[var(--status-warning-border)]',
  ok: 'bg-[var(--status-ok-bg)] text-[var(--status-ok-text)] border-[var(--status-ok-border)]',
  info: 'bg-[var(--status-info-bg)] text-[var(--status-info-text)] border-[var(--status-info-border)]',
  missing:
    'bg-[var(--status-missing-bg)] text-[var(--status-missing-text)] border-[var(--status-missing-border)]',
  improve:
    'bg-[var(--status-warning-bg)] text-[var(--status-warning-text)] border-[var(--status-warning-border)]',
  high: 'bg-[var(--status-critical-bg)] text-[var(--status-critical-text)] border-[var(--status-critical-border)]',
  medium:
    'bg-[var(--status-warning-bg)] text-[var(--status-warning-text)] border-[var(--status-warning-border)]',
  low: 'bg-[var(--status-info-bg)] text-[var(--status-info-text)] border-[var(--status-info-border)]',
}

interface BadgeProps {
  kind: StatusKind | 'high' | 'medium' | 'low'
  children: React.ReactNode
  withDot?: boolean
}

export function Badge({ kind, children, withDot = false }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded border text-[10px] font-medium uppercase tracking-wider ${STYLES[kind]}`}
    >
      {withDot && (
        <span className="inline-block w-1 h-1 rounded-full bg-current flex-shrink-0" />
      )}
      {children}
    </span>
  )
}
