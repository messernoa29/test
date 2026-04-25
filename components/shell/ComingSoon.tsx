import Link from 'next/link'
import { Icon } from './Icon'
import type { ToolIcon } from '@/lib/tools'

interface ComingSoonProps {
  tool: string
  icon: ToolIcon
  description: string
  status: 'Bientôt disponible' | 'Planifié'
  features?: string[]
}

export function ComingSoon({
  tool,
  icon,
  description,
  status,
  features,
}: ComingSoonProps) {
  return (
    <div className="max-w-3xl mx-auto px-8 py-12">
      <div className="flex items-center gap-4 mb-6">
        <span className="w-12 h-12 rounded-md flex items-center justify-center bg-[var(--primary-bg)] text-primary">
          <Icon name={icon} size={22} />
        </span>
        <div>
          <p className="text-xs text-text-tertiary mb-0.5">Outil · {status}</p>
          <h1 className="text-xl font-semibold text-text-primary">{tool}</h1>
        </div>
      </div>

      <p className="text-base text-text-secondary leading-relaxed mb-8">{description}</p>

      {features && features.length > 0 && (
        <section className="mb-8">
          <div className="text-[11px] uppercase tracking-wider font-medium text-text-tertiary mb-3">
            Fonctionnalités prévues
          </div>
          <ul className="space-y-2.5">
            {features.map((feat, i) => (
              <li
                key={i}
                className="flex items-start gap-3 text-sm text-text-primary leading-relaxed"
              >
                <span className="text-xs tabular-nums text-text-tertiary mt-[3px] flex-shrink-0 w-5">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span>{feat}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="border-t border-[var(--border-subtle)] pt-5">
        <Link
          href="/"
          className="text-sm font-medium text-primary hover:underline underline-offset-4"
        >
          ← Retour au dashboard
        </Link>
      </div>
    </div>
  )
}
