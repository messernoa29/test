'use client'

import { useEffect, useState } from 'react'
import { notFound, useParams } from 'next/navigation'
import { AuthRequiredError, getContentBrief } from '@/lib/api'
import type { ContentBrief } from '@/lib/types'
import { BriefDetail } from '@/components/brief/BriefDetail'

export default function BriefDetailPage() {
  const params = useParams<{ id: string }>()
  const id = params?.id
  const [brief, setBrief] = useState<ContentBrief | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    getContentBrief(id)
      .then((b) => {
        if (!cancelled) setBrief(b)
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
          Impossible de charger ce brief
        </h1>
        <p className="text-sm">{error}</p>
      </div>
    )
  }

  if (!brief) {
    return (
      <div className="max-w-2xl mx-auto px-8 py-16 text-text-secondary text-sm">
        Chargement…
      </div>
    )
  }

  return <BriefDetail initial={brief} />
}
