/**
 * Loading skeleton for the company priority board (`PriorityBoard`): the info alert, the
 * add-a-company card, the four priority columns and the save row.
 */
import { SkeletonLine, SkeletonRegion } from '@/components/common/skeletons'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

const COLUMN_ACCENTS = ['border-primary/40', 'border-info/40', 'border-border', 'border-destructive/40']

export function PriorityBoardSkeleton() {
  return (
    <SkeletonRegion label="Loading your company priorities" className="space-y-4">
      <div className="rounded-xl border border-border p-4 pl-11" aria-hidden>
        <SkeletonLine size="sm" className="w-full max-w-2xl" />
      </div>

      <Card aria-hidden>
        <CardContent className="py-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="flex-1 space-y-1.5">
              <SkeletonLine size="sm" className="w-28" />
              <Skeleton className="h-9 w-full rounded-lg" />
            </div>
            <div className="space-y-1.5 sm:w-44">
              <SkeletonLine size="sm" className="w-16" />
              <Skeleton className="h-9 w-full rounded-lg" />
            </div>
            <Skeleton className="h-9 w-20 rounded-lg" />
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4" aria-hidden>
        {COLUMN_ACCENTS.map((accent, column) => (
          <Card key={column} className={cn('border-t-4', accent)}>
            <div className="flex flex-col space-y-1.5 p-6 pb-3">
              <div className="flex h-5 items-center justify-between gap-2">
                <Skeleton className="h-3.5 w-20" />
                <Skeleton className="h-3 w-4" />
              </div>
              <SkeletonLine size="xs" className="w-40 max-w-full" />
            </div>
            <CardContent className="space-y-2">
              {Array.from({ length: column === 3 ? 1 : 2 }, (_, index) => (
                <div key={index} className="space-y-2 rounded-md border border-border bg-muted/20 p-2">
                  <div className="flex items-start justify-between gap-1">
                    <SkeletonLine size="sm" className={index ? 'w-20' : 'w-28'} boxClassName="flex-1" />
                    <Skeleton className="size-8 shrink-0 rounded-md" />
                  </div>
                  <Skeleton className="h-8 w-full rounded-lg" />
                  <Skeleton className="h-8 w-full rounded-lg" />
                </div>
              ))}
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="flex flex-wrap items-center justify-end gap-2" aria-hidden>
        <Skeleton className="h-8 w-24 rounded-md" />
        <Skeleton className="h-9 w-36 rounded-lg" />
      </div>
    </SkeletonRegion>
  )
}
