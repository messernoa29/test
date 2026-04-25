import { listAiVisibilityChecks } from '@/lib/api'
import { AiVisibilityList } from '@/components/ai-visibility/AiVisibilityList'

export const dynamic = 'force-dynamic'

export default async function AiVisibilityPage() {
  const checks = await safeList()
  return <AiVisibilityList initial={checks} />
}

async function safeList() {
  try {
    return await listAiVisibilityChecks()
  } catch {
    return []
  }
}
