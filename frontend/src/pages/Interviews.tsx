import { CalendarClock } from 'lucide-react'

import { EmptyState } from '@/components/common/EmptyState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'

/**
 * Placeholder shell. A page agent replaces this file's contents with the real
 * screen — keep the default export and the PageContainer/PageHeader wrapper.
 */
export default function InterviewsPage() {
  return (
    <PageContainer>
      <PageHeader title="Interviews" description="Scheduled rounds and the AI-generated preparation material for each one." />
      <EmptyState
        icon={CalendarClock}
        title="Coming soon"
        description="Upcoming interviews and prep sheets backed by /interviews."
      />
    </PageContainer>
  )
}
