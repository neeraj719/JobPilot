import { Ban, Star } from 'lucide-react'

import { PRIORITY_LABELS, cn, priorityColor } from '@/lib/utils'
import type { CompanyPriority } from '@/types/api'

export interface PriorityBadgeProps {
  priority: CompanyPriority | null | undefined
  className?: string
  /** `false` shows just `P1` / `Avoid` instead of the full label. */
  verbose?: boolean
}

/** Company priority pill: P1 (dream), P2 (standard), P3 (low) or AVOID. */
export function PriorityBadge({ priority, className, verbose = false }: PriorityBadgeProps) {
  if (!priority) return null
  const label = verbose ? PRIORITY_LABELS[priority] : priority === 'AVOID' ? 'Avoid' : priority

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium',
        priorityColor(priority),
        className,
      )}
      title={PRIORITY_LABELS[priority]}
    >
      {priority === 'P1' ? <Star className="size-3 fill-current" aria-hidden /> : null}
      {priority === 'AVOID' ? <Ban className="size-3" aria-hidden /> : null}
      {label}
    </span>
  )
}
