import { Compass } from 'lucide-react'
import { Link } from 'react-router-dom'

import { EmptyState } from '@/components/common/EmptyState'
import { PageContainer } from '@/components/layout/PageContainer'
import { Button } from '@/components/ui/button'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

export default function NotFoundPage() {
  useDocumentTitle('Page not found')

  return (
    <PageContainer width="narrow" className="flex min-h-[60vh] items-center justify-center">
      <EmptyState
        icon={Compass}
        title="404 — page not found"
        description="That route does not exist. It may have been renamed, or the link is out of date."
        action={
          <Button asChild>
            <Link to="/dashboard">Back to dashboard</Link>
          </Button>
        }
        className="w-full"
      />
    </PageContainer>
  )
}
