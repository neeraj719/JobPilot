import { ArrowRight, Check, Info } from 'lucide-react'
import * as React from 'react'

import { SkeletonLine, SkeletonRegion } from '@/components/common/skeletons'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { toast } from '@/components/ui/toaster'
import { errorMessage } from '@/lib/api'
import { cn } from '@/lib/utils'

import { useApplyLinkedIn } from '../api'
import type { LinkedInApplyResult, LinkedInDiffGroup, LinkedInDiffRow, LinkedInSyncResult, LinkedInValue } from '../types'

const GROUPS: { id: LinkedInDiffGroup; title: string }[] = [
  { id: 'basics', title: 'Basics' },
  { id: 'experience', title: 'Experience' },
  { id: 'education', title: 'Education' },
  { id: 'skills', title: 'Skills' },
  { id: 'certifications', title: 'Certifications' },
  { id: 'languages', title: 'Languages' },
]

function str(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function dates(item: Record<string, unknown>): string {
  const start = str(item.start)
  const end = str(item.end)
  if (!start && !end) return ''
  return `${start || '?'} – ${end || '?'}`
}

/** One readable line for a profile value (string, or an experience / education / certification entry). */
export function describeValue(value: LinkedInValue): string {
  if (value == null) return '—'
  if (typeof value === 'string') return value
  const item = value as Record<string, unknown>
  if (str(item.company) || str(item.title) || str(item.designation)) {
    return [str(item.title) || str(item.designation), str(item.company), dates(item)].filter(Boolean).join(' · ')
  }
  if (str(item.institution) || str(item.school)) {
    return [str(item.degree), str(item.field), str(item.institution) || str(item.school), dates(item)].filter(Boolean).join(' · ')
  }
  if (str(item.name)) return [str(item.name), str(item.issuer), str(item.year)].filter(Boolean).join(' · ')
  return Object.values(item).map(str).filter(Boolean).join(' · ') || '—'
}

function DiffRowItem({ row, checked, onCheckedChange }: { row: LinkedInDiffRow; checked: boolean; onCheckedChange: (next: boolean) => void }) {
  const id = `li-row-${row.id.replace(/[^a-zA-Z0-9_-]/g, '_')}`
  const description = row.incoming && typeof row.incoming === 'object' ? str((row.incoming as Record<string, unknown>).description) : ''
  return (
    <li className={cn('flex gap-3 rounded-lg border p-3 transition-colors', checked ? 'border-primary/40 bg-primary/5' : 'border-border')}>
      <Checkbox id={id} checked={checked} onCheckedChange={(next) => onCheckedChange(next === true)} className="mt-0.5" />
      <label htmlFor={id} className="min-w-0 flex-1 cursor-pointer space-y-1">
        <span className="flex flex-wrap items-center gap-2 text-xs font-medium text-muted-foreground">
          {row.label}
          {row.action === 'add' ? <Badge variant="success">New</Badge> : <Badge variant="warning">Differs from your profile</Badge>}
        </span>
        <span className="block break-words text-sm font-medium text-foreground">{describeValue(row.incoming)}</span>
        {description ? <span className="line-clamp-2 block text-xs text-muted-foreground">{description}</span> : null}
        {row.action === 'replace' ? (
          <span className="block break-words text-xs text-muted-foreground">
            Your profile now: <span className="text-foreground">{describeValue(row.current)}</span>
          </span>
        ) : null}
      </label>
    </li>
  )
}

export interface LinkedInReviewDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  result: LinkedInSyncResult | null | undefined
  loading?: boolean
  onApplied?: (result: LinkedInApplyResult) => void
}

/**
 * Review changes: LinkedIn (incoming) vs the profile (current). Additions are ticked, conflicts
 * are not; only ticked rows are written, and the server recomputes them (the client only sends ids).
 */
