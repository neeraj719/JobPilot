/**
 * First-paint placeholders for the Dashboard and Analytics pages. Every block mirrors the
 * loaded component — `StatCard` tiles, `AttentionPanel`, `TodayCard`, `AutomationCard`,
 * `ChartCard` (its own loading branch: plot block + caption bar), `ActivityTimeline` — with
 * the same grids, so nothing jumps when the data lands.
 */
import { SkeletonLine, SkeletonRegion } from '@/components/common/skeletons'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

/** A `StatCard` without an icon: title, 30 px figure, caption (p-5, space-y-2). */
function StatTileSkeleton() {
  return (
    <Card>
      <CardContent className="space-y-2 p-5">
        <SkeletonLine size="sm" className="w-24" />
        <Skeleton className="h-[1.875rem] w-14 rounded-lg" />
        <SkeletonLine size="xs" className="w-28 max-w-full" />
      </CardContent>
    </Card>
  )
}

/** `CardHeader` with `text-base` title and a one-line description. */
function CardHeaderSkeleton({ title = 'w-40', description = 'w-56', badge = false }: { title?: string; description?: string; badge?: boolean }) {
  return (
    <div className="flex flex-row items-start justify-between gap-3 p-6">
      <div className="min-w-0 flex-1 space-y-1">
        <SkeletonLine size="title" className={title} />
        <SkeletonLine size="sm" className={cn(description, 'max-w-full')} />
      </div>
      {badge ? <Skeleton className="h-[22px] w-16 shrink-0 rounded-full" /> : null}
    </div>
  )
}

/** A `ChartCard` in its loading state (plot block `height - 24` + caption bar). */
export function ChartCardSkeleton({ height = 280, className, title = 'w-44' }: { height?: number; className?: string; title?: string }) {
  return (
    <Card className={cn('flex min-w-0 flex-col', className)}>
      <CardHeaderSkeleton title={title} description="w-64" />
      <CardContent className="flex-1">
        <div className="space-y-3" style={{ minHeight: height }}>
          <Skeleton className="w-full rounded-lg" style={{ height: height - 24 }} />
          <Skeleton className="h-3 w-1/3" />
        </div>
      </CardContent>
    </Card>
  )
}

/** `ActivityTimeline` rows: 32 px tone circle on a rule, title + time, a message line. */
export function ActivitySkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <SkeletonRegion label="Loading recent activity">
      <ol className="relative space-y-1" aria-hidden>
        {Array.from({ length: rows }, (_, index) => (
          <li key={index} className="-mx-2 flex gap-3 px-2 py-1">
            <div className="relative flex flex-col items-center">
              <Skeleton className="size-8 shrink-0 rounded-full" />
              {index < rows - 1 ? <span className="mt-1 w-px flex-1 bg-border" /> : null}
            </div>
            <div className="min-w-0 flex-1 pb-3">
              <div className="flex items-center justify-between gap-3">
                <SkeletonLine size="sm" className={index % 2 ? 'w-40' : 'w-56'} boxClassName="flex-1" />
                <Skeleton className="h-3 w-14 shrink-0" />
              </div>
              <SkeletonLine size="sm" className={index % 2 ? 'w-1/2' : 'w-2/3'} />
            </div>
          </li>
        ))}
      </ol>
    </SkeletonRegion>
  )
}

