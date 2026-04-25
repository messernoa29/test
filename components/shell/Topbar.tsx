'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { ThemeToggle } from './ThemeToggle'

export interface Breadcrumb {
  label: string
  href?: string
}

interface TopbarProps {
  crumbs?: Breadcrumb[]
  right?: React.ReactNode
}

export function Topbar({ crumbs, right }: TopbarProps) {
  const pathname = usePathname()
  const computed = crumbs ?? defaultCrumbs(pathname)

  return (
    <header className="sticky top-0 z-10 h-14 bg-bg-surface border-b border-[var(--border-subtle)]">
      <div className="h-full px-6 flex items-center gap-3">
        <nav className="flex items-center gap-2 text-sm min-w-0 flex-1">
          {computed.map((c, i) => {
            const last = i === computed.length - 1
            return (
              <span key={i} className="flex items-center gap-2 min-w-0">
                {c.href && !last ? (
                  <Link
                    href={c.href}
                    className="text-text-tertiary hover:text-text-primary transition-colors truncate"
                  >
                    {c.label}
                  </Link>
                ) : (
                  <span
                    className={`${last ? 'text-text-primary font-medium' : 'text-text-tertiary'} truncate`}
                  >
                    {c.label}
                  </span>
                )}
                {!last && (
                  <span className="text-text-tertiary flex-shrink-0">/</span>
                )}
              </span>
            )
          })}
        </nav>

        <div className="flex items-center gap-2 flex-shrink-0">
          {right}
          <ThemeToggle />
          <UserPill />
        </div>
      </div>
    </header>
  )
}

function UserPill() {
  return (
    <div className="flex items-center gap-2 pl-3 border-l border-[var(--border-subtle)]">
      <span className="w-7 h-7 rounded-full flex items-center justify-center bg-primary text-white font-semibold text-[11px]">
        AG
      </span>
      <div className="hidden md:flex flex-col leading-tight">
        <span className="text-xs font-medium text-text-primary">Agence</span>
        <span className="text-[10px] text-text-tertiary">Admin</span>
      </div>
    </div>
  )
}

function defaultCrumbs(pathname: string): Breadcrumb[] {
  if (pathname === '/') return [{ label: 'Dashboard' }]
  const parts = pathname.split('/').filter(Boolean)
  const crumbs: Breadcrumb[] = [{ label: 'Dashboard', href: '/' }]
  const acc: string[] = []
  parts.forEach((p) => {
    acc.push(p)
    crumbs.push({ label: humanize(p), href: `/${acc.join('/')}` })
  })
  if (crumbs.length > 0) delete crumbs[crumbs.length - 1]!.href
  return crumbs
}

function humanize(slug: string): string {
  const map: Record<string, string> = {
    audit: 'Audit Web',
    settings: 'Réglages',
    'seo-tracker': 'SEO Tracker',
    'competitor-watch': 'Competitor Watch',
    'content-brief': 'Content Brief',
    'perf-monitor': 'Performance Monitor',
  }
  return map[slug] ?? slug
}
