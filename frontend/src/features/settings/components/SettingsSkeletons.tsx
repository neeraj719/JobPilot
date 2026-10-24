/**
 * Loading skeletons for the Settings cards. Each one mirrors the loaded rows of its card
 * (frames, paddings, line heights) so the card does not change height when data arrives.
 */
import { SkeletonLine, SkeletonRegion } from '@/components/common/skeletons'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

/** `AiSettingsCard` rows: label left, value (text or badge) right, `py-2` with hairlines. */
export function InfoRowsSkeleton({ rows = 3, label = 'Loading' }: { rows?: number; label?: string }) {
  return (
    <SkeletonRegion label={label}>
      <div aria-hidden>
        {Array.from({ length: rows }, (_, index) => (
          <div key={index} className="flex items-center justify-between gap-3 border-b border-border py-2 last:border-0">
            <div className="flex h-[22px] items-center">
              <Skeleton className="h-3.5 w-20" />
            </div>
            {index === rows - 1 ? <Skeleton className="h-[22px] w-20 rounded-full" /> : <Skeleton className="h-3.5 w-28" />}
          </div>
        ))}
      </div>
    </SkeletonRegion>
  )
}

/** `ConnectedAccountsCard` adapter rows: name + badges, terms note, Connect button. */
export function AdapterRowsSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <SkeletonRegion label="Loading job boards">
      <ul className="space-y-3" aria-hidden>
        {Array.from({ length: rows }, (_, index) => (
          <li key={index} className="space-y-3 rounded-lg border border-border p-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1 space-y-1.5">
                <div className="flex h-[22px] flex-wrap items-center gap-2">
                  <Skeleton className="h-3.5 w-24" />
                  <Skeleton className="h-[22px] w-14 rounded-full" />
                  {index % 2 ? null : <Skeleton className="h-[22px] w-32 rounded-full" />}
                </div>
                <SkeletonLine size="xs" className="w-full max-w-2xl" />
                <SkeletonLine size="xs" className="w-1/2" />
              </div>
              <Skeleton className="h-8 w-24 shrink-0 rounded-md" />
            </div>
          </li>
        ))}
      </ul>
    </SkeletonRegion>
  )
}

/**
 * Divided, bordered session rows (device sessions and stored browser sessions): a title or
 * badge line over a caption, an action button on the right.
 */
export function SessionRowsSkeleton({ rows = 2, badges = false, label = 'Loading sessions' }: { rows?: number; badges?: boolean; label?: string }) {
  return (
    <SkeletonRegion label={label}>
      <ul className="divide-y divide-border rounded-lg border border-border" aria-hidden>
        {Array.from({ length: rows }, (_, index) => (
          <li key={index} className="flex flex-wrap items-center justify-between gap-3 p-3">
            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex h-[22px] flex-wrap items-center gap-2">
                {badges ? (
                  <>
                    <Skeleton className="h-[22px] w-20 rounded-full" />
                    <Skeleton className="h-[22px] w-14 rounded-full" />
                  </>
                ) : (
                  <>
                    <Skeleton className="h-3.5 w-36" />
                    {index === 0 ? <Skeleton className="h-[22px] w-24 rounded-full" /> : null}
                  </>
                )}
              </div>
              <SkeletonLine size="xs" className={index % 2 ? 'w-48' : 'w-64'} boxClassName="max-w-full" />
            </div>
            <Skeleton className="h-8 w-20 shrink-0 rounded-md" />
          </li>
        ))}
      </ul>
    </SkeletonRegion>
  )
}

/** `EmailIntegrationCard`: the Gmail status row and the read-only-access line. */
export function GmailStatusSkeleton() {
  return (
    <SkeletonRegion label="Loading the Gmail status" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border p-3" aria-hidden>
        <div className="flex items-center gap-3">
          <Skeleton className="size-9 shrink-0 rounded-full" />
          <div>
            <div className="flex h-[22px] items-center gap-2">
              <Skeleton className="h-3.5 w-12" />
              <Skeleton className="h-[22px] w-24 rounded-full" />
            </div>
            <SkeletonLine size="xs" className="w-56" />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Skeleton className="h-8 w-28 rounded-md" />
          <Skeleton className="h-8 w-28 rounded-md" />
        </div>
      </div>
      <div className="flex h-4 flex-wrap items-center gap-2" aria-hidden>
        <Skeleton className="size-3.5 rounded-full" />
        <Skeleton className="h-3 w-28" />
        <Skeleton className="h-3 w-40" />
      </div>
    </SkeletonRegion>
  )
}

