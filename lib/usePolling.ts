'use client'

import { useEffect, useRef, useState } from 'react'

/**
 * Lightweight polling hook. Invokes `fetcher` immediately, then every
 * `intervalMs` milliseconds as long as `active` is true. Tracks consecutive
 * failures so the UI can show a warning when the backend disappears.
 */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  active: boolean,
  intervalMs: number,
): {
  data: T | null
  error: Error | null
  consecutiveFailures: number
  refresh: () => void
} {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [consecutiveFailures, setFailures] = useState(0)
  const [tick, setTick] = useState(0)
  const failuresRef = useRef(0)

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const run = async () => {
      try {
        const next = await fetcher()
        if (cancelled) return
        failuresRef.current = 0
        setFailures(0)
        setData(next)
        setError(null)
      } catch (e) {
        if (cancelled) return
        failuresRef.current += 1
        setFailures(failuresRef.current)
        setError(e as Error)
      }
      if (!cancelled && active) {
        timer = setTimeout(run, intervalMs)
      }
    }

    run()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, intervalMs, tick])

  return {
    data,
    error,
    consecutiveFailures,
    refresh: () => setTick((n) => n + 1),
  }
}
