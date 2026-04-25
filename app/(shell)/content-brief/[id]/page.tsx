import { notFound } from 'next/navigation'
import { getContentBrief } from '@/lib/api'
import type { ContentBrief } from '@/lib/types'
import { BriefDetail } from '@/components/brief/BriefDetail'

interface PageProps {
  params: { id: string }
}

export const dynamic = 'force-dynamic'

export default async function BriefDetailPage({ params }: PageProps) {
  let brief: ContentBrief
  try {
    brief = await getContentBrief(params.id)
  } catch (e) {
    const msg = (e as Error).message ?? ''
    if (msg.includes('404') || msg.includes('introuvable')) notFound()
    throw e
  }
  return <BriefDetail initial={brief} />
}
