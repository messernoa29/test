import type { MissingPage } from '@/lib/types'
import { Badge } from '@/components/ui/Badge'

interface Props {
  pages: MissingPage[]
}

export function MissingPagesTable({ pages }: Props) {
  return (
    <div className="border border-[var(--border-subtle)] rounded-md overflow-hidden bg-bg-surface">
      <div className="grid grid-cols-[1.4fr_2fr_110px_100px] bg-bg-elevated border-b border-[var(--border-subtle)]">
        {['URL recommandée', 'Raison', 'Vol./mois', 'Priorité'].map((h) => (
          <div
            key={h}
            className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary px-4 py-2.5"
          >
            {h}
          </div>
        ))}
      </div>
      {pages.map((p, i) => {
        const priority = (p.priority ?? 'medium') as MissingPage['priority']
        return (
          <div
            key={i}
            className="grid grid-cols-[1.4fr_2fr_110px_100px] border-b border-[var(--border-subtle)] last:border-0 items-start hover:bg-bg-elevated transition-colors"
          >
            <code className="font-mono text-xs text-text-primary px-4 py-3 break-all">
              {p.url || '—'}
            </code>
            <div className="text-sm text-text-secondary px-4 py-3 leading-snug">
              {p.reason || '—'}
            </div>
            <div className="font-mono text-xs text-text-primary tabular-nums px-4 py-3">
              {typeof p.estimatedSearchVolume === 'number' &&
              p.estimatedSearchVolume > 0
                ? `~${p.estimatedSearchVolume}`
                : '—'}
            </div>
            <div className="px-4 py-3">
              <Badge kind={priority}>{priority.toUpperCase()}</Badge>
            </div>
          </div>
        )
      })}
    </div>
  )
}
