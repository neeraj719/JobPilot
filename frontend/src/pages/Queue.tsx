import { ListChecks } from 'lucide-react'

import { EmptyState } from '@/components/common/EmptyState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'

/**
 * Placeholder shell. A page agent replaces this file's contents with the real
 * screen — keep the default export and the PageContainer/PageHeader wrapper.
 */
export default function QueuePage() {
  return (
    <PageContainer>
      <PageHeader title="Application Queue" description="Applications prepared by the automation, ordered by company priority and match score." />
      <EmptyState
        icon={ListChecks}
        title="Coming soon"
        description="The approval centre backed by GET /applications/queue — review answers, resolve pauses and approve sends."
      />
    </PageContainer>
  )
}
