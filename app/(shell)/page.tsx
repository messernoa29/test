import { listRecent } from '@/lib/api'
import { DashboardContent } from '@/components/dashboard/DashboardContent'

export const dynamic = 'force-dynamic'

export default async function DashboardPage() {
  const audits = await safeList()
  return <DashboardContent initial={audits} />
}

async function safeList() {
  try {
    return await listRecent()
  } catch {
    return []
  }
}
