/**
 * Loading skeletons for the Jobs page: the job card grid (`JobCardItem`) and the job detail
 * sheet (`JobDetailSheet`). Same frames, paddings and line heights as the loaded markup.
 */
import { SkeletonLine, SkeletonRegion } from '@/components/common/skeletons'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

/** `MatchScore` with its bar: a 22 px pill over a 4 px bar, right-aligned. */
function MatchScoreSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn('flex shrink-0 flex-col items-end gap-1', className)}>
      <Skeleton className="h-[22px] w-12 rounded-full" />
      <Skeleton className="h-1 w-16 rounded-full" />
    </div>
  )
}

/** One `JobCardItem`. */
export function JobCardSkeleton({ variant = 0 }: { variant?: number }) {
  return (
    <Card className="flex h-full flex-col">
      <CardContent className="flex flex-1 flex-col gap-3 p-4">
        <div className="flex items-center gap-3">
          <Skeleton className="size-8 shrink-0 rounded-lg" />
          <div className="flex min-w-0 flex-1 items-center gap-1.5">
            <Skeleton className={cn('h-3.5', variant % 2 ? 'w-20' : 'w-28')} />
          </div>
          <MatchScoreSkeleton className="w-14" />
        </div>
        <div>
          <div className="flex h-[1.375rem] items-center">
            <Skeleton className="h-4 w-11/12" />
          </div>
          <div className="flex h-[1.375rem] items-center">
            <Skeleton className={cn('h-4', variant % 3 ? 'w-1/2' : 'w-2/3')} />
          </div>
        </div>
        <div className="grid gap-1">
          <SkeletonLine size="xs" className="w-2/5" />
          <SkeletonLine size="xs" className="w-3/5" />
        </div>
        <div className="flex flex-wrap items-center gap-1">
          <Skeleton className="h-3 w-12" />
          <Skeleton className="h-5 w-14 rounded-md" />
          <Skeleton className="h-5 w-16 rounded-md" />
        </div>
        <div className="mt-auto flex flex-wrap items-center gap-2 pt-1">
          <Skeleton className="h-[22px] w-20 rounded-full" />
          <Skeleton className="ml-auto h-3 w-14" />
        </div>
        <div className="flex items-center gap-2 border-t border-border pt-3">
          <Skeleton className="h-8 flex-1 rounded-md" />
          <Skeleton className="h-8 flex-1 rounded-md" />
          <Skeleton className="size-8 shrink-0 rounded-md" />
        </div>
      </CardContent>
    </Card>
  )
}

/** The Jobs result grid (1 / 2 / 3 columns, gap-4). */
export function JobGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <SkeletonRegion label="Loading jobs" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} aria-hidden>
          <JobCardSkeleton variant={index} />
        </div>
      ))}
    </SkeletonRegion>
  )
}

/** The job detail sheet body while the job loads: header, the facts grid, sources, match. */
export function JobDetailSkeleton() {
  return (
    <SkeletonRegion label="Loading job details" className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-col space-y-2 border-b border-border p-6 pb-4 pr-12" aria-hidden>
        <div className="flex items-start gap-3">
          <Skeleton className="size-14 shrink-0 rounded-lg" />
          <div className="min-w-0 flex-1 space-y-1">
            <SkeletonLine size="lg" className="w-3/4" />
            <div className="flex h-[22px] items-center gap-1.5">
              <Skeleton className="h-3.5 w-28" />
              <Skeleton className="h-[22px] w-10 rounded-full" />
            </div>
          </div>
          <MatchScoreSkeleton className="w-16" />
        </div>
      </div>
      <div className="space-y-5 p-6" aria-hidden>
        <div className="grid grid-cols-2 gap-4">
          {[16, 12, 20, 14, 10, 18].map((width, index) => (
            <div key={index} className="space-y-0.5">
              <SkeletonLine size="2xs" className="w-16" />
              <Skeleton className="h-3.5" style={{ width: `${width * 0.5}rem`, maxWidth: '100%' }} />
            </div>
          ))}
        </div>
        <div className="h-px w-full bg-border" />
        <section className="space-y-2">
          <SkeletonLine size="sm" className="w-36" />
          <div className="space-y-1.5">
            {[0, 1].map((index) => (
              <div key={index} className="flex h-5 items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Skeleton className="h-3.5 w-20" />
                  <Skeleton className="h-3 w-24" />
                </div>
                <Skeleton className="h-3 w-10" />
              </div>
            ))}
          </div>
        </section>
        <div className="h-px w-full bg-border" />
        <section className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <SkeletonLine size="sm" className="w-32" />
            <Skeleton className="h-8 w-28 rounded-md" />
          </div>
          <div className="space-y-3 rounded-lg border border-border bg-muted/30 p-3">
            <SkeletonLine size="sm" className="w-full" />
            <SkeletonLine size="sm" className="w-4/5" />
            <div className="grid gap-3 sm:grid-cols-2">
              <Skeleton className="h-10 w-full rounded-md" />
              <Skeleton className="h-10 w-full rounded-md" />
            </div>
          </div>
        </section>
      </div>
    </SkeletonRegion>
  )
}
