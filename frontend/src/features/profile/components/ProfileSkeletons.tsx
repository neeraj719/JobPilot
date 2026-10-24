/**
 * Loading skeletons for the Profile page: the tab bar, a `SectionCard` form (the Personal
 * tab is the default), and the standing-answers rows. Sized from the loaded markup.
 */
import { SkeletonLine, SkeletonRegion } from '@/components/common/skeletons'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

function FieldSkeleton({ label = 'w-20', hint = false }: { label?: string; hint?: boolean }) {
  return (
    <div className="space-y-1.5">
      <SkeletonLine size="sm" className={label} />
      <Skeleton className="h-9 w-full rounded-lg" />
      {hint ? <SkeletonLine size="xs" className="w-36" /> : null}
    </div>
  )
}

/**
 * A `SectionCard` while its data loads: title + description with the header action, the
 * Personal tab's field grids, and the Discard / Save footer.
 */
export function SectionCardSkeleton() {
  return (
    <Card className="overflow-hidden" aria-hidden>
      <div className="flex flex-col gap-3 p-6 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1 space-y-1">
          <SkeletonLine size="title" className="w-24" />
          <SkeletonLine size="sm" className="w-96 max-w-full" />
        </div>
        <Skeleton className="h-8 w-40 shrink-0 rounded-md" />
      </div>
      <CardContent className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <FieldSkeleton label="w-20" />
          <FieldSkeleton label="w-20" />
          <FieldSkeleton label="w-20" />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <FieldSkeleton label="w-12" />
          <FieldSkeleton label="w-12" hint />
        </div>
        <FieldSkeleton label="w-16" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <FieldSkeleton label="w-10" />
          <FieldSkeleton label="w-10" />
          <FieldSkeleton label="w-14" />
        </div>
      </CardContent>
      <div className="flex flex-wrap items-center justify-end gap-2 border-t bg-muted/30 p-6 py-3">
        <Skeleton className="mr-auto h-3 w-14" />
        <Skeleton className="h-8 w-20 rounded-md" />
        <Skeleton className="h-8 w-16 rounded-md" />
      </div>
    </Card>
  )
}

/** The Profile page body below the completeness card: tab bar + the active section card. */
export function ProfileBodySkeleton() {
  return (
    <SkeletonRegion label="Loading your profile">
      <div className="inline-flex h-9 items-center gap-1 rounded-full bg-muted p-1 dark:bg-surface-2" aria-hidden>
        {[16, 24, 20, 28].map((width, index) => (
          <div key={index} className="flex h-7 items-center px-3.5">
            <Skeleton className="h-3.5" style={{ width: `${width * 0.25}rem` }} />
          </div>
        ))}
      </div>
      <div className="mt-4">
        <SectionCardSkeleton />
      </div>
    </SkeletonRegion>
  )
}

/** `StandingAnswersCard` rows: question, scope badge, icon actions, the answer box. */
export function StandingAnswersSkeleton({ rows = 2 }: { rows?: number }) {
  return (
    <SkeletonRegion label="Loading your standing answers">
      <ul className="divide-y" aria-hidden>
        {Array.from({ length: rows }, (_, index) => (
          <li key={index} className="space-y-2 py-4 first:pt-0 last:pb-0">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex h-[1.203rem] items-center">
                  <Skeleton className="h-3.5 w-3/4" />
                </div>
                <Skeleton className="h-[22px] w-24 rounded-full" />
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Skeleton className="size-8 rounded-md" />
                <Skeleton className="size-8 rounded-md" />
              </div>
            </div>
            <div className="rounded-md bg-muted/40 px-3 py-2">
              <SkeletonLine size="sm" className={index % 2 ? 'w-1/3' : 'w-1/2'} />
            </div>
          </li>
        ))}
      </ul>
    </SkeletonRegion>
  )
}
