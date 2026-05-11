'use client'

import { useEffect, useState } from 'react'
import { notFound, useParams } from 'next/navigation'
import { AuthRequiredError, getAiVisibilityCheck } from '@/lib/api'
import type { AiVisibilityCheck } from '@/lib/types'
import { AiVisibilityDetail } from '@/components/ai-visibility/AiVisibilityDetail'

export default function AiVisibilityDetailPage() {
  const params = useParams<{ id: string }>()
  const id = params?.id
  const [check, setCheck] = useState<AiVisibilityCheck | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    getAiVisibilityCheck(id)
      .then((c) => {
        if (!cancelled) setCheck(c)
      })
      .catch((e) => {
        if (cancelled) return
        if (e instanceof AuthRequiredError) return
        const msg = (e as Error).message ?? ''
        if (msg.includes('404') || msg.includes('introuvable')) {
          notFound()
          return
        }
        setError(msg || 'Erreur de chargement')
      })
    return () => {
      cancelled = true
    }
  }, [id])

  if (error) {
    return (
      <div className="max-w-2xl mx-auto px-8 py-16 text-text-secondary">
        <h1 className="text-xl font-semibold text-text-primary mb-2">
          Impossible de charger cette analyse
        </h1>
        <p className="text-sm">{error}</p>
      </div>
    )
  }

  if (!check) {
    return (
      <div className="max-w-2xl mx-auto px-8 py-16 text-text-secondary text-sm">
        Chargement…
      </div>
    )
  }

  return <AiVisibilityDetail initial={check} />
}
