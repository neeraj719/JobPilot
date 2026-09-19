import { ArrowLeft, Send } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { EmptyState } from '@/components/common/EmptyState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'

/**
 * Placeholder shell for a single application. A page agent replaces this with the
 * review centre (answers, events, emails, interviews, form snapshot).
 */
export default function ApplicationDetailPage() {
  const { id } = useParams<{ id: string }>()

  return (
    <PageContainer>
      <PageHeader
        eyebrow={
          <Link
            to="/applications"
            className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="size-4" aria-hidden />
            All applications
          </Link>
        }
        title="Application"
        description={id ? `Application ${id}` : 'Application detail'}
        actions={
          <Button variant="outline" asChild>
            <Link to="/queue">Open the queue</Link>
          </Button>
        }
      />
      <EmptyState
        icon={Send}
        title="Coming soon"
        description="Answers, the detected form snapshot, the event timeline, linked emails and interviews will render here from GET /applications/{id}."
      />
    </PageContainer>
  )
}
