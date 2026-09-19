import { ArrowRight, Bot, Play } from 'lucide-react'
import * as React from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { errorMessage } from '@/lib/api'
import { AUTOMATION_STATE_LABELS, cn, formatDateTime, formatNumber, formatRelative } from '@/lib/utils'
import type { AutomationRunRead, AutomationStatus } from '@/types/api'

import { useAutomationRun, useRefreshDashboard, useStartAutomationRun } from '../api'

const RUN_STAT_ROWS: { key: string; label: string }[] = [
  { key: 'jobs_found', label: 'Found' },
  { key: 'jobs_matched', label: 'Matched' },
  { key: 'queued', label: 'Queued' },
  { key: 'submitted', label: 'Submitted' },
]

function runTone(run: AutomationRunRead | null | undefined): string {
  switch (run?.status) {
    case 'SUCCESS':
      return 'bg-success/10 text-success border-success/20'
    case 'FAILED':
      return 'bg-destructive/10 text-destructive border-destructive/20'
    case 'RUNNING':
      return 'bg-primary/10 text-primary border-primary/20'
    case 'CANCELLED':
      return 'bg-muted text-muted-foreground border-transparent'
    default:
      return 'bg-muted text-muted-foreground border-transparent'
  }
}

/**
 * Automation status plus the "Run now" affordance.
 *
 * Starting a run answers 202 with a RUNNING row, so the card takes that id and polls
 * `GET /automation/runs/{id}` until it settles, then refreshes everything the pipeline
 * touched (stats, charts, activity, queue).
 */
export function AutomationCard({
  status,
  className,
}: {
  status: AutomationStatus | undefined
  className?: string
}) {
  const [startedRunId, setStartedRunId] = React.useState<string | null>(null)
  const startRun = useStartAutomationRun()
  const refreshDashboard = useRefreshDashboard()

  // Adopt a run that was already in flight when the page loaded.
  const activeRunId = startedRunId ?? (status?.running ? (status.last_run?.id ?? null) : null)
  const { data: polledRun } = useAutomationRun(activeRunId)

  const settledRef = React.useRef<string | null>(null)
  React.useEffect(() => {
    if (!polledRun || polledRun.status === 'RUNNING') return
    if (settledRef.current === polledRun.id) return
    settledRef.current = polledRun.id
    setStartedRunId(null)
    refreshDashboard()
    if (polledRun.status === 'SUCCESS') {
      const stats = polledRun.stats ?? {}
      toast.success('Automation run finished', {
        description: `${formatNumber(stats.jobs_found ?? 0)} jobs found · ${formatNumber(stats.queued ?? 0)} queued · ${formatNumber(stats.submitted ?? 0)} submitted`,
      })
    } else if (polledRun.status === 'FAILED') {
      toast.error('Automation run failed', { description: polledRun.error ?? 'Open Automation for the step log.' })
    }
  }, [polledRun, refreshDashboard])

  const isRunning = Boolean(activeRunId) || Boolean(status?.running) || startRun.isPending
  const lastRun = polledRun ?? status?.last_run ?? null
  const stats = lastRun?.stats ?? {}

  const handleRun = () => {
    startRun.mutate(
      {},
      {
        onSuccess: (run) => {
          setStartedRunId(run.id)
          settledRef.current = null
          toast.success('Automation started', { description: 'Searching, matching and queueing — this takes a moment.' })
        },
        onError: (error) => {
          toast.error('Could not start the automation', { description: errorMessage(error) })
        },
      },
    )
  }

  return (
    <Card className={cn('flex min-w-0 flex-col', className)}>
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
        <div className="min-w-0 space-y-1">
          <CardTitle className="flex items-center gap-2 text-base">
            <Bot className="size-4 text-muted-foreground" aria-hidden />
            Automation
          </CardTitle>
          <CardDescription>
            {status?.enabled === false
              ? 'Disabled — nothing runs on a schedule.'
              : status?.next_run_at
                ? `Next run ${formatRelative(status.next_run_at)} · ${formatDateTime(status.next_run_at)}`
                : 'Enabled — no run scheduled yet.'}
          </CardDescription>
        </div>
        <span
          className={cn(
            'shrink-0 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium',
            status?.enabled ? 'bg-success/10 text-success border-success/20' : 'bg-muted text-muted-foreground border-transparent',
          )}
        >
          {status?.enabled ? 'Enabled' : 'Disabled'}
        </span>
      </CardHeader>

      <CardContent className="flex-1 space-y-4">
        <div className="rounded-lg border border-border bg-muted/30 p-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-medium text-muted-foreground">
              {isRunning ? 'Current run' : 'Last run'}
              {lastRun ? ` · ${formatRelative(lastRun.started_at)}` : ''}
            </p>
            {lastRun ? (
              <span className={cn('rounded-full border px-2 py-0.5 text-[11px] font-medium', runTone(lastRun))}>
                {lastRun.status === 'RUNNING'
                  ? (lastRun.current_step ?? AUTOMATION_STATE_LABELS.RUNNING)
                  : lastRun.status.charAt(0) + lastRun.status.slice(1).toLowerCase()}
              </span>
            ) : null}
          </div>
          {lastRun ? (
            <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
              {RUN_STAT_ROWS.map((row) => (
                <div key={row.key}>
                  <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">{row.label}</dt>
                  <dd className="text-base font-semibold tabular-nums">{formatNumber(stats[row.key] ?? 0)}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="mt-2 text-sm text-muted-foreground">No runs yet. Start one to fill the queue.</p>
          )}
          {lastRun?.error ? <p className="mt-2 text-xs text-destructive">{lastRun.error}</p> : null}
        </div>

        {status?.today ? (
          <p className="text-xs text-muted-foreground">
            {formatNumber(status.today.applications_submitted)} submitted today
            {status.today.daily_limit !== undefined
              ? ` of a ${formatNumber(status.today.daily_limit)} daily limit`
              : ''}
            {' · '}
            {formatNumber(status.today.limit_remaining)} remaining
          </p>
        ) : null}
      </CardContent>

      <CardFooter className="flex flex-wrap gap-2">
        <Button onClick={handleRun} loading={startRun.isPending} disabled={isRunning} size="sm">
          {!startRun.isPending ? <Play aria-hidden /> : null}
          {isRunning ? 'Running…' : 'Run now'}
        </Button>
        <Button asChild variant="ghost" size="sm">
          <Link to="/automation">
            Automation settings
            <ArrowRight aria-hidden />
          </Link>
        </Button>
      </CardFooter>
    </Card>
  )
}
