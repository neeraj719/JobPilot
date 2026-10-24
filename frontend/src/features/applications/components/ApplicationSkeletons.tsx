/**
 * Loading skeletons for one application: the detail page (back row, `ApplicationHeader`,
 * the facts strip, the tab bar, the review card) and the activity timeline (`TimelineTab`).
 */
import { SkeletonLine, SkeletonRegion } from '@/components/common/skeletons'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

/** `TimelineTab` event rows: 28 px icon on a rule, title + actor chip + time, a message line. */
export function TimelineSkeleton({ rows = 4, bare }: { rows?: number; bare?: boolean }) {
  const list = (
    <ol className="relative" aria-hidden>
      <span className="absolute left-3.5 top-2 h-[calc(100%-1rem)] w-px bg-border" />
      {Array.from({ length: rows }, (_, index) => (
        <li key={index} className="relative flex gap-3 pb-5 last:pb-0">
          <Skeleton className="z-10 size-7 shrink-0 rounded-full" />
          <div className="min-w-0 flex-1 space-y-1 pt-0.5">
            <div className="flex h-5 flex-wrap items-center gap-2">
              <Skeleton className="h-3.5 w-32" />
              <Skeleton className="h-[19px] w-12 rounded-md" />
              <Skeleton className="h-3 w-14" />
            </div>
            <SkeletonLine size="sm" className={index % 2 ? 'w-1/2' : 'w-3/4'} />
          </div>
        </li>
      ))}
    </ol>
  )
  return bare ? list : <SkeletonRegion label="Loading activity">{list}</SkeletonRegion>
}

/** `/applications/:id` before the application arrives. */
export function ApplicationDetailSkeleton() {
  return (
    <SkeletonRegion label="Loading application" className="space-y-6">
      <div className="flex items-center justify-between gap-2" aria-hidden>
        <Skeleton className="h-8 w-32 rounded-md" />
      </div>

      {/* ApplicationHeader */}
      <div className="space-y-4" aria-hidden>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex min-w-0 items-start gap-4">
            <Skeleton className="size-14 shrink-0 rounded-lg" />
            <div className="min-w-0 space-y-2">
              <div className="flex h-[22px] items-center gap-2">
                <Skeleton className="h-3.5 w-28" />
                <Skeleton className="h-[22px] w-10 rounded-full" />
              </div>
              <div className="flex h-[1.71875rem] items-center">
                <Skeleton className="h-5 w-72 max-w-full" />
              </div>
              <div className="flex h-5 items-center gap-2">
                <Skeleton className="h-3.5 w-24" />
                <Skeleton className="h-3.5 w-20" />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Skeleton className="h-[22px] w-24 rounded-full" />
                <Skeleton className="h-[22px] w-28 rounded-full" />
              </div>
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <Skeleton className="h-9 w-40 rounded-lg" />
            <Skeleton className="h-9 w-32 rounded-lg" />
            <Skeleton className="h-9 w-16 rounded-lg" />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4 rounded-lg border border-border bg-card p-4 sm:grid-cols-3 lg:grid-cols-5">
          {[16, 20, 24, 8, 32].map((width, index) => (
            <div key={index} className="space-y-0.5">
              <SkeletonLine size="2xs" className="w-20" />
              <div className="flex h-5 items-center">
                <Skeleton className="h-3.5" style={{ width: `${width * 0.25}rem`, maxWidth: '100%' }} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs + the Review card */}
      <div aria-hidden>
        <div className="inline-flex h-9 items-center gap-1 rounded-full bg-muted p-1 dark:bg-surface-2">
          {[14, 24, 22, 18].map((width, index) => (
            <div key={index} className="flex h-7 items-center px-3.5">
              <Skeleton className="h-3.5" style={{ width: `${width * 0.25}rem` }} />
            </div>
          ))}
        </div>
        <div className="mt-4">
          <Card>
            <div className="flex flex-row flex-wrap items-center justify-between gap-2 p-6">
              <SkeletonLine size="title" className="w-48" />
              <div className="flex items-center gap-2">
                <Skeleton className="h-8 w-20 rounded-md" />
                <Skeleton className="h-8 w-24 rounded-md" />
              </div>
            </div>
            <CardContent className="space-y-5">
              <div className="divide-y divide-border">
                {Array.from({ length: 6 }, (_, index) => (
                  <div key={index} className="flex flex-col gap-1 py-2.5 sm:flex-row sm:items-start sm:gap-4">
                    <div className="flex min-w-0 items-center sm:w-2/5">
                      <SkeletonLine size="sm" className={index % 2 ? 'w-24' : 'w-36'} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <SkeletonLine size="sm" className={index % 3 ? 'w-1/2' : 'w-3/4'} />
                      <div className="mt-1 flex items-center gap-1.5">
                        <Skeleton className="h-[18px] w-16 rounded-full" />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </SkeletonRegion>
  )
}
