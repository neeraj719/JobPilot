import { Link } from 'react-router-dom'

import { PageContainer } from '@/components/layout/PageContainer'
import { Button } from '@/components/ui/button'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

export default function NotFoundPage() {
  useDocumentTitle('Page not found')

  return (
    <PageContainer width="narrow" className="flex min-h-[70vh] items-center justify-center">
      <div className="relative isolate w-full overflow-hidden rounded-3xl border border-border bg-card px-6 py-12 text-center shadow-sm dark:shadow-highlight sm:px-12">
        <div aria-hidden className="absolute left-1/2 top-6 -z-10 size-56 -translate-x-1/2 rounded-full bg-glow-brand/25 blur-3xl" />
        <img
          src="/3d/empty-search-240.webp"
          srcSet="/3d/empty-search-240.webp 240w, /3d/empty-search.webp 480w"
          sizes="128px"
          width={128}
          height={128}
          alt=""
          aria-hidden
          className="mx-auto size-32 animate-float object-contain motion-reduce:animate-none"
        />
        <p className="text-gradient-brand mt-4 font-display text-6xl font-bold leading-none tracking-[-0.04em]">404</p>
        <h1 className="mt-3 text-2xl font-heading">Page not found</h1>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
          That route does not exist. It may have been renamed, or the link is out of date.
        </p>
        <Button asChild size="lg" className="mt-6">
          <Link to="/home">Back to all modules</Link>
        </Button>
      </div>
    </PageContainer>
  )
}
