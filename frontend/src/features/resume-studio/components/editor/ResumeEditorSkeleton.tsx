/**
 * The resume editor while the resume, its draft and the templates load. Mirrors `Editor` in
 * `pages/resume/ResumeEditor.tsx`: header (back link, title + badge + status, actions), the
 * provenance note, then — from `lg` — the section rail | section form card | live preview
 * columns; below `lg`, the Edit / Preview tab bar over the edit column.
 */
import { SkeletonLine, SkeletonRegion } from '@/components/common/skeletons'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

/** `SectionList`: "Sections" label, the 42 px "Name & contact" row, sortable 38 px rows with
 *  icon chips, "Add section". Sticky on xl like the real rail. */
function SectionRailSkeleton() {
  return (
    <div className="min-w-0 space-y-2 xl:sticky xl:top-20 xl:self-start">
      <div className="flex h-4 items-center px-1">
        <Skeleton className="h-2.5 w-16" />
      </div>
      <div className="flex h-[42px] items-center gap-2.5 rounded-xl border border-border bg-card px-2">
        <Skeleton className="size-7 shrink-0 rounded-lg" />
        <Skeleton className="h-3.5 w-24" />
      </div>
      <ul className="space-y-1.5">
        {[20, 12, 22, 16, 20, 24].map((width, index) => (
          <li key={index} className="flex h-[38px] items-center gap-2 rounded-xl border border-border bg-card pl-2 pr-2">
            <Skeleton className="size-4 shrink-0 rounded" />
            <Skeleton className="size-7 shrink-0 rounded-lg" />
            <Skeleton className="h-3.5" style={{ width: `${width * 0.2}rem` }} />
            <Skeleton className="ml-auto h-4 w-5 shrink-0 rounded-full" />
          </li>
        ))}
      </ul>
      <Skeleton className="h-8 w-full rounded-md" />
    </div>
  )
}

/** The section form card — the "Name & contact" panel (`HeaderFields`) the editor opens on. */
function SectionFormSkeleton() {
  const labels = [16, 16, 10, 10, 14, 28, 22, 20, 28]
  return (
    <Card className="overflow-hidden">
      {/* Section header band: 40 px chip + title + one line, py-4, hairline below. */}
      <div className="flex items-center gap-3 border-b border-border px-6 py-4">
        <Skeleton className="size-10 shrink-0 rounded-xl" />
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex h-[1.625rem] items-center">
            <Skeleton className="h-4 w-32" />
          </div>
          <SkeletonLine size="sm" className="w-56 max-w-full" />
        </div>
      </div>
      <CardContent className="p-6">
        <div className="grid gap-3 2xl:grid-cols-2">
          {labels.map((width, index) => (
            <div key={index} className={index === labels.length - 1 ? 'space-y-1 2xl:col-span-2' : 'space-y-1'}>
              <div className="flex h-4 items-center">
                <Skeleton className="h-2.5" style={{ width: `${width * 0.25}rem` }} />
              </div>
              <Skeleton className="h-9 w-full rounded-lg" />
              {index === 5 ? <SkeletonLine size="xs" className="w-40" /> : null}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function EditPaneSkeleton() {
  return (
    <div className="grid gap-4 xl:grid-cols-[12.5rem_minmax(0,1fr)]">
      <SectionRailSkeleton />
      <SectionFormSkeleton />
    </div>
  )
}

/** Template select + zoom group, then the A4 page in its muted frame. */
function PreviewPaneSkeleton() {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Skeleton className="h-8 w-44 rounded-lg" />
        <div className="flex items-center gap-1">
          <Skeleton className="size-8 rounded-md" />
          <div className="flex w-12 justify-center">
            <Skeleton className="h-3 w-8" />
          </div>
          <Skeleton className="size-8 rounded-md" />
          <Skeleton className="size-8 rounded-md" />
        </div>
      </div>
      <div className="overflow-hidden rounded-lg border border-border bg-muted/50 p-3 pb-8">
        {/* An A4 page (794 × 1123) at fit-to-width. */}
        <div className="aspect-[794/1123] w-full space-y-3 rounded-sm bg-card p-[6%] shadow-xs">
          <Skeleton className="h-6 w-1/2" />
          <Skeleton className="h-3 w-2/3" />
          <div className="space-y-2 pt-4">
            <Skeleton className="h-3.5 w-1/4" />
            <Skeleton className="h-2.5 w-full" />
            <Skeleton className="h-2.5 w-full" />
            <Skeleton className="h-2.5 w-4/5" />
          </div>
          <div className="space-y-2 pt-4">
            <Skeleton className="h-3.5 w-1/4" />
            <Skeleton className="h-2.5 w-full" />
            <Skeleton className="h-2.5 w-11/12" />
            <Skeleton className="h-2.5 w-full" />
            <Skeleton className="h-2.5 w-3/5" />
          </div>
          <div className="space-y-2 pt-4">
            <Skeleton className="h-3.5 w-1/4" />
            <Skeleton className="h-2.5 w-full" />
            <Skeleton className="h-2.5 w-2/3" />
          </div>
        </div>
      </div>
    </div>
  )
}

export function ResumeEditorSkeleton() {
  return (
    <SkeletonRegion label="Opening the editor" className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between" aria-hidden>
        <div className="min-w-0 space-y-1">
          <SkeletonLine size="sm" className="w-40" />
          <div className="flex h-7 flex-wrap items-center gap-2">
            <Skeleton className="h-5 w-32" />
            <Skeleton className="h-[22px] w-16 rounded-full" />
            <Skeleton className="h-3 w-36" />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Skeleton className="h-8 w-24 rounded-md" />
          <Skeleton className="h-8 w-32 rounded-md" />
        </div>
      </div>

      <div className="space-y-1" aria-hidden>
        <SkeletonLine size="xs" className="w-full max-w-3xl" />
        <SkeletonLine size="xs" className="w-1/2" />
      </div>

      {/* Desktop: edit | preview side by side. */}
      <div className="hidden grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)] gap-5 lg:grid" aria-hidden>
        <EditPaneSkeleton />
        <PreviewPaneSkeleton />
      </div>
      {/* Mobile / tablet: the Edit / Preview tab bar over the edit column. */}
      <div className="lg:hidden" aria-hidden>
        <Skeleton className="h-9 w-full rounded-full" />
        <div className="mt-4">
          <EditPaneSkeleton />
        </div>
      </div>
    </SkeletonRegion>
  )
}
