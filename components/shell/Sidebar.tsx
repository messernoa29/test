'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import type { AuditJobSummary } from '@/lib/types'
import { listRecent } from '@/lib/api'
import { TOOLS } from '@/lib/tools'
import { Icon } from './Icon'

export function Sidebar() {
  const pathname = usePathname()
  const [collapsed, setCollapsed] = useState(false)
  const [recent, setRecent] = useState<AuditJobSummary[]>([])

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const fetchOnce = async () => {
      try {
        const data = await listRecent()
        if (cancelled) return
        setRecent(data)
        const hasPending = data.some((a) => a.status === 'pending')
        if (hasPending) {
          timer = setTimeout(fetchOnce, 3000)
        }
      } catch {
        if (!cancelled) setRecent([])
      }
    }

    fetchOnce()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [pathname])

  return (
    <aside
      className={`fixed top-0 left-0 bottom-0 z-20 flex flex-col border-r border-[var(--border-subtle)] bg-bg-surface transition-[width] duration-200 ${
        collapsed ? 'w-[56px]' : 'w-[240px]'
      }`}
    >
      {/* Brand */}
      <div className="h-14 px-4 flex items-center justify-between border-b border-[var(--border-subtle)]">
        <Link href="/" className="flex items-center gap-2.5 min-w-0">
          <span className="w-7 h-7 rounded-md flex items-center justify-center bg-primary text-white font-semibold text-[13px] flex-shrink-0">
            A
          </span>
          {!collapsed && (
            <span className="text-[14px] font-semibold text-text-primary truncate">
              Audit Bureau
            </span>
          )}
        </Link>
        <button
          onClick={() => setCollapsed((v) => !v)}
          className="text-text-tertiary hover:text-text-primary p-1 -mr-1 transition-colors"
          aria-label="Réduire la sidebar"
        >
          <span className="inline-block text-xs">{collapsed ? '›' : '‹'}</span>
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-3">
        <NavSection label="Tableau de bord" collapsed={collapsed}>
          <NavItem
            href="/"
            icon="dashboard"
            label="Dashboard"
            active={pathname === '/'}
            collapsed={collapsed}
          />
        </NavSection>

        <NavSection label="Outils" collapsed={collapsed}>
          {TOOLS.map((tool) => {
            const active =
              tool.href === '/'
                ? pathname === '/'
                : pathname.startsWith(tool.href)
            return (
              <NavItem
                key={tool.id}
                href={tool.status === 'live' ? tool.href : '#'}
                icon={tool.icon}
                label={tool.name}
                active={active}
                disabled={tool.status !== 'live'}
                badge={
                  tool.status === 'soon'
                    ? 'SOON'
                    : tool.status === 'planned'
                      ? 'PLANNED'
                      : undefined
                }
                collapsed={collapsed}
              />
            )
          })}
        </NavSection>

        {!collapsed && recent.length > 0 && (
          <NavSection label="Historique" collapsed={collapsed}>
            <ul className="px-2 space-y-0.5">
              {recent.slice(0, 8).map((a) => {
                const active = pathname === `/audit/${a.id}`
                const pending = a.status === 'pending'
                const failed = a.status === 'failed'
                return (
                  <li key={a.id}>
                    <Link
                      href={`/audit/${a.id}`}
                      className={`flex items-center gap-2 px-2 py-1.5 rounded-md text-xs transition-colors ${
                        active
                          ? 'bg-[var(--primary-bg)] text-primary'
                          : 'text-text-secondary hover:text-text-primary hover:bg-bg-elevated'
                      }`}
                    >
                      <span
                        className="inline-block w-1 h-4 rounded-full flex-shrink-0"
                        style={{
                          background: pending
                            ? 'var(--status-info-accent)'
                            : failed
                              ? 'var(--status-critical-accent)'
                              : scoreColor(a.globalScore ?? 0),
                        }}
                      />
                      <span className="truncate flex-1">{a.domain}</span>
                      {pending ? (
                        <span
                          className="w-1.5 h-1.5 rounded-full bg-[var(--status-info-accent)] flex-shrink-0"
                          style={{ animation: 'pulse-critical 1.5s ease-in-out infinite' }}
                          aria-label="En cours"
                        />
                      ) : failed ? (
                        <span className="text-[10px] uppercase tracking-wider text-[var(--status-critical-text)]">
                          !
                        </span>
                      ) : (
                        <span className="text-[11px] tabular-nums text-text-tertiary">
                          {a.globalScore ?? '—'}
                        </span>
                      )}
                    </Link>
                  </li>
                )
              })}
            </ul>
          </NavSection>
        )}

        <NavSection label="Système" collapsed={collapsed}>
          <NavItem
            href="/settings"
            icon="settings"
            label="Réglages"
            active={pathname.startsWith('/settings')}
            collapsed={collapsed}
          />
        </NavSection>
      </nav>

      {/* Footer status */}
      <div
        className={`border-t border-[var(--border-subtle)] px-4 py-2.5 text-[11px] text-text-tertiary ${
          collapsed ? 'text-center' : ''
        }`}
      >
        {collapsed ? (
          <span
            className="inline-block w-1.5 h-1.5 rounded-full"
            style={{ background: 'var(--status-ok-accent)' }}
          />
        ) : (
          <div className="flex items-center gap-2">
            <span
              className="inline-block w-1.5 h-1.5 rounded-full"
              style={{ background: 'var(--status-ok-accent)' }}
            />
            <span>API connectée · v0.1</span>
          </div>
        )}
      </div>
    </aside>
  )
}

function NavSection({
  label,
  collapsed,
  children,
}: {
  label: string
  collapsed: boolean
  children: React.ReactNode
}) {
  return (
    <div className="mb-4">
      {!collapsed && (
        <div className="px-4 mb-1.5 text-[10px] uppercase tracking-wider font-semibold text-text-tertiary">
          {label}
        </div>
      )}
      {children}
    </div>
  )
}

interface NavItemProps {
  href: string
  icon: React.ComponentProps<typeof Icon>['name']
  label: string
  active?: boolean
  disabled?: boolean
  badge?: string
  collapsed?: boolean
}

function NavItem({ href, icon, label, active, disabled, badge, collapsed }: NavItemProps) {
  const classes = `flex items-center gap-2.5 mx-2 px-2 py-1.5 rounded-md text-sm transition-colors ${
    disabled
      ? 'text-text-tertiary cursor-not-allowed'
      : active
        ? 'bg-[var(--primary-bg)] text-primary font-medium'
        : 'text-text-secondary hover:text-text-primary hover:bg-bg-elevated'
  }`

  const content = (
    <>
      <Icon name={icon} size={16} className="flex-shrink-0" />
      {!collapsed && (
        <>
          <span className="flex-1 truncate">{label}</span>
          {badge && (
            <span className="text-[9px] tracking-wider font-semibold text-text-tertiary bg-bg-elevated px-1.5 py-0.5 rounded">
              {badge}
            </span>
          )}
        </>
      )}
    </>
  )

  if (disabled) {
    return (
      <div className={classes} title={collapsed ? label : undefined}>
        {content}
      </div>
    )
  }
  return (
    <Link href={href} className={classes} title={collapsed ? label : undefined}>
      {content}
    </Link>
  )
}

function scoreColor(score: number): string {
  if (score < 40) return 'var(--status-critical-accent)'
  if (score < 60) return 'var(--status-warning-accent)'
  if (score < 80) return 'var(--status-info-accent)'
  return 'var(--status-ok-accent)'
}
