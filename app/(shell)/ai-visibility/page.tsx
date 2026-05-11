'use client'

import { useEffect, useState } from 'react'
import { AuthRequiredError, listAiVisibilityChecks } from '@/lib/api'
import type { AiVisibilityCheck } from '@/lib/types'
import { AiVisibilityList } from '@/components/ai-visibility/AiVisibilityList'

export default function AiVisibilityPage() {
  const [checks, setChecks] = useState<AiVisibilityCheck[] | null>(null)

  useEffect(() => {
    let cancelled = false
    listAiVisibilityChecks()
      .then((data) => {
        if (!cancelled) setChecks(data)
      })
      .catch((e) => {
        if (cancelled) return
        if (e instanceof AuthRequiredError) return
        setChecks([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (checks === null) {
    return (
      <div className="max-w-2xl mx-auto px-8 py-16 text-text-secondary text-sm">
        Chargement…
      </div>
    )
  }

  return <AiVisibilityList initial={checks} />
}
