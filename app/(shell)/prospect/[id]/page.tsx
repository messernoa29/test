'use client'

import { useEffect, useRef, useState } from 'react'
import { notFound, useParams } from 'next/navigation'
import { AuthRequiredError, getProspect } from '@/lib/api'
import type { ProspectSheet } from '@/lib/types'
import { ProspectSheetView } from '@/components/prospect/ProspectSheetView'

export default function ProspectDetailPage() {
  const params = useParams<{ id: string }>()
  const id = params?.id
  const [sheet, setSheet] = useState<ProspectSheet | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!id) return
    let cancelled = false

    const tick = async () => {
      try {
        const next = await getProspect(id)
        if (cancelled) return
        setSheet(next)
        if (next.status === 'pending' || next.status === 'running') {
          timerRef.current = setTimeout(tick, 2000)
        }
      } catch (e) {
        if (cancelled) return
        if (e instanceof AuthRequiredError) return
        const msg = (e as Error).message ?? ''
        if (msg.includes('404') || msg.includes('introuvable')) {
          notFound()
          return
        }
        setError(msg || 'Erreur de chargement')
      }
    }

    tick()
    return () => {
      cancelled = true
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [id])

  if (error) {
    return (
      <div className="max-w-2xl mx-auto px-8 py-16 text-text-secondary">
        <h1 className="text-xl font-semibold text-text-primary mb-2">
          Impossible de charger cette fiche
        </h1>
        <p className="text-sm">{error}</p>
      </div>
    )
  }

  if (!sheet) {
    return (
      <div className="max-w-2xl mx-auto px-8 py-16 text-text-secondary text-sm">
        Chargement…
      </div>
    )
  }

  if (sheet.status === 'pending' || sheet.status === 'running') {
    return (
      <div className="max-w-2xl mx-auto px-8 py-20 text-center">
        <div className="inline-flex items-center gap-3 text-text-secondary">
          <span
            className="w-3 h-3 rounded-full bg-primary"
            style={{ animation: 'pulse-critical 1.5s ease-in-out infinite' }}
          />
          <span className="text-sm">
            {sheet.status === 'pending'
              ? 'En file d’attente…'
              : 'Génération de la fiche prospect en cours…'}
          </span>
        </div>
        <p className="text-xs text-text-tertiary mt-3">
          On analyse {sheet.domain}. Vous pouvez quitter la page, la fiche
          s’affichera ici dès qu’elle est prête.
        </p>
      </div>
    )
  }

  return <ProspectSheetView sheet={sheet} />
}
