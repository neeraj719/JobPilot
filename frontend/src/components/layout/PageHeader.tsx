import * as React from 'react'

import { cn } from '@/lib/utils'

export interface PageHeaderProps {
  title: string
  description?: React.ReactNode
  /** Buttons / filters rendered on the right. */
  actions?: React.ReactNode
  /** Breadcrumbs or a back link rendered above the title. */
  eyebrow?: React.ReactNode
  className?: string
  children?: React.ReactNode
}

/** Title block at the top of every page. Pairs with `PageContainer`. */
export function PageHeader({ title, description, actions, eyebrow, className, children }: PageHeaderProps) {
  return (
    <header className={cn('space-y-3', className)}>
      {eyebrow ? <div className="text-sm text-muted-foreground">{eyebrow}</div> : null}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <h1 className="truncate text-2xl font-semibold tracking-tight">{title}</h1>
          {description ? <p className="max-w-3xl text-sm text-muted-foreground">{description}</p> : null}
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </header>
  )
}
