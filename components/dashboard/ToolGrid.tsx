import Link from 'next/link'
import { TOOLS } from '@/lib/tools'
import { Icon } from '@/components/shell/Icon'

export function ToolGrid() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
      {TOOLS.map((tool) => {
        const disabled = tool.status !== 'live'
        const cls = `relative group p-5 rounded-md border transition-colors ${
          disabled
            ? 'border-[var(--border-subtle)] bg-bg-surface cursor-not-allowed'
            : 'border-[var(--border-subtle)] bg-bg-surface hover:border-[var(--border-default)] hover:bg-bg-elevated'
        }`
        const content = (
          <>
            <div className="flex items-center justify-between mb-4">
              <span
                className={`w-9 h-9 rounded-md flex items-center justify-center ${
                  disabled
                    ? 'bg-bg-elevated text-text-tertiary'
                    : 'bg-[var(--primary-bg)] text-primary'
                }`}
              >
                <Icon name={tool.icon} size={18} />
              </span>
              {disabled && (
                <span className="text-[10px] tracking-wider uppercase font-medium text-text-tertiary bg-bg-elevated px-2 py-0.5 rounded">
                  {tool.status === 'soon' ? 'Bientôt' : 'Planifié'}
                </span>
              )}
            </div>
            <h3 className="text-base font-semibold text-text-primary mb-1">
              {tool.name}
            </h3>
            <p className="text-sm text-text-secondary leading-relaxed">
              {tool.description}
            </p>
            {!disabled && (
              <div className="mt-4 text-xs font-medium text-primary opacity-0 group-hover:opacity-100 transition-opacity">
                Ouvrir →
              </div>
            )}
          </>
        )
        return disabled ? (
          <div key={tool.id} className={cls}>
            {content}
          </div>
        ) : (
          <Link key={tool.id} href={tool.href} className={cls}>
            {content}
          </Link>
        )
      })}
    </div>
  )
}
