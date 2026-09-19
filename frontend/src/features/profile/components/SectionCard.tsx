import { Check } from 'lucide-react'
import * as React from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

export interface SectionCardProps {
  title: string
  description?: React.ReactNode
  /** Rendered next to the title (e.g. an "Import from resume" button). */
  headerAction?: React.ReactNode
  isDirty: boolean
  isSaving: boolean
  onReset?: () => void
  saveLabel?: string
  children: React.ReactNode
  /** Wired to the surrounding `<form id=...>` so the footer button submits it. */
  formId: string
  className?: string
}

/**
 * One saveable profile section: header, body and a footer that only becomes actionable
 * once the section is dirty. Every section owns its own form, so a failed save never
 * blocks the others.
 */
export function SectionCard({
  title,
  description,
  headerAction,
  isDirty,
  isSaving,
  onReset,
  saveLabel = 'Save',
  children,
  formId,
  className,
}: SectionCardProps) {
  return (
    <Card className={cn('overflow-hidden', className)}>
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <CardTitle className="flex items-center gap-2 text-base">
            {title}
            {isDirty ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-warning/15 px-2 py-0.5 text-[11px] font-medium text-warning">
                Unsaved changes
              </span>
            ) : null}
          </CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </div>
        {headerAction ? <div className="shrink-0">{headerAction}</div> : null}
      </CardHeader>
      <CardContent className="space-y-6">{children}</CardContent>
      <CardFooter className="flex flex-wrap items-center justify-end gap-2 border-t bg-muted/30 py-3">
        {!isDirty && !isSaving ? (
          <span className="mr-auto inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            <Check className="size-3.5 text-success" aria-hidden />
            Saved
          </span>
        ) : null}
        {onReset ? (
          <Button type="button" variant="ghost" size="sm" onClick={onReset} disabled={!isDirty || isSaving}>
            Discard
          </Button>
        ) : null}
        <Button type="submit" form={formId} size="sm" loading={isSaving} disabled={!isDirty}>
          {saveLabel}
        </Button>
      </CardFooter>
    </Card>
  )
}

export interface FieldProps {
  label: string
  htmlFor?: string
  hint?: React.ReactNode
  error?: string
  className?: string
  children: React.ReactNode
}

/** Label + control + hint/error, used by every hand-rolled field in the profile form. */
export function Field({ label, htmlFor, hint, error, className, children }: FieldProps) {
  return (
    <div className={cn('space-y-1.5', className)}>
      <Label htmlFor={htmlFor} className={cn(error && 'text-destructive')}>
        {label}
      </Label>
      {children}
      {error ? (
        <p className="text-xs font-medium text-destructive">{error}</p>
      ) : hint ? (
        <p className="text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  )
}

/** Responsive two/three column grid used inside sections. */
export function FieldGrid({ cols = 2, className, children }: { cols?: 2 | 3; className?: string; children: React.ReactNode }) {
  return (
    <div className={cn('grid gap-4', cols === 3 ? 'sm:grid-cols-2 lg:grid-cols-3' : 'sm:grid-cols-2', className)}>
      {children}
    </div>
  )
}
