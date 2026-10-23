import { cn, statusColor, statusLabel } from '@/lib/utils'
import type { ApplicationStatus } from '@/types/api'

export interface StatusBadgeProps {
  status: ApplicationStatus | null | undefined
  className?: string
  /** Text shown when `status` is null (a job with no application yet). */
  fallbackLabel?: string
}

/** Colour-coded pill for an `ApplicationStatus`. */
export function StatusBadge({ status, className, fallbackLabel = 'Not applied' }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium',
        statusColor(status),
        className,
      )}
    >
      <span className="size-1.5 shrink-0 rounded-full bg-current opacity-80" aria-hidden />
      {statusLabel(status, fallbackLabel)}
    </span>
  )
}
