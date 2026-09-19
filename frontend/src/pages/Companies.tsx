import { Building2 } from 'lucide-react'

import { EmptyState } from '@/components/common/EmptyState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'

/**
 * Placeholder shell. A page agent replaces this file's contents with the real
 * screen — keep the default export and the PageContainer/PageHeader wrapper.
 */
export default function CompaniesPage() {
  return (
    <PageContainer>
      <PageHeader title="Companies" description="Your priority list: which companies to chase first and which to never apply to." />
      <EmptyState
        icon={Building2}
        title="Coming soon"
        description="Company directory and the P1/P2/P3/Avoid preference editor backed by GET /companies."
      />
    </PageContainer>
  )
}
