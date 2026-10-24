/**
 * Loading skeletons for the ATS screens: the optimizer's two input cards, the analysis results
 * (score ring + category bars + keywords + recommendations), the source-vs-tailored compare
 * view, and the Job-Specific Resumes board / table / detail. Each mirrors the loaded markup —
 * same Card frames, paddings, grids and line heights — so nothing moves when data arrives.
 */
import { SkeletonLine, SkeletonRegion } from '@/components/common/skeletons'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

/** `CardHeader` with `pb-*`: title (+ description), optional sm button on the right. */
function HeaderSkeleton({
  title = 'w-36',
  description = 'w-72',
  action,
  pb = 'pb-3',
}: {
  title?: string
  description?: string | null
  action?: string
  pb?: string
}) {
  return (
    <div className={cn('flex flex-row flex-wrap items-start justify-between gap-2 p-6', pb)}>
      <div className="min-w-0 flex-1 space-y-1">
        <SkeletonLine size="title" className={title} />
        {description ? <SkeletonLine size="sm" className={cn(description, 'max-w-full')} /> : null}
      </div>
      {action ? <Skeleton className={cn('h-8 shrink-0 rounded-md', action)} /> : null}
    </div>
  )
}

/** `ScoreRing`: the ring, its caption, room for the delta pill. */
function ScoreRingSkeleton({ size = 132 }: { size?: number }) {
  return (
    <div className="flex flex-col items-center gap-1.5">
      <Skeleton className="rounded-full" style={{ width: size, height: size }} />
      <SkeletonLine size="xs" className="w-28" />
    </div>
  )
}

/* ------------------------------------------------------------------ optimizer */

/** The "1 Resume · 2 Job description · 3 Results" step row under the page title. */
export function AtsStepsSkeleton() {
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2" aria-hidden>
      {[16, 28, 16].map((width, index) => (
        <div key={index} className="flex items-center gap-2">
          <Skeleton className="size-7 rounded-full" />
          <Skeleton className="h-3.5" style={{ width: `${width * 0.25}rem` }} />
        </div>
      ))}
    </div>
  )
}

/** `/resume/ats` while the resume list loads: the resume card and the job-description card. */
export function AtsOptimizerSkeleton() {
  return (
    <SkeletonRegion label="Loading the ATS Optimizer">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]" aria-hidden>
        <Card className="h-fit">
          <HeaderSkeleton title="w-24" description="w-52" />
          <CardContent className="space-y-4">
            <Skeleton className="h-9 w-full rounded-lg" />
            <div className="flex flex-wrap gap-2">
              <Skeleton className="h-[22px] w-16 rounded-full" />
              <Skeleton className="h-[22px] w-20 rounded-full" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <HeaderSkeleton title="w-40" description="w-96" />
          <CardContent className="space-y-4">
            <Skeleton className="h-9 w-80 max-w-full rounded-full" />
            <Skeleton className="h-48 w-full rounded-lg" />
            <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
              <Skeleton className="h-9 w-28 rounded-lg" />
              <Skeleton className="h-3 w-52" />
            </div>
          </CardContent>
        </Card>
      </div>
    </SkeletonRegion>
  )
}

/* ------------------------------------------------------------------ analysis results */

