import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { APPLICATION_STATUS_LABELS, cn, statusColor } from '@/lib/utils'
import { APPLICATION_STATUSES, type ApplicationStatus } from '@/types/api'

export interface ApplicationStatusSelectProps {
  value: ApplicationStatus
  onChange: (status: ApplicationStatus) => void
  disabled?: boolean
  className?: string
  'aria-label'?: string
}

/**
 * Inline status picker used in the applications table and the detail actions menu.
 * It is colour-matched to `StatusBadge` so a row still reads at a glance.
 */
export function ApplicationStatusSelect({
  value,
  onChange,
  disabled = false,
  className,
  'aria-label': ariaLabel = 'Change application status',
}: ApplicationStatusSelectProps) {
  return (
    <Select value={value} onValueChange={(next) => onChange(next as ApplicationStatus)} disabled={disabled}>
      <SelectTrigger
        aria-label={ariaLabel}
        className={cn('h-7 w-auto min-w-36 rounded-full border px-2.5 text-xs font-medium', statusColor(value), className)}
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {APPLICATION_STATUSES.map((status) => (
          <SelectItem key={status} value={status}>
            {APPLICATION_STATUS_LABELS[status]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
