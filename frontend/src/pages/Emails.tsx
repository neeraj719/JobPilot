import { Mail } from 'lucide-react'

import { EmptyState } from '@/components/common/EmptyState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'

/**
 * Placeholder shell. A page agent replaces this file's contents with the real
 * screen — keep the default export and the PageContainer/PageHeader wrapper.
 */
export default function EmailsPage() {
  return (
    <PageContainer>
      <PageHeader title="Emails" description="Replies detected in your inbox, classified and linked to the application they belong to." />
      <EmptyState
        icon={Mail}
        title="Coming soon"
        description="The Gmail inbox view backed by GET /emails, plus connect/sync actions from /integrations/gmail."
      />
    </PageContainer>
  )
}
