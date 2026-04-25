import { listRecent } from '@/lib/api'
import { AuditListContent } from '@/components/audit/AuditListContent'

export const dynamic = 'force-dynamic'

export default async function AuditToolPage() {
  const audits = await safeList()
  return <AuditListContent initial={audits} />
}

async function safeList() {
  try {
    return await listRecent()
  } catch {
    return []
  }
}
