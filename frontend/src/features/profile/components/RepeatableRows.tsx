import { Plus, Trash2 } from 'lucide-react'
import * as React from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export interface RepeatableRowsProps {
  /** Rendered above the rows; omit when the SectionCard heading is enough. */
  label?: string
  description?: React.ReactNode
  emptyLabel: string
  addLabel: string
  onAdd: () => void
  count: number
  className?: string
  children: React.ReactNode
}

/** Shell for a `useFieldArray` group: heading, rows, empty hint and an add button. */
export function RepeatableRows({
  label,
  description,
  emptyLabel,
  addLabel,
  onAdd,
  count,
  className,
  children,
}: RepeatableRowsProps) {
  return (
    <section className={cn('space-y-3', className)}>
      {label ? (
        <div className="space-y-0.5">
          <h3 className="text-sm font-medium">{label}</h3>
          {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
        </div>
      ) : null}

      {count === 0 ? (
        <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
          {emptyLabel}
        </p>
      ) : (
        <div className="space-y-3">{children}</div>
      )}

      <Button type="button" variant="outline" size="sm" onClick={onAdd}>
        <Plus aria-hidden />
        {addLabel}
      </Button>
    </section>
  )
}

export interface RepeatableRowProps {
  title: React.ReactNode
  onRemove: () => void
  removeLabel: string
  className?: string
  children: React.ReactNode
}

/** One removable row inside `RepeatableRows`. */
export function RepeatableRow({ title, onRemove, removeLabel, className, children }: RepeatableRowProps) {
  return (
    <div className={cn('rounded-lg border border-border bg-muted/20 p-3 sm:p-4', className)}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</span>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={onRemove}
          aria-label={removeLabel}
          className="text-muted-foreground hover:text-destructive"
        >
          <Trash2 aria-hidden />
        </Button>
      </div>
      <div className="space-y-4">{children}</div>
    </div>
  )
}