export function LinkedInReviewDialog({ open, onOpenChange, result, loading = false, onApplied }: LinkedInReviewDialogProps) {
  const apply = useApplyLinkedIn()
  const rows = React.useMemo(() => (result?.diff.rows ?? []).filter((row) => row.action !== 'same'), [result])
  const same = result?.diff.same ?? 0
  const [selected, setSelected] = React.useState<Set<string>>(new Set())

  React.useEffect(() => {
    if (open) setSelected(new Set(rows.filter((row) => row.default_selected).map((row) => row.id)))
  }, [open, rows])

  const toggle = (id: string, next: boolean) =>
    setSelected((prev) => {
      const copy = new Set(prev)
      if (next) copy.add(id)
      else copy.delete(id)
      return copy
    })

  const setGroup = (group: LinkedInDiffGroup, next: boolean) =>
    setSelected((prev) => {
      const copy = new Set(prev)
      for (const row of rows) if (row.group === group) (next ? copy.add(row.id) : copy.delete(row.id))
      return copy
    })

  const handleApply = async () => {
    try {
      const applied = await apply.mutateAsync([...selected])
      toast.success('Profile updated', {
        description: `${applied.applied} ${applied.applied === 1 ? 'change' : 'changes'} from LinkedIn applied. You can create your resume now.`,
      })
      onApplied?.(applied)
      onOpenChange(false)
    } catch (error) {
      toast.error('Could not apply the changes', { description: errorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (apply.isPending ? undefined : onOpenChange(next))}>
      <DialogContent className="flex max-h-[90vh] max-w-2xl flex-col gap-0 p-0">
        <DialogHeader className="border-b border-border p-5 pr-12 sm:p-6 sm:pr-12">
          <DialogTitle>Review changes from LinkedIn</DialogTitle>
          <DialogDescription>
            Tick what should go into your profile. New details are ticked; anything that differs from what you already have is left
            unticked so you decide.
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-5 sm:p-6">
          {loading || !result ? (
            <SkeletonRegion label="Reading LinkedIn" className="space-y-3">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="flex gap-3 rounded-lg border border-border p-3">
                  <Skeleton className="mt-0.5 size-4 shrink-0 rounded-[4px]" />
                  <div className="min-w-0 flex-1">
                    <SkeletonLine size="xs" className="w-24" />
                    <SkeletonLine size="sm" className="w-3/4" />
                  </div>
                </div>
              ))}
            </SkeletonRegion>
          ) : (
            <>
              {result.notes.map((note) => (
                <Alert key={note} variant="info">
                  <Info aria-hidden />
                  <AlertDescription>{note}</AlertDescription>
                </Alert>
              ))}
              {rows.length === 0 ? (
                <p className="flex items-center gap-2 rounded-lg border border-border bg-surface-2 p-4 text-sm">
                  <Check className="size-4 text-success" aria-hidden />
                  Your profile already matches everything LinkedIn shared.
                </p>
              ) : (
                GROUPS.map(({ id, title }) => {
                  const groupRows = rows.filter((row) => row.group === id)
                  if (!groupRows.length) return null
                  const allOn = groupRows.every((row) => selected.has(row.id))
                  return (
                    <section key={id} aria-label={title} className="space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <h3 className="text-sm font-semibold">
                          {title} <span className="font-normal text-muted-foreground">({groupRows.length})</span>
                        </h3>
                        {groupRows.length > 1 ? (
                          <Button type="button" variant="ghost" size="sm" onClick={() => setGroup(id, !allOn)}>
                            {allOn ? 'Untick all' : 'Tick all'}
                          </Button>
                        ) : null}
                      </div>
                      <ul className="space-y-2">
                        {groupRows.map((row) => (
                          <DiffRowItem key={row.id} row={row} checked={selected.has(row.id)} onCheckedChange={(next) => toggle(row.id, next)} />
                        ))}
                      </ul>
                    </section>
                  )
                })
              )}
              {same > 0 ? (
                <p className="text-xs text-muted-foreground">
                  {same} {same === 1 ? 'detail already matches' : 'details already match'} your profile and {same === 1 ? 'is' : 'are'} not listed.
                </p>
              ) : null}
            </>
          )}
        </div>

        <DialogFooter className="border-t border-border p-4 sm:p-5">
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)} disabled={apply.isPending}>
            {rows.length ? 'Not now' : 'Close'}
          </Button>
          {rows.length ? (
            <Button type="button" onClick={() => void handleApply()} loading={apply.isPending} disabled={selected.size === 0 || loading}>
              Apply {selected.size} {selected.size === 1 ? 'change' : 'changes'} <ArrowRight aria-hidden />
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
