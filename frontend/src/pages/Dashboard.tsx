import { LayoutDashboard } from 'lucide-react'

import { EmptyState } from '@/components/common/EmptyState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'

/**
 * Placeholder shell. A page agent replaces this file's contents with the real
 * screen — keep the default export and the PageContainer/PageHeader wrapper.
 */
export default function DashboardPage() {
  return (
    <PageContainer>
      <PageHeader title="Dashboard" description="Today at a glance: what was found, what was sent and what needs you." />
      <EmptyState
        icon={LayoutDashboard}
        title="Coming soon"
        description="Stat cards, the attention list and the activity timeline land here once the dashboard feature is wired to GET /dashboard/stats."
      />
    </PageContainer>
  )
}
