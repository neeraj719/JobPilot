import { CircleCheck, TriangleAlert } from 'lucide-react'

import { Card, CardContent } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { MISSING_FIELD_LABELS, MISSING_FIELD_TABS, type ProfileTab } from '@/features/profile/schema'

export interface ProfileCompletenessProps {
  completeness: number
  missingFields: string[]
  loading?: boolean
  onJumpTo: (tab: ProfileTab) => void
}

function barColor(value: number): string {
  if (value >= 90) return 'bg-success'
  if (value >= 60) return 'bg-warning'
  return 'bg-destructive'
}

/**
 * Completeness meter + the fields the backend still counts as missing. Each chip jumps
 * to the tab that owns the field, so "fix what's missing" is one click away.
 */
export function ProfileCompleteness({ completeness, missingFields, loading, onJumpTo }: ProfileCompletenessProps) {
  if (loading) {
    return (
      <Card role="status" aria-busy="true">
        <span className="sr-only">Loading profile completeness</span>
        <CardContent className="space-y-3 py-5" aria-hidden>
          <div className="flex h-5 items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Skeleton className="size-4 rounded-full" />
              <Skeleton className="h-3.5 w-36" />
            </div>
            <Skeleton className="h-3.5 w-9" />
          </div>
          <Skeleton className="h-2 w-full rounded-full" />
          <div className="flex h-[22px] flex-wrap items-center gap-1.5">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-[22px] w-20 rounded-full" />
            <Skeleton className="h-[22px] w-24 rounded-full" />
          </div>
        </CardContent>
      </Card>
    )
  }

  const complete = missingFields.length === 0

  return (
    <Card>
      <CardContent className="space-y-3 py-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            {complete ? (
              <CircleCheck className="size-4 text-success" aria-hidden />
            ) : (
              <TriangleAlert className="size-4 text-warning" aria-hidden />
            )}
            <h2 className="text-sm font-medium">Profile completeness</h2>
          </div>
          <span className="text-sm font-semibold tabular-nums">{completeness}%</span>
        </div>

        <Progress
          value={completeness}
          indicatorClassName={barColor(completeness)}
          aria-label={`Profile ${completeness} percent complete`}
        />

        {complete ? (
          <p className="text-xs text-muted-foreground">
            Everything the answer engine needs is on file. Applications will not have to stop and ask you.
          </p>
        ) : (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-muted-foreground">Still missing:</span>
            {missingFields.map((field) => (
              <button
                key={field}
                type="button"
                onClick={() => onJumpTo(MISSING_FIELD_TABS[field] ?? 'personal')}
                className={cn(
                  'rounded-full border border-warning/30 bg-warning/10 px-2 py-0.5 text-xs font-medium text-warning',
                  'transition-colors hover:bg-warning/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                )}
              >
                {MISSING_FIELD_LABELS[field] ?? field}
              </button>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
