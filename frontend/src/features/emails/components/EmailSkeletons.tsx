/**
 * Loading skeletons for the Emails page: the inbox column (`EmailList`), the reading pane
 * (`EmailDetail`) and the application picker rows (`ApplicationPicker`).
 */
import { SkeletonLine, SkeletonRegion } from '@/components/common/skeletons'
import { Skeleton } from '@/components/ui/skeleton'

/** Inbox rows: dot + sender + time, subject, two snippet lines, the badge row. */
export function EmailListSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <SkeletonRegion label="Loading emails">
      <ul className="divide-y divide-border" aria-hidden>
        {Array.from({ length: rows }, (_, index) => (
          <li key={index}>
            <div className="w-full space-y-1 px-3 py-2.5">
              <div className="flex h-5 items-center gap-2">
                <Skeleton className="size-1.5 shrink-0 rounded-full" />
                <Skeleton className={index % 2 ? 'h-3.5 w-24' : 'h-3.5 w-32'} />
                <Skeleton className="ml-auto h-2.5 w-10 shrink-0" />
              </div>
              <SkeletonLine size="sm" className={index % 3 ? 'w-3/5' : 'w-4/5'} boxClassName="pl-3.5" />
              <div className="pl-3.5">
                <SkeletonLine size="xs" className="w-full" />
                <SkeletonLine size="xs" className="w-2/3" />
              </div>
              <div className="flex items-center gap-1 pl-3.5 pt-0.5">
                <Skeleton className="h-[18px] w-20 rounded-full" />
                <Skeleton className="h-[18px] w-14 rounded-full" />
              </div>
            </div>
          </li>
        ))}
      </ul>
    </SkeletonRegion>
  )
}

/** The reading pane: subject + action, From / Date, the classification box, the body. */
export function EmailDetailSkeleton() {
  return (
    <SkeletonRegion label="Loading email" className="flex h-full min-h-0 flex-col">
      <div className="space-y-3 border-b border-border p-5" aria-hidden>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <SkeletonLine size="lg" className="w-3/4" boxClassName="min-w-0 flex-1" />
          <Skeleton className="h-8 w-28 shrink-0 rounded-md" />
        </div>
        <div className="space-y-1">
          {['w-56', 'w-48'].map((width, index) => (
            <div key={index} className="flex h-5 items-center gap-2">
              <div className="w-16 shrink-0">
                <Skeleton className="h-3.5 w-10" />
              </div>
              <Skeleton className={`h-3.5 ${width} max-w-[70%]`} />
            </div>
          ))}
        </div>
      </div>
      <div className="space-y-4 border-b border-border p-5" aria-hidden>
        <div className="space-y-2 rounded-lg border border-border bg-muted/30 p-3">
          <div className="flex h-[22px] items-center gap-2">
            <Skeleton className="h-[22px] w-28 rounded-full" />
            <Skeleton className="h-3 w-24" />
          </div>
          <SkeletonLine size="xs" className="w-3/4" />
          <div className="flex flex-wrap items-end gap-2 pt-1">
            <div className="min-w-[12rem] flex-1 space-y-1">
              <SkeletonLine size="xs" className="w-16" />
              <Skeleton className="h-8 w-full rounded-lg" />
            </div>
          </div>
        </div>
        <div className="flex items-center justify-between gap-3 rounded-lg border border-dashed border-border p-3">
          <SkeletonLine size="sm" className="w-56 max-w-full" />
          <Skeleton className="h-8 w-24 shrink-0 rounded-md" />
        </div>
      </div>
      <div className="space-y-1 p-5" aria-hidden>
        {['w-full', 'w-11/12', 'w-full', 'w-4/5', 'w-2/3', 'w-full', 'w-1/2'].map((width, index) => (
          <div key={index} className="flex h-[1.421875rem] items-center">
            <Skeleton className={`h-3.5 ${width}`} />
          </div>
        ))}
      </div>
    </SkeletonRegion>
  )
}

/** `ApplicationPicker` option rows: icon tile, company over role, status badge. */
export function ApplicationOptionsSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <SkeletonRegion label="Loading your applications">
      <ul aria-hidden>
        {Array.from({ length: rows }, (_, index) => (
          <li key={index} className="flex w-full items-center gap-3 border-b border-border/60 px-3 py-2 last:border-b-0">
            <Skeleton className="size-7 shrink-0 rounded-md" />
            <div className="min-w-0 flex-1">
              <SkeletonLine size="sm" className={index % 2 ? 'w-28' : 'w-36'} />
              <SkeletonLine size="xs" className={index % 2 ? 'w-40' : 'w-32'} />
            </div>
            <Skeleton className="h-[22px] w-20 shrink-0 rounded-full" />
          </li>
        ))}
      </ul>
    </SkeletonRegion>
  )
}
