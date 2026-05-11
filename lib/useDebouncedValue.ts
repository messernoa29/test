'use client'

import { useEffect, useState } from 'react'

/**
 * Returns a debounced copy of `value`: it only updates `delayMs` after the
 * last change. Used to keep large client-side filters (crawl table, page
 * list) from re-rendering on every keystroke.
 */
export function useDebouncedValue<T>(value: T, delayMs = 200): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(id)
  }, [value, delayMs])
  return debounced
}
