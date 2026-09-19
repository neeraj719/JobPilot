import { Send } from 'lucide-react'

import { EmptyState } from '@/components/common/EmptyState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'

/**
 * Placeholder shell. A page agent replaces this file's contents with the real
 * screen — keep the default export and the PageContainer/PageHeader wrapper.
 */
export default function ApplicationsPage() {
  return (
    <PageContainer>
      <PageHeader title="Applications" description="Everything you have sent, with the status each company moved it to." />
      <EmptyState
        icon={Send}
        title="Coming soon"
        description="The tracker backed by GET /applications, filterable by status, source, company and date."
      />
    </PageContainer>
  )
}