/** The Dashboard below its header: KPIs, attention/today/automation, trends, activity. */
export function DashboardSkeleton() {
  return (
    <SkeletonRegion label="Loading the dashboard" className="space-y-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7" aria-hidden>
        {Array.from({ length: 7 }, (_, index) => (
          <StatTileSkeleton key={index} />
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-3" aria-hidden>
        {/* AttentionPanel */}
        <Card className="flex min-w-0 flex-col">
          <CardHeaderSkeleton title="w-44" description="w-60" />
          <CardContent className="flex-1">
            <ul className="space-y-2">
              {Array.from({ length: 3 }, (_, index) => (
                <li key={index} className="flex items-center gap-3 rounded-lg border border-border bg-card/60 p-3">
                  <Skeleton className="size-9 shrink-0 rounded-lg" />
                  <SkeletonLine size="sm" className={index % 2 ? 'w-2/5' : 'w-3/5'} boxClassName="min-w-0 flex-1" />
                  <Skeleton className="h-8 w-20 shrink-0 rounded-md" />
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
        {/* TodayCard */}
        <Card className="flex min-w-0 flex-col">
          <CardHeaderSkeleton title="w-16" description="w-52" />
          <CardContent className="flex-1">
            <div className="divide-y divide-border">
              {[24, 20, 20, 22, 16, 20].map((width, index) => (
                <div key={index} className="flex items-center justify-between py-2.5">
                  <div className="flex h-5 items-center gap-2">
                    <Skeleton className="size-4 shrink-0 rounded" />
                    <Skeleton className="h-3.5" style={{ width: `${width * 0.25}rem` }} />
                  </div>
                  <Skeleton className="h-3.5 w-6" />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
        {/* AutomationCard */}
        <Card className="flex min-w-0 flex-col">
          <CardHeaderSkeleton title="w-28" description="w-56" badge />
          <CardContent className="flex-1 space-y-4">
            <div className="rounded-lg border border-border bg-muted/30 p-3">
              <div className="flex items-center justify-between gap-2">
                <SkeletonLine size="xs" className="w-32" />
                <Skeleton className="h-5 w-20 rounded-full" />
              </div>
              <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
                {Array.from({ length: 4 }, (_, index) => (
                  <div key={index}>
                    <SkeletonLine size="2xs" className="w-12" />
                    <SkeletonLine size="base" className="w-8" />
                  </div>
                ))}
              </div>
            </div>
            <SkeletonLine size="xs" className="w-4/5" />
          </CardContent>
          <div className="flex flex-wrap gap-2 p-6 pt-0">
            <Skeleton className="h-8 w-28 rounded-md" />
            <Skeleton className="h-8 w-24 rounded-md" />
          </div>
        </Card>
      </div>

      {/* The "Trends" filter row. */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-6" aria-hidden>
        <div>
          <SkeletonLine size="lg" className="w-20" />
          <SkeletonLine size="sm" className="w-56" />
        </div>
        <div className="flex items-center gap-2">
          <Skeleton className="h-[30px] w-48 rounded-md" />
          <Skeleton className="h-8 w-28 rounded-md" />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3" aria-hidden>
        <ChartCardSkeleton className="lg:col-span-2" height={260} title="w-72" />
        <ChartCardSkeleton height={260} title="w-20" />
      </div>
      <div className="grid gap-4 lg:grid-cols-3" aria-hidden>
        <ChartCardSkeleton height={240} title="w-24" />
        <ChartCardSkeleton title="w-32" />
        <ChartCardSkeleton title="w-36" />
      </div>

      <Card aria-hidden>
        <div className="flex flex-col gap-2 p-6 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex h-5 items-center gap-2">
              <Skeleton className="size-4 rounded" />
              <Skeleton className="h-4 w-32" />
            </div>
            <SkeletonLine size="sm" className="w-96 max-w-full" />
          </div>
          <Skeleton className="h-8 w-32 shrink-0 rounded-md" />
        </div>
        <CardContent>
          <ActivitySkeleton />
        </CardContent>
      </Card>
    </SkeletonRegion>
  )
}

/** The Analytics page below its header: four KPIs, the 320 px trend, then the chart grids. */
export function AnalyticsSkeleton() {
  return (
    <SkeletonRegion label="Loading analytics" className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4" aria-hidden>
        {Array.from({ length: 4 }, (_, index) => (
          <StatTileSkeleton key={index} />
        ))}
      </div>
      <div aria-hidden>
        <ChartCardSkeleton height={320} title="w-72" />
      </div>
      <div className="grid items-start gap-4 lg:grid-cols-3" aria-hidden>
        <ChartCardSkeleton title="w-20" />
        <ChartCardSkeleton title="w-24" />
        <ChartCardSkeleton title="w-32" />
      </div>
      <div className="grid items-start gap-4 lg:grid-cols-2" aria-hidden>
        <ChartCardSkeleton title="w-52" />
        <ChartCardSkeleton title="w-48" />
      </div>
      <div className="grid items-start gap-4 xl:grid-cols-2" aria-hidden>
        <ChartCardSkeleton height={200} title="w-48" />
        <ChartCardSkeleton height={200} title="w-56" />
      </div>
    </SkeletonRegion>
  )
}
