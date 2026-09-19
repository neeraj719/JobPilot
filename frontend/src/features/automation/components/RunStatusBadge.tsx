import { cn } from '@/lib/utils'
import type { AutomationRunStatus } from '@/types/api'

export const RUN_STATUS_LABELS: Record<AutomationRunStatus, string> = {
  RUNNING: 'Running',
  SUCCESS: 'Succeeded',
  PARTIAL: 'Partial',
  FAILED: 'Failed',
  PAUSED: 'Paused',
  CANCELLED: 'Cancelled',
}

const RUN_STATUS_CLASSES: Record<AutomationRunStatus, string> = {
  RUNNING: 'bg-primary/10 text-primary border-primary/20',
  SUCCESS: 'bg-success/10 text-success border-success/20',
  PARTIAL: 'bg-warning/15 text-warning border-warning/25',
  FAILED: 'bg-destructive/10 text-destructive border-destructive/20',
  PAUSED: 'bg-info/10 text-info border-info/20',
  CANCELLED: 'bg-muted text-muted-foreground border-transparent',
}

export interface RunStatusBadgeProps {
  status: AutomationRunStatus
  className?: string
}

/** Colour-coded pill for an automation run outcome. */
export function RunStatusBadge({ status, className }: RunStatusBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium',
        RUN_STATUS_CLASSES[status] ?? 'bg-muted text-muted-foreground border-transparent',
        className,
      )}
    >
      {status === 'RUNNING' ? (
        <span className="size-1.5 animate-pulse rounded-full bg-current" aria-hidden />
      ) : null}
      {RUN_STATUS_LABELS[status] ?? status}
    </span>
  )
}
