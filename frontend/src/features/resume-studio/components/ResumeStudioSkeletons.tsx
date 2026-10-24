/**
 * Loading skeletons for the Resume Studio screens (My Resumes grid, one resume's detail, the
 * Version History timeline). Each mirrors the loaded markup box for box — same Card frames,
 * paddings, line heights and grids — so nothing moves when the data arrives.
 */
import { SkeletonLine, SkeletonRegion } from '@/components/common/skeletons'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { ResumePanelsSkeleton } from '@/features/resume/components/ResumeSkeletons'

/** One `StudioResumeCard`: 144 px preview strip, name + role, badge row, "Edited …". */
export function StudioResumeCardSkeleton() {
  return (
    <Card className="flex flex-col overflow-hidden" aria-hidden>
      <div className="relative h-36 overflow-hidden border-b border-border bg-muted/60 px-4 pt-3">
        {/* The 0.3-scale page preview (794 px × 0.3). */}
        <Skeleton className="h-full w-[238px] max-w-full rounded-b-none rounded-t-sm" />
      </div>
      <CardContent className="flex flex-1 flex-col gap-2 p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <SkeletonLine size="base" className="w-2/3" />
            <SkeletonLine size="xs" className="w-2/5" />
          </div>
          <Skeleton className="size-8 shrink-0 rounded-md" />
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Skeleton className="h-[22px] w-16 rounded-full" />
          <Skeleton className="h-[22px] w-9 rounded-full" />
        </div>
        <SkeletonLine size="xs" className="w-28" boxClassName="mt-auto" />
      </CardContent>
    </Card>
  )
}

/** The My Resumes grid (1 / 2 / 3 columns, gap-4). */
export function ResumeCardGridSkeleton({ count = 6, className }: { count?: number; className?: string }) {
  return (
    <SkeletonRegion label="Loading your resumes" className={cn('grid gap-4 sm:grid-cols-2 xl:grid-cols-3', className)}>
      {Array.from({ length: count }, (_, index) => (
        <StudioResumeCardSkeleton key={index} />
      ))}
    </SkeletonRegion>
  )
}

/**
 * `/resume/my/:id` while the resume loads: back link, title, badge row and actions, the
 * target-role bar, then the insights, extracted-data and version-history cards.
 */
export function ResumeDetailSkeleton() {
  return (
    <SkeletonRegion label="Loading resume" className="space-y-6">
      <div className="space-y-3" aria-hidden>
        <SkeletonLine size="sm" className="w-28" />
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 flex-1 space-y-1.5">
            <SkeletonLine size="2xl" className="w-72 max-w-[80%] rounded-lg" />
            <div className="flex flex-wrap items-center gap-1.5">
              <Skeleton className="h-[22px] w-16 rounded-full" />
              <Skeleton className="h-[22px] w-20 rounded-full" />
              <Skeleton className="h-[22px] w-9 rounded-full" />
              <Skeleton className="h-3.5 w-28" />
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <Skeleton className="h-8 w-32 rounded-md" />
            <Skeleton className="h-8 w-24 rounded-md" />
            <Skeleton className="h-8 w-24 rounded-md" />
            <Skeleton className="h-8 w-32 rounded-md" />
          </div>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border p-3" aria-hidden>
        <SkeletonLine size="sm" className="w-20" />
        <Skeleton className="h-8 w-64 rounded-lg" />
        <div className="ml-auto flex flex-wrap gap-2">
          {[16, 20, 24, 16, 16].map((width, index) => (
            <Skeleton key={index} className="h-8 rounded-md" style={{ width: `${width * 0.25}rem` }} />
          ))}
        </div>
      </div>
      <ResumePanelsSkeleton bare />
    </SkeletonRegion>
  )
}

/** Version History: day headings over a left-ruled timeline of version cards. */
export function VersionTimelineSkeleton({ groups = [3, 2] }: { groups?: number[] }) {
  return (
    <SkeletonRegion label="Loading version history" className="space-y-6">
      {groups.map((rows, group) => (
        <section key={group} className="space-y-3" aria-hidden>
          <div className="flex h-6 items-center gap-2">
            <Skeleton className="h-6 w-24 rounded-full" />
            <Skeleton className="h-3 w-14" />
          </div>
          <ol className="relative space-y-3 pl-11">
            <span className="absolute inset-y-3 left-[15px] w-0.5 rounded-full bg-border" />
            {Array.from({ length: rows }, (_, index) => (
              <li key={index} className="relative">
                <Skeleton className="absolute -left-11 top-3.5 size-8 rounded-full ring-4 ring-background" />
                <Card>
                  <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
                    <div className="min-w-0 flex-1 space-y-1.5">
                      <div className="flex h-6 flex-wrap items-center gap-1.5">
                        <Skeleton className="h-4 w-40" />
                        <Skeleton className="h-[22px] w-9 rounded-full" />
                        <Skeleton className="h-[22px] w-16 rounded-full" />
                        <Skeleton className="h-[22px] w-16 rounded-full" />
                      </div>
                      <SkeletonLine size="sm" className={index % 2 ? 'w-2/5' : 'w-3/5'} />
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <Skeleton className="h-3 w-14" />
                      <Skeleton className="h-8 w-[6.5rem] rounded-md" />
                      <Skeleton className="h-8 w-24 rounded-md" />
                    </div>
                  </CardContent>
                </Card>
              </li>
            ))}
          </ol>
        </section>
      ))}
    </SkeletonRegion>
  )
}

/** `DiffView` inside the compare dialog: labels line, column captions, grouped field diffs. */
export function DiffViewSkeleton() {
  return (
    <SkeletonRegion label="Loading the comparison" className="space-y-4">
      <div className="flex h-5 flex-wrap items-center gap-2" aria-hidden>
        <Skeleton className="h-3.5 w-20" />
        <Skeleton className="size-4 rounded" />
        <Skeleton className="h-3.5 w-20" />
        <Skeleton className="h-3.5 w-40" />
      </div>
      <div className="hidden grid-cols-2 gap-3 px-1 sm:grid" aria-hidden>
        <SkeletonLine size="xs" className="w-16" />
        <SkeletonLine size="xs" className="w-16" />
      </div>
      {[2, 1].map((items, group) => (
        <section key={group} className="space-y-2" aria-hidden>
          <SkeletonLine size="sm" className="w-24" />
          <ul className="space-y-2">
            {Array.from({ length: items }, (_, index) => (
              <li key={index} className="rounded-md border border-border p-2">
                <div className="mb-1.5 flex items-center gap-2">
                  <Skeleton className="h-[22px] w-16 rounded-full" />
                  <Skeleton className="h-3 w-24" />
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <div>
                    <SkeletonLine size="sm" className="w-full" />
                    <SkeletonLine size="sm" className="w-3/5" />
                  </div>
                  <div>
                    <SkeletonLine size="sm" className="w-full" />
                    <SkeletonLine size="sm" className="w-2/3" />
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </SkeletonRegion>
  )
}
