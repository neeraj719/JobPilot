import { type LucideIcon, Inbox } from 'lucide-react'
import * as React from 'react'

import { cn } from '@/lib/utils'

export interface EmptyStateProps {
  title: string
  description?: string
  icon?: LucideIcon
  /** Primary call to action, e.g. a `<Button>`. */
  action?: React.ReactNode
  className?: string
  /** `sm` for empty table bodies, `md` for whole pages. */
  size?: 'sm' | 'md'
}

/** The "nothing here yet" panel — every list and page uses this one. */
export function EmptyState({
  title,
  description,
  icon: Icon = Inbox,
  action,
  className,
  size = 'md',
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-surface-2/60 text-center',
        size === 'md' ? 'gap-3 px-6 py-14' : 'gap-2 px-4 py-10',
        className,
      )}
    >
      <span
        className={cn(
          'flex items-center justify-center rounded-full bg-card text-muted-foreground shadow-xs ring-1 ring-border',
          size === 'md' ? 'size-12' : 'size-10',
        )}
      >
        <Icon className={size === 'md' ? 'size-6' : 'size-5'} aria-hidden />
      </span>
      <div className="space-y-1">
        <h3 className={cn('font-semibold', size === 'md' ? 'text-base' : 'text-sm')}>{title}</h3>
        {description ? <p className="mx-auto max-w-md text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {action ? <div className="pt-1">{action}</div> : null}
    </div>
  )
}
