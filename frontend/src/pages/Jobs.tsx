import { Briefcase } from 'lucide-react'

import { EmptyState } from '@/components/common/EmptyState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'

/**
 * Placeholder shell. A page agent replaces this file's contents with the real
 * screen — keep the default export and the PageContainer/PageHeader wrapper.
 */
export default function JobsPage() {
  return (
    <PageContainer>
      <PageHeader title="Jobs" description="Every posting discovered across your platforms, deduplicated and scored against your resume." />
      <EmptyState
        icon={Briefcase}
        title="Coming soon"
        description="The filterable job list backed by GET /jobs (and the discover action) will be built on this page."
      />
    </PageContainer>
  )
}
