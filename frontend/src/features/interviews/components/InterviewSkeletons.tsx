/**
 * Loading skeletons for Interviews: the sectioned card grid (`InterviewCard`) and the
 * preparation sheet while it is being written (`InterviewPrepPanel`).
 */
import { SkeletonLine, SkeletonRegion } from '@/components/common/skeletons'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

/** One `InterviewCard`: company + role and status, chips, the when/duration lines, buttons. */
function InterviewCardSkeleton({ variant }: { variant: number }) {
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <SkeletonLine size="sm" className={variant % 2 ? 'w-28' : 'w-36'} />
            <SkeletonLine size="sm" className={variant % 2 ? 'w-40' : 'w-32'} />
          </div>
          <Skeleton className="h-[22px] w-20 shrink-0 rounded-full" />
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Skeleton className="h-5 w-16 rounded-md" />
          <Skeleton className="h-5 w-12 rounded-md" />
        </div>
        <div className="space-y-1">
          <div className="flex h-5 items-center gap-2">
            <Skeleton className="size-3.5 shrink-0 rounded-full" />
            <Skeleton className="h-3.5 w-48 max-w-[80%]" />
          </div>
          <div className="flex h-5 items-center gap-2">
            <Skeleton className="size-3.5 shrink-0 rounded-full" />
            <Skeleton className="h-3.5 w-16" />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Skeleton className="h-8 w-20 rounded-md" />
          <Skeleton className="ml-auto h-8 w-28 rounded-md" />
        </div>
      </CardContent>
    </Card>
  )
}

/** The Interviews page body: the "Upcoming" section heading and its card grid. */
export function InterviewsSkeleton({ count = 3 }: { count?: number }) {
  return (
    <SkeletonRegion label="Loading interviews" className="space-y-8">
      <section className="space-y-3" aria-hidden>
        <div className="flex h-5 items-center gap-2">
          <Skeleton className="size-4 rounded" />
          <Skeleton className="h-3.5 w-20" />
          <Skeleton className="h-5 w-7 rounded-full" />
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: count }, (_, index) => (
            <InterviewCardSkeleton key={index} variant={index} />
          ))}
        </div>
      </section>
    </SkeletonRegion>
  )
}

/**
 * The preparation sheet while the model writes it: the meta line + Regenerate button, then
 * the five collapsible sections (the first one open).
 */
export function InterviewPrepSkeleton() {
  return (
    <SkeletonRegion label="Writing your preparation sheet" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2" aria-hidden>
        <SkeletonLine size="xs" className="w-48" />
        <Skeleton className="h-8 w-28 rounded-md" />
      </div>
      <div className="space-y-2" aria-hidden>
        {Array.from({ length: 5 }, (_, index) => (
          <div key={index} className="overflow-hidden rounded-lg border border-border">
            <div className="flex items-center gap-1 bg-muted/40 pr-2">
              <div className="flex min-w-0 flex-1 items-center gap-2 px-3 py-2.5">
                <Skeleton className="size-4 shrink-0 rounded" />
                <div className="min-w-0 flex-1">
                  <SkeletonLine size="sm" className={index % 2 ? 'w-36' : 'w-44'} />
                  <SkeletonLine size="xs" className="w-60 max-w-full" />
                </div>
                <Skeleton className="h-5 w-7 shrink-0 rounded-full" />
              </div>
              <Skeleton className="size-8 shrink-0 rounded-md" />
            </div>
            {index === 0 ? (
              <ol className="divide-y divide-border/60">
                {Array.from({ length: 4 }, (_, row) => (
                  <li key={row} className="flex items-start gap-2 px-3 py-2">
                    <Skeleton className="mt-0.5 h-3.5 w-4 shrink-0" />
                    <SkeletonLine size="sm" className={row % 2 ? 'w-2/3' : 'w-5/6'} boxClassName="flex-1" />
                  </li>
                ))}
              </ol>
            ) : null}
          </div>
        ))}
      </div>
    </SkeletonRegion>
  )
}
