import { notFound } from 'next/navigation'
import { getAiVisibilityCheck } from '@/lib/api'
import type { AiVisibilityCheck } from '@/lib/types'
import { AiVisibilityDetail } from '@/components/ai-visibility/AiVisibilityDetail'

interface PageProps {
  params: { id: string }
}

export const dynamic = 'force-dynamic'

export default async function AiVisibilityDetailPage({ params }: PageProps) {
  let check: AiVisibilityCheck
  try {
    check = await getAiVisibilityCheck(params.id)
  } catch (e) {
    const msg = (e as Error).message ?? ''
    if (msg.includes('404') || msg.includes('introuvable')) notFound()
    throw e
  }
  return <AiVisibilityDetail initial={check} />
}
