/**
 * Loading skeletons for the Workspace settings cards (landing preference, module order) and
 * the admin module cards. Rows mirror the loaded `li` markup: `p-3`, a 36 px icon tile, a
 * title (+ badge) line over a caption, and the row's own trailing controls.
 */
import { SkeletonLine, SkeletonRegion } from '@/components/common/skeletons'
import { Skeleton } from '@/components/ui/skeleton'

type Trailing = 'arrows' | 'switch' | 'select-switch'

/** Divided, bordered module rows. */
export function ModuleRowsSkeleton({
  rows = 3,
  trailing,
  label = 'Loading modules',
  bare,
}: {
  rows?: number
  trailing: Trailing
  label?: string
  /** Inside another skeleton region: no status region of its own. */
  bare?: boolean
}) {
  const list = (
    <ul className="divide-y divide-border rounded-lg border border-border" aria-hidden>
      {Array.from({ length: rows }, (_, index) => (
        <li key={index} className="flex items-center gap-3 p-3">
          <Skeleton className="size-9 shrink-0 rounded-md" />
          <div className="min-w-0 flex-1">
            <div className="flex h-[22px] items-center gap-2">
              <Skeleton className="h-3.5 w-32" />
              {index === 0 ? <Skeleton className="h-[22px] w-16 rounded-full" /> : null}
            </div>
            <SkeletonLine size="xs" className={index % 2 ? 'w-40' : 'w-56'} boxClassName="max-w-full" />
          </div>
          {trailing === 'arrows' ? (
            <div className="flex shrink-0 items-center gap-1">
              <Skeleton className="size-8 rounded-lg" />
              <Skeleton className="size-8 rounded-lg" />
              <Skeleton className="size-8 rounded-lg" />
            </div>
          ) : null}
          {trailing === 'select-switch' ? <Skeleton className="h-8 w-36 shrink-0 rounded-lg" /> : null}
          {trailing !== 'arrows' ? <Skeleton className="h-5 w-9 shrink-0 rounded-full" /> : null}
        </li>
      ))}
    </ul>
  )
  return bare ? list : <SkeletonRegion label={label}>{list}</SkeletonRegion>
}

/** `LandingForm`: the radio cards, the tips toggle row, the save button. */
export function LandingFormSkeleton({ options = 2 }: { options?: number }) {
  return (
    <SkeletonRegion label="Loading workspace preferences" className="space-y-5">
      <div className="space-y-2" aria-hidden>
        <SkeletonLine size="sm" className="w-36" />
        <div className="grid gap-2">
          {Array.from({ length: options }, (_, index) => (
            <div key={index} className="flex items-start gap-3 rounded-lg border border-border p-3">
              <Skeleton className="mt-0.5 size-4 shrink-0 rounded-full" />
              <div className="min-w-0 flex-1 space-y-0.5">
                <SkeletonLine size="sm" className="w-32" />
                <SkeletonLine size="xs" className="w-72 max-w-full" />
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="flex items-center justify-between gap-4 rounded-lg border border-border p-3" aria-hidden>
        <div className="min-w-0 flex-1 space-y-0.5">
          <SkeletonLine size="sm" className="w-48" />
          <SkeletonLine size="xs" className="w-64 max-w-full" />
        </div>
        <Skeleton className="h-5 w-9 shrink-0 rounded-full" />
      </div>
      <div className="flex justify-end" aria-hidden>
        <Skeleton className="h-9 w-36 rounded-lg" />
      </div>
    </SkeletonRegion>
  )
}

/** Admin › Modules for user, after a lookup: the account line, then the module switches. */
export function AdminUserModulesSkeleton() {
  return (
    <SkeletonRegion label="Finding the account" className="space-y-3">
      <div className="flex h-5 items-center gap-2" aria-hidden>
        <Skeleton className="size-4 rounded-full" />
        <Skeleton className="h-3.5 w-32" />
        <Skeleton className="h-3.5 w-44" />
      </div>
      <ModuleRowsSkeleton rows={3} trailing="switch" bare />
    </SkeletonRegion>
  )
}
