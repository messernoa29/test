'use client'

import { listRecent } from '@/lib/api'
import type { AuditJobSummary } from '@/lib/types'
import { usePolling } from '@/lib/usePolling'
import { AuditForm } from './AuditForm'
import { RecentAuditsTable } from '@/components/dashboard/RecentAuditsTable'

interface Props {
  initial: AuditJobSummary[]
}

export function AuditListContent({ initial }: Props) {
  const hasPending = initial.some((a) => a.status === 'pending')
  const { data } = usePolling(() => listRecent(), hasPending, 3000)
  const audits = data ?? initial
  const pending = audits.filter((a) => a.status === 'pending').length

  return (
    <div className="max-w-6xl mx-auto px-8 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-text-primary mb-1">Audit Web</h1>
        <p className="text-sm text-text-secondary max-w-2xl">
          Entrez une URL. L&apos;IA crawle les pages clés, analyse 6 axes (sécurité,
          SEO, UX, contenu, performance, business) et produit un rapport PDF prêt à
          présenter à un client.
        </p>
      </div>

      <section className="mb-10">
        <div className="bg-bg-surface border border-[var(--border-subtle)] rounded-md p-5">
          <AuditForm />
        </div>
      </section>

      <section>
        <div className="flex items-end justify-between mb-4">
          <div>
            <h2 className="text-base font-semibold text-text-primary">
              Audits précédents
            </h2>
            <p className="text-xs text-text-tertiary mt-0.5">
              {audits.length} rapport{audits.length > 1 ? 's' : ''} en session
              {pending > 0 ? ` · ${pending} en cours` : ''}
            </p>
          </div>
        </div>
        <RecentAuditsTable audits={audits} />
      </section>
    </div>
  )
}
