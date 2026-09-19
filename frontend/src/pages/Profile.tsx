import { UserRound } from 'lucide-react'

import { EmptyState } from '@/components/common/EmptyState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'

/**
 * Placeholder shell. A page agent replaces this file's contents with the real
 * screen — keep the default export and the PageContainer/PageHeader wrapper.
 */
export default function ProfilePage() {
  return (
    <PageContainer>
      <PageHeader title="Profile" description="The facts used to answer application forms. Nothing here is ever invented by AI." />
      <EmptyState
        icon={UserRound}
        title="Coming soon"
        description="Profile and job-preference forms backed by GET /profile and GET /preferences/job, with a completeness meter."
      />
    </PageContainer>
  )
}
