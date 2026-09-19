import { Bot } from 'lucide-react'

import { EmptyState } from '@/components/common/EmptyState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'

/**
 * Placeholder shell. A page agent replaces this file's contents with the real
 * screen — keep the default export and the PageContainer/PageHeader wrapper.
 */
export default function AutomationPage() {
  return (
    <PageContainer>
      <PageHeader title="Automation" description="Schedule the daily run and set the safety rails it must respect." />
      <EmptyState
        icon={Bot}
        title="Coming soon"
        description="Automation config, run history and live run progress backed by /automation/config, /automation/runs and /automation/status."
      />
    </PageContainer>
  )
}
