import { AlertTriangle, CheckCircle2, Circle, Loader2, MinusCircle } from 'lucide-react'
import * as React from 'react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { formatApiClock, formatDuration } from '@/features/automation/datetime'
import { resolveSteps, type ResolvedStep } from '@/features/automation/steps'
import type { AutomationRunRead, AutomationStepStatus } from '@/types/api'

const STATUS_ICON: Record<AutomationStepStatus, typeof Circle> = {
  SUCCESS: CheckCircle2,
  FAILED: AlertTriangle,
  SKIPPED: MinusCircle,
  RUNNING: Loader2,
  PENDING: Circle,
}

const STATUS_ICON_CLASS: Record<AutomationStepStatus, string> = {
  SUCCESS: 'text-success',
  FAILED: 'text-destructive',
  SKIPPED: 'text-muted-foreground',
  RUNNING: 'text-primary animate-spin',
  PENDING: 'text-muted-foreground/40',
}

const STATUS_LABEL: Record<AutomationStepStatus, string> = {
  SUCCESS: 'Done',
  FAILED: 'Failed',
  SKIPPED: 'Skipped',
  RUNNING: 'Running',
  PENDING: 'Waiting',
}

/** Turns `{queued: 6, sources: ['NAUKRI']}` into readable `key value` chips. */
function stepChips(data: Record<string, unknown> | undefined): { key: string; value: string }[] {
  if (!data) return []
  const chips: { key: string; value: string }[] = []
  for (const [key, value] of Object.entries(data)) {
    if (value === null || value === undefined) continue
    if (typeof value === 'number' || typeof value === 'boolean') {
      chips.push({ key, value: String(value) })
    } else if (typeof value === 'string') {
      if (value.length <= 40) chips.push({ key, value })
    } else if (Array.isArray(value)) {
      chips.push({ key, value: `${value.length}` })
    } else if (typeof value === 'object') {
      const entries = Object.entries(value as Record<string, unknown>).filter(([, v]) => typeof v === 'number' && v !== 0)
      for (const [subKey, subValue] of entries) chips.push({ key: subKey, value: String(subValue) })
    }
  }
  return chips.slice(0, 8)
}

function StepRow({ step, isLast }: { step: ResolvedStep; isLast: boolean }) {
  const Icon = STATUS_ICON[step.status]
  const recorded = step.recorded
  const chips = stepChips(recorded?.data)
  const duration =
    recorded?.duration_ms !== null && recorded?.duration_ms !== undefined ? formatDuration(recorded.duration_ms) : null

  return (
    <li className="relative flex gap-3 pb-5 last:pb-0">
      {!isLast ? (
        <span
          className={cn(
            'absolute left-[11px] top-6 h-[calc(100%-1.25rem)] w-px',
            step.status === 'SUCCESS' ? 'bg-success/40' : 'bg-border',
          )}
          aria-hidden
        />
      ) : null}

      <span className="relative z-10 mt-0.5 flex size-[22px] shrink-0 items-center justify-center rounded-full bg-card">
        <Icon className={cn('size-[18px]', STATUS_ICON_CLASS[step.status])} aria-hidden />
      </span>

      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <p
            className={cn(
              'text-sm font-medium',
              step.status === 'PENDING' && 'text-muted-foreground',
              step.status === 'FAILED' && 'text-destructive',
            )}
          >
            {step.label}
          </p>
          <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
            {STATUS_LABEL[step.status]}
          </span>
          {recorded?.started_at ? (
            <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
              {formatApiClock(recorded.started_at)}
              {duration ? ` · ${duration}` : ''}
            </span>
          ) : null}
        </div>

        <p className={cn('text-sm', recorded?.message ? 'text-muted-foreground' : 'text-muted-foreground/70')}>
          {recorded?.message || step.hint}
        </p>

        {chips.length > 0 ? (
          <ul className="flex flex-wrap gap-1 pt-0.5">
            {chips.map((chip) => (
              <li
                key={`${step.key}-${chip.key}`}
                className="rounded-md border border-border bg-muted/50 px-1.5 py-0.5 text-[11px] text-muted-foreground"
              >
                <span className="font-medium text-foreground">{chip.value}</span> {chip.key.replace(/_/g, ' ')}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </li>
  )
}

export interface RunPipelineProps {
  run: AutomationRunRead | null | undefined
  loading?: boolean
  className?: string
}

/** Vertical stepper showing every pipeline stage of one run. */
export function RunPipeline({ run, loading = false, className }: RunPipelineProps) {
  const steps = React.useMemo(() => resolveSteps(run), [run])

  return (
    <Card className={className}>
      <CardHeader className="pb-4">
        <CardTitle>Pipeline</CardTitle>
        <CardDescription>
          {run?.status === 'RUNNING'
            ? 'Live — this refreshes every two seconds.'
            : 'Every stage this run went through, in order.'}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-4">
            {Array.from({ length: 6 }, (_, index) => (
              <div key={index} className="flex gap-3">
                <Skeleton className="size-5 shrink-0 rounded-full" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-3.5 w-32" />
                  <Skeleton className="h-3 w-48" />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <ol className="relative">
            {steps.map((step, index) => (
              <StepRow key={step.key} step={step} isLast={index === steps.length - 1} />
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  )
}
