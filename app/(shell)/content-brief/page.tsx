import { listContentBriefs } from '@/lib/api'
import { BriefList } from '@/components/brief/BriefList'

export const dynamic = 'force-dynamic'

export default async function ContentBriefPage() {
  const briefs = await safeList()
  return <BriefList initial={briefs} />
}

async function safeList() {
  try {
    return await listContentBriefs()
  } catch {
    return []
  }
}
