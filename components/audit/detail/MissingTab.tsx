'use client'

import type { AuditResult } from '@/lib/types'
import { MissingPagesTable } from '../MissingPagesTable'
import { EmptyState, SectionHeader } from './shared'

export function MissingTab({ pages }: { pages: NonNullable<AuditResult['missingPages']> }) {
  return (
    <div className="space-y-5">
      <SectionHeader
        title="Pages stratégiques manquantes"
        sub={pages.length > 0 ? `${pages.length} pages à créer` : 'Aucune page manquante détectée'}
      />
      {pages.length === 0 ? (
        <EmptyState message="L'IA n'a identifié aucune page stratégique manquante pour ce site, ou la détection n'a pas pu aboutir." />
      ) : (
        <MissingPagesTable pages={pages} />
      )}
    </div>
  )
}
