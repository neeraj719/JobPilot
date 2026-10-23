import { Construction, type LucideIcon } from 'lucide-react'
import { Link } from 'react-router-dom'

import { EmptyState } from '@/components/common/EmptyState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

interface ComingSoonProps {
  title: string
  description: string
  icon?: LucideIcon
}

/**
 * Placeholder for a Resume destination that is still being built. Each work stream
 * replaces the page that imports this with the real one (`notes/resume-studio-plan.md`).
 */
export function ComingSoonPage({ title, description, icon = Construction }: ComingSoonProps) {
  useDocumentTitle(title)
  return (
    <PageContainer>
      <PageHeader eyebrow="Resume" title={title} description={description} />
      <EmptyState
        icon={icon}
        title={`${title} is on its way`}
        description="This part of the resume workspace is being built. Your existing resumes, versions and recommendations are untouched."
        action={
          <Button variant="outline" asChild>
            <Link to="/resume/my">Go to My Resumes</Link>
          </Button>
        }
      />
    </PageContainer>
  )
}

export default ComingSoonPage
