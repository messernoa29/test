import { notFound } from 'next/navigation'
import { getCompetitorBattle } from '@/lib/api'
import type { CompetitorBattle } from '@/lib/types'
import { CompetitorDetail } from '@/components/competitor/CompetitorDetail'

interface PageProps {
  params: { id: string }
}

export const dynamic = 'force-dynamic'

export default async function CompetitorBattlePage({ params }: PageProps) {
  let battle: CompetitorBattle
  try {
    battle = await getCompetitorBattle(params.id)
  } catch (e) {
    const msg = (e as Error).message ?? ''
    if (msg.includes('404') || msg.includes('not found')) notFound()
    throw e
  }
  return <CompetitorDetail initial={battle} />
}