/** `AnalysisResults`: score card, category bars | keywords, recommendations. */
export function AnalysisResultsSkeleton() {
  return (
    <SkeletonRegion label="Loading the analysis" className="space-y-6">
      <Card aria-hidden>
        <CardContent className="grid gap-6 p-6 md:grid-cols-[auto_1fr]">
          <ScoreRingSkeleton />
          <div className="min-w-0 space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0 flex-1 space-y-1">
                <SkeletonLine size="lg" className="w-72 max-w-full" />
                <SkeletonLine size="sm" className="w-64 max-w-full" />
              </div>
              <Skeleton className="h-8 w-32 rounded-md" />
            </div>
            <div className="space-y-0">
              <SkeletonLine size="xs" className="w-full" />
              <SkeletonLine size="xs" className="w-2/3" />
            </div>
            <div className="flex flex-wrap gap-2">
              <Skeleton className="h-8 w-52 rounded-md" />
              <Skeleton className="h-8 w-36 rounded-md" />
              <Skeleton className="h-8 w-24 rounded-md" />
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]" aria-hidden>
        <Card>
          <HeaderSkeleton title="w-36" description="w-72" pb="pb-2" />
          <CardContent>
            <ul className="divide-y divide-border">
              {[72, 55, 88, 40, 64, 80].map((value, index) => (
                <li key={index} className="py-2">
                  <div className="flex h-5 items-center gap-3">
                    <div className="w-40 shrink-0 sm:w-48">
                      <Skeleton className="h-3.5 w-3/4" />
                    </div>
                    <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-muted">
                      <Skeleton className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${value}%` }} />
                    </div>
                    <div className="flex w-10 shrink-0 justify-end">
                      <Skeleton className="h-3.5 w-6" />
                    </div>
                    <div className="hidden w-10 shrink-0 justify-end sm:flex">
                      <Skeleton className="h-3 w-7" />
                    </div>
                    <Skeleton className="size-4 shrink-0 rounded" />
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
        <Card>
          <HeaderSkeleton title="w-24" description="w-80" pb="pb-2" />
          <CardContent>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <SkeletonLine size="xs" className="w-24" />
                <div className="flex flex-wrap gap-1.5">
                  {[16, 20, 14, 24, 18, 12, 22].map((width, index) => (
                    <Skeleton key={index} className="h-[22px] rounded-full" style={{ width: `${width * 0.25}rem` }} />
                  ))}
                </div>
              </div>
              <div className="space-y-2">
                <SkeletonLine size="xs" className="w-24" />
                <div className="space-y-1.5">
                  {[0, 1, 2].map((index) => (
                    <div key={index} className="flex h-5 items-center gap-2">
                      <Skeleton className="h-[22px] w-20 rounded-full" />
                      <Skeleton className="h-3 w-40 max-w-[60%]" />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card aria-hidden>
        <HeaderSkeleton title="w-40" description="w-[36rem]" pb="pb-2" />
        <CardContent>
          <div className="space-y-3">
            {[0, 1, 2].map((index) => (
              <div key={index} className="space-y-2 rounded-lg border border-border p-3">
                <div className="flex items-center gap-2">
                  <Skeleton className="h-[22px] w-20 rounded-full" />
                  <Skeleton className="h-3.5 w-48 max-w-[50%]" />
                </div>
                <SkeletonLine size="sm" className={index === 1 ? 'w-1/2' : 'w-4/5'} />
                <div className="flex justify-end gap-2">
                  <Skeleton className="h-8 w-16 rounded-md" />
                  <Skeleton className="h-8 w-20 rounded-md" />
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </SkeletonRegion>
  )
}

/* ------------------------------------------------------------------ compare */

/** `CompareView`: summary badges, the two side headers, then diff sections. */
export function CompareViewSkeleton() {
  return (
    <SkeletonRegion label="Loading the comparison" className="space-y-5">
      <div className="flex flex-wrap items-center gap-2" aria-hidden>
        {[16, 18, 18, 24].map((width, index) => (
          <Skeleton key={index} className="h-[22px] rounded-full" style={{ width: `${width * 0.25}rem` }} />
        ))}
      </div>
      <div className="grid gap-4 md:grid-cols-2" aria-hidden>
        {[0, 1].map((index) => (
          <div key={index} className="flex items-center justify-between gap-2">
            <div className="min-w-0 flex-1">
              <SkeletonLine size="2xs" className="w-16" />
              <SkeletonLine size="sm" className="w-1/2" />
            </div>
            <Skeleton className="h-[1.125rem] w-8" />
          </div>
        ))}
      </div>
      {['w-16', 'w-12'].map((heading, index) => (
        <section key={index} className="space-y-2" aria-hidden>
          <SkeletonLine size="xs" className={heading} />
          <SkeletonLine size="sm" className="w-full" />
          <SkeletonLine size="sm" className="w-3/5" />
        </section>
      ))}
      <section className="space-y-3" aria-hidden>
        <SkeletonLine size="xs" className="w-20" />
        {[0, 1].map((index) => (
          <div key={index} className="space-y-1.5 rounded-md border border-border p-3">
            <SkeletonLine size="sm" className="w-1/3" />
            <SkeletonLine size="sm" className="w-11/12" />
          </div>
        ))}
      </section>
    </SkeletonRegion>
  )
}

/* ------------------------------------------------------------------ job targets */

/** One `TargetCard` (`rounded-lg border bg-card p-3`). */
function TargetCardSkeleton({ wide = false }: { wide?: boolean }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3 shadow-xs">
      <SkeletonLine size="sm" className={wide ? 'w-4/5' : 'w-3/5'} />
      <SkeletonLine size="xs" className="w-1/2" />
      <div className="mt-2.5 flex items-center gap-1.5">
        <Skeleton className="h-4 w-10" />
        <Skeleton className="h-5 w-20 rounded-full" />
      </div>
    </div>
  )
}

/** The eight-column status board (scrolls sideways like the real one). */
export function TargetBoardSkeleton() {
  const perColumn = [2, 1, 2, 1, 0, 1, 0, 0]
  return (
    <SkeletonRegion label="Loading job targets" className="-mx-4 overflow-x-auto px-4 pb-2 sm:mx-0 sm:px-0">
      <div className="grid grid-cols-[repeat(8,minmax(11rem,1fr))] gap-3" aria-hidden>
        {perColumn.map((cards, column) => (
          <section key={column} className="flex min-h-40 flex-col gap-2 rounded-xl bg-surface-2 p-2">
            <div className="flex min-h-8 items-center justify-between gap-2 px-1.5">
              <Skeleton className="h-2.5 w-16" />
              <Skeleton className="h-4 w-5 rounded-full" />
            </div>
            {Array.from({ length: cards }, (_, index) => (
              <TargetCardSkeleton key={index} wide={(column + index) % 2 === 0} />
            ))}
          </section>
        ))}
      </div>
    </SkeletonRegion>
  )
}

/** `TargetTable`: the real column set (with its responsive hiding) inside a Card. */
export function TargetTableSkeleton({ rows = 6 }: { rows?: number }) {
  const head = 'h-9 px-3 text-left align-middle first:pl-4 last:pr-4'
  const cell = 'px-3 py-2.5 align-middle first:pl-4 last:pr-4'
  return (
    <SkeletonRegion label="Loading job targets">
      <Card aria-hidden>
        <CardContent className="p-0">
          <div className="relative w-full overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-surface-2">
                <tr className="border-b border-border">
                  <th className={head}><Skeleton className="h-2.5 w-10" /></th>
                  <th className={head}><Skeleton className="h-2.5 w-12" /></th>
                  <th className={head}><Skeleton className="ml-auto h-2.5 w-14" /></th>
                  <th className={cn(head, 'hidden md:table-cell')}><Skeleton className="h-2.5 w-14" /></th>
                  <th className={cn(head, 'hidden lg:table-cell')}><Skeleton className="h-2.5 w-14" /></th>
                  <th className={cn(head, 'hidden lg:table-cell')}><Skeleton className="h-2.5 w-14" /></th>
                </tr>
              </thead>
              <tbody>
                {Array.from({ length: rows }, (_, index) => (
                  <tr key={index} className="border-b border-border last:border-0">
                    <td className={cell}>
                      <SkeletonLine size="sm" className={index % 2 ? 'w-36' : 'w-48'} />
                      <SkeletonLine size="xs" className="w-24" />
                    </td>
                    <td className={cell}><Skeleton className="h-[22px] w-24 rounded-full" /></td>
                    <td className={cell}><Skeleton className="ml-auto h-3.5 w-10" /></td>
                    <td className={cn(cell, 'hidden md:table-cell')}><Skeleton className="h-3.5 w-36" /></td>
                    <td className={cn(cell, 'hidden lg:table-cell')}><Skeleton className="h-3.5 w-20" /></td>
                    <td className={cn(cell, 'hidden lg:table-cell')}><Skeleton className="h-3.5 w-16" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </SkeletonRegion>
  )
}

/**
 * `/resume/targets/:id` while the target loads: back link, title, company + badges, the
 * status select and icon actions; then the estimate / tailored / JD cards and the details card.
 */
export function JobTargetDetailSkeleton() {
  return (
    <SkeletonRegion label="Loading job target" className="space-y-6">
      {/* Header band: back link 20, title 32/36, meta row 24, then the 50 px stepper. */}
      <div className="space-y-5 rounded-3xl border border-border p-5 sm:p-6" aria-hidden>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 flex-1 space-y-2">
            <div className="flex h-5 items-center">
              <Skeleton className="h-3.5 w-40" />
            </div>
            <div className="flex h-8 items-center sm:h-9">
              <Skeleton className="h-7 w-72 max-w-[80%] rounded-lg" />
            </div>
            <div className="flex h-6 flex-wrap items-center gap-2">
              <Skeleton className="h-3.5 w-28" />
              <Skeleton className="h-[22px] w-24 rounded-full" />
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <Skeleton className="h-9 w-44 rounded-lg" />
            <Skeleton className="size-9 rounded-lg" />
            <Skeleton className="size-9 rounded-lg" />
          </div>
        </div>
        <div className="-mx-1 overflow-hidden px-1 pb-1">
          <div className="grid min-w-[34rem] grid-cols-6">
            {Array.from({ length: 6 }, (_, index) => (
              <div key={index} className="flex flex-col items-center gap-1.5">
                <Skeleton className="size-7 rounded-full" />
                <Skeleton className="h-3 w-14" />
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,20rem)]" aria-hidden>
        <div className="min-w-0 space-y-6">
          <Card>
            <HeaderSkeleton title="w-28" description="w-80" action="w-44" />
            <CardContent>
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                <ScoreRingSkeleton size={104} />
                <div className="min-w-0 flex-1 space-y-2">
                  <SkeletonLine size="xs" className="w-36" />
                  <div className="flex flex-wrap gap-1.5">
                    {[16, 20, 14, 18].map((width, index) => (
                      <Skeleton key={index} className="h-[22px] rounded-full" style={{ width: `${width * 0.25}rem` }} />
                    ))}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <HeaderSkeleton title="w-32" description="w-96" />
            <CardContent className="space-y-3">
              <Skeleton className="h-9 w-full rounded-lg" />
              <Skeleton className="h-9 w-40 rounded-lg" />
            </CardContent>
          </Card>
          <Card>
            <HeaderSkeleton title="w-32" description="w-72" action="w-28" />
            <CardContent className="space-y-2">
              <SkeletonLine size="sm" className="w-full" />
              <SkeletonLine size="sm" className="w-full" />
              <SkeletonLine size="sm" className="w-4/5" />
              <SkeletonLine size="sm" className="w-3/5" />
            </CardContent>
          </Card>
        </div>
        <div className="space-y-6">
          <Card>
            <HeaderSkeleton title="w-32" description={null} />
            <CardContent className="space-y-3">
              <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
                {[0, 1, 2].map((index) => (
                  <div key={index} className="contents">
                    <SkeletonLine size="sm" className="w-16" />
                    <SkeletonLine size="sm" className="w-24" />
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-2 gap-2">
                {[0, 1].map((index) => (
                  <div key={index} className="space-y-1">
                    <SkeletonLine size="xs" className="w-16" />
                    <Skeleton className="h-9 w-full rounded-lg" />
                  </div>
                ))}
              </div>
              <div className="space-y-1">
                <SkeletonLine size="xs" className="w-12" />
                <Skeleton className="h-20 w-full rounded-lg" />
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </SkeletonRegion>
  )
}
