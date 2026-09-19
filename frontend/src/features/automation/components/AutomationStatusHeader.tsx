import { CalendarClock, Gauge, Play, Settings2, ShieldCheck, StopCircle, Target, TestTube2 } from 'lucide-react'
import type { ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { formatApiDateTime, formatCountdown } from '@/features/automation/datetime'
import { stepLabel } from '@/features/automation/steps'
import type { AutomationConfigRead, AutomationRunRead, AutomationStatus } from '@/types/api'

export interface AutomationStatusHeaderProps {
  status: AutomationStatus | undefined
  config: AutomationConfigRead | undefined
  /** The run currently selected/being polled — used for the live step readout. */
  activeRun: AutomationRunRead | null
  loading?: boolean
  togglePending?: boolean
  runPending?: boolean
  dryRunPending?: boolean
  cancelPending?: boolean
  onToggleEnabled: (enabled: boolean) => void
  onRunNow: () => void
  onDryRun: () => void
  onCancel: () => void
  onEditConfig: () => void
}

function Metric({
  icon: Icon,
  label,
  children,
}: {
  icon: typeof Gauge
  label: string
  children: ReactNode
}) {
  return (
    <div className="min-w-0 space-y-1">
      <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <Icon className="size-3.5" aria-hidden />
        {label}
      </p>
      <div className="text-sm text-foreground">{children}</div>
    </div>
  )
}

/**
 * Top of the Automation page: the master switch, the schedule, today's budget and the
 * buttons that start, dry-run or cancel the pipeline.
 */
export function AutomationStatusHeader({
  status,
  config,
  activeRun,
  loading = false,
  togglePending = false,
  runPending = false,
  dryRunPending = false,
  cancelPending = false,
  onToggleEnabled,
  onRunNow,
  onDryRun,
  onCancel,
  onEditConfig,
}: AutomationStatusHeaderProps) {
  const running = Boolean(status?.running) || activeRun?.status === 'RUNNING'
  const enabled = status?.enabled ?? config?.enabled ?? false

  const dailyLimit = status?.today.daily_limit ?? config?.daily_application_limit ?? 0
  const submittedToday = status?.today.applications_submitted ?? 0
  const remaining = status?.today.limit_remaining ?? Math.max(0, dailyLimit - submittedToday)
  const usedPercent = dailyLimit > 0 ? Math.min(100, Math.round((submittedToday / dailyLimit) * 100)) : 0

  const countdown = formatCountdown(status?.next_run_at ?? config?.next_run_at)
  const scheduleSummary = config
    ? `Daily at ${config.schedule_time} ${config.timezone}`
    : 'Schedule not configured'

  if (loading) {
    return (
      <Card>
        <CardContent className="space-y-4 p-6">
          <Skeleton className="h-6 w-56" />
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 4 }, (_, index) => (
              <Skeleton key={index} className="h-12 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className={cn(running && 'border-primary/40 shadow-[0_0_0_1px] shadow-primary/10')}>
      <CardContent className="space-y-5 p-5 sm:p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-start gap-3">
            <Switch
              id="automation-enabled"
              checked={enabled}
              disabled={togglePending}
              onCheckedChange={onToggleEnabled}
              aria-label="Enable the daily automation run"
            />
            <div className="space-y-1">
              <label htmlFor="automation-enabled" className="block text-sm font-semibold">
                {enabled ? 'Automation is on' : 'Automation is off'}
              </label>
              <p className="text-sm text-muted-foreground">
                {running
                  ? `Running now — ${stepLabel(activeRun?.current_step ?? null)}`
                  : enabled
                    ? 'The pipeline runs on its schedule and stops at your safety rails.'
                    : 'Nothing runs on a schedule. You can still start a run by hand.'}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {running ? (
              <Button variant="destructive" onClick={onCancel} loading={cancelPending}>
                <StopCircle />
                Cancel run
              </Button>
            ) : (
              <>
                <Button variant="outline" onClick={onDryRun} loading={dryRunPending} disabled={runPending}>
                  <TestTube2 />
                  Dry run
                </Button>
                <Button onClick={onRunNow} loading={runPending} disabled={dryRunPending}>
                  <Play />
                  Run now
                </Button>
              </>
            )}
            <Button variant="ghost" size="icon" onClick={onEditConfig} aria-label="Edit automation settings">
              <Settings2 />
            </Button>
          </div>
        </div>

        <div className="grid gap-5 border-t border-border pt-5 sm:grid-cols-2 lg:grid-cols-4">
          <Metric icon={CalendarClock} label="Schedule">
            <p className="truncate font-medium">{scheduleSummary}</p>
            <p className="text-xs text-muted-foreground">
              {status?.next_run_at || config?.next_run_at
                ? `Next run ${countdown ?? ''} · ${formatApiDateTime(status?.next_run_at ?? config?.next_run_at)}`
                : 'No run scheduled'}
            </p>
          </Metric>

          <Metric icon={Gauge} label="Today's budget">
            <p className="font-medium tabular-nums">
              {submittedToday} / {dailyLimit || '—'} applications
            </p>
            <Progress
              value={usedPercent}
              className="mt-1.5 h-1.5"
              indicatorClassName={usedPercent >= 100 ? 'bg-warning' : 'bg-primary'}
              aria-label={`${submittedToday} of ${dailyLimit} applications used today`}
            />
            <p className="mt-1 text-xs text-muted-foreground">{remaining} left today</p>
          </Metric>

          <Metric icon={Target} label="Minimum match">
            <p className="font-medium tabular-nums">{config?.min_match_score ?? '—'}%</p>
            <p className="text-xs text-muted-foreground">
              {config?.prioritize_priority_companies ? 'P1 companies jump the queue' : 'No priority boost'}
            </p>
          </Metric>

          <Metric icon={ShieldCheck} label="Auto-submit">
            <p className={cn('font-medium', config?.auto_submit_enabled ? 'text-warning' : 'text-foreground')}>
              {config?.auto_submit_enabled ? 'Enabled' : 'Off — you approve each one'}
            </p>
            <p className="text-xs text-muted-foreground">
              {config?.auto_submit_enabled
                ? `${config.auto_submit_sources.length || 'All'} allowed source${config.auto_submit_sources.length === 1 ? '' : 's'}`
                : 'Applications wait in the review queue'}
            </p>
          </Metric>
        </div>
      </CardContent>
    </Card>
  )
}
