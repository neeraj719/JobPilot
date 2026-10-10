import { AlertTriangle, Ban, Send, TriangleAlert } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { RunStatusBadge } from '@/features/automation/components/RunStatusBadge'
import { durationBetween, formatApiDateTime, formatDuration } from '@/features/automation/datetime'
import { readFilterReasons, statCount } from '@/features/automation/stats'
import { failedStep, stepLabel } from '@/features/automation/steps'
import type { AutomationRunRead, AutomationRunStats } from '@/types/api'

interface StatDefinition {
  key: keyof AutomationRunStats & string
  label: string
  tone?: 'default' | 'success' | 'warning' | 'destructive'
}

const STAT_TILES: StatDefinition[] = [
  { key: 'jobs_found', label: 'Jobs found' },
  { key: 'jobs_new', label: 'New' },
  { key: 'duplicates_merged', label: 'Duplicates merged' },
  { key: 'jobs_analyzed', label: 'Analysed' },
  { key: 'jobs_matched', label: 'Matched' },
  { key: 'high_match', label: 'High match', tone: 'success' },
  { key: 'queued', label: 'Queued' },
  { key: 'discover_only', label: 'Discover only' },
  { key: 'prepared', label: 'Prepared' },
  { key: 'submitted', label: 'Submitted', tone: 'success' },
  { key: 'requires_user', label: 'Needs you', tone: 'warning' },
  { key: 'failed', label: 'Failed', tone: 'destructive' },
  { key: 'skipped_limit', label: 'Skipped (limit)' },
]

const TONE_CLASS: Record<NonNullable<StatDefinition['tone']>, string> = {
  default: 'text-foreground',
  success: 'text-success',
  warning: 'text-warning',
  destructive: 'text-destructive',
}

export interface RunSummaryProps {
  run: AutomationRunRead | null | undefined
  loading?: boolean
}

/** Headline outcome of one run: status line, failure callout and the twelve counters. */
export function RunSummary({ run, loading = false }: RunSummaryProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {Array.from({ length: STAT_TILES.length }, (_, index) => (
          <Skeleton key={index} className="h-[72px] w-full rounded-lg" />
        ))}
      </div>
    )
  }

  if (!run) return null

  const stats = run.stats
  const elapsed = durationBetween(run.started_at, run.finished_at ?? new Date().toISOString())
  const broken = failedStep(run)
  const requiresUser = statCount(stats, 'requires_user')
  const filterReasons = readFilterReasons(stats)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
        <RunStatusBadge status={run.status} />
        <span className="text-muted-foreground">
          {run.trigger === 'MANUAL' ? 'Started by you' : 'Scheduled'} · {formatApiDateTime(run.started_at)}
        </span>
        <span className="text-muted-foreground">
          {run.finished_at ? `Took ${formatDuration(elapsed)}` : `Running for ${formatDuration(elapsed)}`}
        </span>
        {run.current_step ? (
          <span className="rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
            {stepLabel(run.current_step)}
          </span>
        ) : null}
      </div>

      {run.error || broken ? (
        <div
          role="alert"
          className="flex flex-col gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-4 sm:flex-row sm:items-start"
        >
          <AlertTriangle className="mt-0.5 size-5 shrink-0 text-destructive" aria-hidden />
          <div className="min-w-0 space-y-1">
            <p className="text-sm font-semibold text-destructive">
              {broken ? `The run failed at "${stepLabel(broken.step)}"` : 'The run reported an error'}
            </p>
            <p className="break-words text-sm text-muted-foreground">
              {run.error || broken?.message || 'No further detail was recorded.'}
            </p>
          </div>
        </div>
      ) : null}

      {requiresUser > 0 ? (
        <div className="flex flex-col gap-2 rounded-lg border border-warning/30 bg-warning/5 p-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="flex items-start gap-2 text-sm">
            <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
            <span>
              <span className="font-semibold">
                {requiresUser} application{requiresUser === 1 ? '' : 's'} need your input
              </span>{' '}
              <span className="text-muted-foreground">
                before they can be submitted — the automation stopped rather than guessing.
              </span>
            </span>
          </p>
          <Button asChild variant="outline" size="sm" className="shrink-0">
            <Link to="/queue">
              <Send />
              Open the review queue
            </Link>
          </Button>
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {STAT_TILES.map((tile) => {
          const value = statCount(stats, tile.key)
          return (
            <Card key={tile.key} className={cn(value === 0 && 'opacity-70')}>
              <CardContent className="space-y-0.5 p-3">
                <p className={cn('text-xl font-semibold tabular-nums', TONE_CLASS[tile.tone ?? 'default'])}>{value}</p>
                <p className="truncate text-xs text-muted-foreground" title={tile.label}>
                  {tile.label}
                </p>
              </CardContent>
            </Card>
          )
        })}
      </div>

      {filterReasons ? (
        <div className="rounded-lg border border-border bg-muted/30 p-3">
          <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <Ban className="size-3.5" aria-hidden />
            Why {statCount(stats, 'filtered_out')} jobs were dropped
          </p>
          <ul className="flex flex-wrap gap-1.5">
            {Object.entries(filterReasons).map(([reason, count]) => (
              <li
                key={reason}
                className="rounded-md border border-border bg-card px-2 py-0.5 text-xs text-muted-foreground"
              >
                <span className="font-semibold text-foreground tabular-nums">{count}</span>{' '}
                {reason.replace(/_/g, ' ')}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
