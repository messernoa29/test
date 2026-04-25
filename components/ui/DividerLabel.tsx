interface DividerLabelProps {
  children: React.ReactNode
  className?: string
}

export function DividerLabel({ children, className = '' }: DividerLabelProps) {
  return (
    <div
      className={`flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.12em] text-text-tertiary ${className}`}
    >
      <span className="flex-1 h-[0.5px] bg-[var(--border-default)]" />
      <span>{children}</span>
      <span className="flex-1 h-[0.5px] bg-[var(--border-default)]" />
    </div>
  )
}
