import { FileText } from 'lucide-react'

import { EmptyState } from '@/components/common/EmptyState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'

/**
 * Placeholder shell. A page agent replaces this file's contents with the real
 * screen — keep the default export and the PageContainer/PageHeader wrapper.
 */
export default function ResumePage() {
  return (
    <PageContainer>
      <PageHeader title="Resume" description="Upload, parse and version the resumes JobPilot attaches to applications." />
      <EmptyState
        icon={FileText}
        title="Coming soon"
        description="Resume upload, the parsed-data editor and version history backed by /resumes."
      />
    </PageContainer>
  )
}
