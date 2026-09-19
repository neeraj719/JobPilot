import { Settings } from 'lucide-react'

import { EmptyState } from '@/components/common/EmptyState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'

/**
 * Placeholder shell. A page agent replaces this file's contents with the real
 * screen — keep the default export and the PageContainer/PageHeader wrapper.
 */
export default function SettingsPage() {
  return (
    <PageContainer>
      <PageHeader title="Settings" description="Account, connected platforms, notifications and data controls." />
      <EmptyState
        icon={Settings}
        title="Coming soon"
        description="Account settings, password change and integration management backed by /auth and /integrations."
      />
    </PageContainer>
  )
}
