'use client'

import { useEffect, useState } from 'react'
import { notFound, useParams } from 'next/navigation'
import { AuthRequiredError, getCompetitorBattle } from '@/lib/api'
import type { CompetitorBattle } from '@/lib/types'
import { CompetitorDetail } from '@/components/competitor/CompetitorDetail'

export default function CompetitorBattlePage() {
  const params = useParams<{ id: string }>()
  const id = params?.id
  const [battle, setBattle] = useState<CompetitorBattle | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    getCompetitorBattle(id)
      .then((b) => {
        if (!cancelled) setBattle(b)
      })
      .catch((e) => {
        if (cancelled) return
        if (e instanceof AuthRequiredError) return
        const msg = (e as Error).message ?? ''
        if (msg.includes('404') || msg.includes('not found')) {
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

  if (!battle) {
    return (
      <div className="max-w-2xl mx-auto px-8 py-16 text-text-secondary text-sm">
        Chargement…
      </div>
    )
  }

  return <CompetitorDetail initial={battle} />
}
