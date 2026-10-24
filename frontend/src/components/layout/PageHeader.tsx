import * as React from 'react'

import { cn } from '@/lib/utils'

export interface PageHeaderProps {
  title: string
  description?: React.ReactNode
  /** Buttons / filters rendered on the right. */
  actions?: React.ReactNode
  /**
   * Rendered above the title. A plain string ("Resume") is a section label and shows as a
   * small-caps brand eyebrow; a node (breadcrumb, back link) keeps the quiet muted style.
   */
  eyebrow?: React.ReactNode
  className?: string
  children?: React.ReactNode
}

/** Title block at the top of every page. Pairs with `PageContainer`. */
export function PageHeader({ title, description, actions, eyebrow, className, children }: PageHeaderProps) {
  return (
    <header className={cn('space-y-3', className)}>
      {eyebrow ? (
        typeof eyebrow === 'string' ? (
          <p className="-mb-1 text-2xs font-semibold uppercase tracking-[0.08em] text-primary">{eyebrow}</p>
        ) : (
          <div className="text-sm text-muted-foreground">{eyebrow}</div>
        )
      ) : null}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1.5">
          <h1 className="truncate text-2xl font-heading text-foreground sm:text-3xl">{title}</h1>
          {description ? <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground">{description}</p> : null}
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </header>
  )
}
