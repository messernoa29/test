import { listCompetitorBattles } from '@/lib/api'
import { CompetitorList } from '@/components/competitor/CompetitorList'

export const dynamic = 'force-dynamic'

export default async function CompetitorWatchPage() {
  const battles = await safeList()
  return <CompetitorList initial={battles} />
}

async function safeList() {
  try {
    return await listCompetitorBattles()
  } catch {
    return []
  }
}
