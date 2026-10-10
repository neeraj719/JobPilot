import { CheckCircle2, HelpCircle, PauseCircle } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { ReviewCounts } from '@/features/applications/api'

interface Chip {
  key: keyof ReviewCounts
  label: string
  icon: LucideIcon
  className: string
}

const CHIPS: Chip[] = [
  { key: 'pending_review', label: 'Pending review', icon: PauseCircle, className: 'bg-info/10 text-info border-info/20' },
  {
    key: 'requires_input',
    label: 'Need your input',
    icon: HelpCircle,
    className: 'bg-warning/15 text-warning border-warning/25',
  },
  {
    key: 'ready_to_submit',
    label: 'Ready to submit',
    icon: CheckCircle2,
    className: 'bg-success/10 text-success border-success/20',
  },
]

export interface QueueSummaryProps {
  counts: ReviewCounts | undefined
  loading?: boolean
  className?: string
}

/** The three Approval Center counters shown above the queue table. */
export function QueueSummary({ counts, loading = false, className }: QueueSummaryProps) {
  if (loading && !counts) {
    return (
      <div className={cn('flex flex-wrap gap-2', className)}>
        {CHIPS.map((chip) => (
          <Skeleton key={chip.key} className="h-9 w-40 rounded-full" />
        ))}
      </div>
    )
  }

  return (
    <div className={cn('flex flex-wrap gap-2', className)}>
      {CHIPS.map((chip) => {
        const Icon = chip.icon
        const value = counts?.[chip.key] ?? 0
        return (
          <span
            key={chip.key}
            className={cn(
              'inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-medium',
              value > 0 ? chip.className : 'border-border bg-muted/50 text-muted-foreground',
            )}
          >
            <Icon className="size-4" aria-hidden />
            <span className="tabular-nums">{value}</span>
            <span className="font-normal">{chip.label}</span>
          </span>
        )
      })}
    </div>
  )
}
