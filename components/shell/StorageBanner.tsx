'use client'

import { useEffect, useState } from 'react'
import { fetchHealth } from '@/lib/api'

/**
 * Shows a warning strip when the backend is running on the in-memory
 * fallback store (DATABASE_URL missing or the SQL backend failed to
 * connect). In that mode every audit and tracker is lost on the next
 * deploy / restart, so users should know before they rely on history.
 */
export function StorageBanner() {
  const [degraded, setDegraded] = useState(false)

  useEffect(() => {
    let cancelled = false
    const check = async () => {
      try {
        const h = await fetchHealth()
        if (!cancelled) setDegraded(h.persistentStorage === false)
      } catch {
        // Health unreachable — don't show the banner; the page itself will
        // surface connection problems.
      }
    }
    check()
    const id = setInterval(check, 60_000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  if (!degraded) return null

  return (
    <div className="px-4 py-2 text-xs bg-[var(--status-warning-bg)] border-b border-[var(--status-warning-border)] text-[var(--status-warning-text)]">
      <strong>Mode dégradé</strong> — la base de données n&apos;est pas
      connectée. Les audits et historiques sont stockés en mémoire et seront
      perdus au prochain redémarrage du serveur. Vérifiez{' '}
      <code className="font-mono">DATABASE_URL</code> côté backend.
    </div>
  )
}
