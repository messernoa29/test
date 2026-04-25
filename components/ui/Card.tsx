import type { StatusKind } from '@/lib/design'

const ACCENT_COLOR: Record<StatusKind, string> = {
  critical: 'var(--status-critical-accent)',
  warning: 'var(--status-warning-accent)',
  ok: 'var(--status-ok-accent)',
  info: 'var(--status-info-accent)',
  missing: 'var(--status-missing-accent)',
  improve: 'var(--status-warning-accent)',
}

interface CardProps {
  accent?: StatusKind
  className?: string
  children: React.ReactNode
}

export function Card({ accent, className = '', children }: CardProps) {
  const style = accent
    ? ({ ['--card-accent' as string]: ACCENT_COLOR[accent] } as React.CSSProperties)
    : undefined
  return (
    <div
      className={`relative overflow-hidden bg-bg-surface border-[0.5px] border-[var(--border-default)] rounded-md px-6 py-5 ${className}`}
      style={style}
    >
      {accent && (
        <span
          className="absolute left-0 top-0 bottom-0 w-[3px]"
          style={{ background: 'var(--card-accent)' }}
        />
      )}
      {children}
    </div>
  )
}