/** The checkbox grid of job sources (`SourceCheckboxes`) while the adapter list loads. */
export function SourceCheckboxesSkeleton({ count = 6 }: { count?: number }) {
  const widths = [20, 16, 24, 18, 22, 14]
  return (
    <SkeletonRegion label="Loading the job sources" className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="flex h-4 items-center gap-2" aria-hidden>
          <Skeleton className="size-4 shrink-0 rounded" />
          <Skeleton className="h-3.5" style={{ width: `${(widths[index % widths.length] ?? 20) * 0.25}rem` }} />
        </div>
      ))}
    </SkeletonRegion>
  )
}

/** A bordered toggle row (`ToggleRow`): label + description, switch on the right. */
function ToggleRowSkeleton({ label = 'w-56', description = 'w-80' }: { label?: string; description?: string }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border border-border p-3">
      <div className="min-w-0 flex-1 space-y-0.5">
        <SkeletonLine size="sm" className={label} />
        <SkeletonLine size="xs" className={`${description} max-w-full`} />
      </div>
      <Skeleton className="h-5 w-9 shrink-0 rounded-full" />
    </div>
  )
}

/** A `Field`: label, 36 px control, optional hint. */
function FieldSkeleton({ hint = false, label = 'w-24' }: { hint?: boolean; label?: string }) {
  return (
    <div className="space-y-1.5">
      <SkeletonLine size="sm" className={label} />
      <Skeleton className="h-9 w-full rounded-lg" />
      {hint ? <SkeletonLine size="xs" className="w-36" /> : null}
    </div>
  )
}

/** `AutomationSettingsForm` while the config loads: header, the first form groups, footer. */
export function AutomationSettingsSkeleton() {
  return (
    <SkeletonRegion label="Loading automation settings">
      <Card className="overflow-hidden" aria-hidden>
        <div className="flex flex-col space-y-1.5 p-6">
          <SkeletonLine size="title" className="w-64" />
          <SkeletonLine size="sm" className="w-full max-w-2xl" />
          <SkeletonLine size="sm" className="w-1/2" />
        </div>
        <CardContent className="space-y-6">
          <ToggleRowSkeleton />
          <div className="grid gap-4 sm:grid-cols-2">
            <FieldSkeleton hint label="w-28" />
            <FieldSkeleton label="w-20" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <FieldSkeleton hint label="w-32" />
            <FieldSkeleton hint label="w-36" />
            <FieldSkeleton hint label="w-28" />
          </div>
          <section className="space-y-2">
            <SkeletonLine size="sm" className="w-36" />
            <SkeletonLine size="xs" className="w-80 max-w-full" />
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <FieldSkeleton label="w-20" />
              <FieldSkeleton label="w-20" />
              <FieldSkeleton label="w-20" />
            </div>
          </section>
          <div className="h-px w-full bg-border" />
          <ToggleRowSkeleton label="w-48" description="w-96" />
          <section className="space-y-2">
            <SkeletonLine size="sm" className="w-32" />
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {[20, 16, 24, 18, 22, 14].map((width, index) => (
                <div key={index} className="flex h-4 items-center gap-2">
                  <Skeleton className="size-4 shrink-0 rounded" />
                  <Skeleton className="h-3.5" style={{ width: `${width * 0.25}rem` }} />
                </div>
              ))}
            </div>
          </section>
        </CardContent>
        <div className="flex flex-wrap items-center justify-end gap-2 border-t bg-muted/30 p-6 py-3">
          <Skeleton className="h-8 w-16 rounded-md" />
          <Skeleton className="h-8 w-28 rounded-md" />
        </div>
      </Card>
    </SkeletonRegion>
  )
}
