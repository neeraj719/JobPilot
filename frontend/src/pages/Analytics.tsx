import { BarChart3 } from 'lucide-react'

import { EmptyState } from '@/components/common/EmptyState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'

/**
 * Placeholder shell. A page agent replaces this file's contents with the real
 * screen — keep the default export and the PageContainer/PageHeader wrapper.
 */
export default function AnalyticsPage() {
  return (
    <PageContainer>
      <PageHeader title="Analytics" description="Funnel, response rates and where your applications actually go." />
      <EmptyState
        icon={BarChart3}
        title="Coming soon"
        description="Recharts visualisations backed by GET /dashboard/charts."
      />
    </PageContainer>
  )
}
