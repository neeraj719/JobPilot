import { ArrowRight, GitCompareArrows } from 'lucide-react'

import { EmptyState } from '@/components/common/EmptyState'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

import type { DiffField, ResumeDiff } from '../types'

function show(value: unknown): string {
  if (value === null || value === undefined || value === '') return ''
  if (Array.isArray(value)) return value.join(', ')
  return String(value)
}

const KIND_STYLE: Record<DiffField['kind'], { label: string; className: string }> = {
  added: { label: 'Added', className: 'border-success/30 bg-success/10 text-success' },
  removed: { label: 'Removed', className: 'border-destructive/30 bg-destructive/10 text-destructive' },
  changed: { label: 'Changed', className: 'border-warning/30 bg-warning/10 text-warning' },
}

function pathLabel(field: DiffField): string {
  if (field.path === 'skills') return 'Skill'
  const bullet = field.path.match(/\.bullets\[(\d+)\]$/)
  if (bullet) return `Bullet ${Number(bullet[1]) + 1}`
  const part = field.path.split('.').pop() ?? field.path
  return part.replace(/\[\d+\]$/, '').replace(/_/g, ' ')
}

/** Side-by-side field diff: before on the left, after on the right, kinds colour-coded. */
export function DiffView({ diff, className }: { diff: ResumeDiff; className?: string }) {
  if (!diff.fields.length) {
    return <EmptyState size="sm" icon={GitCompareArrows} title="No content changes" description="These two are identical." />
  }
  const groups = new Map<string, DiffField[]>()
  for (const field of diff.fields) {
    const key = field.label ?? 'Resume'
    groups.set(key, [...(groups.get(key) ?? []), field])
  }
  return (
    <div className={cn('space-y-4', className)}>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">{diff.before_label ?? 'Before'}</span>
        <ArrowRight className="size-4 text-muted-foreground" aria-hidden />
        <span className="font-medium">{diff.after_label ?? 'After'}</span>
        <span className="text-muted-foreground">· {diff.description}</span>
      </div>
      <div className="hidden grid-cols-2 gap-3 px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground sm:grid">
        <span>{diff.before_label ?? 'Before'}</span>
        <span>{diff.after_label ?? 'After'}</span>
      </div>
      {[...groups.entries()].map(([group, fields]) => (
        <section key={group} className="space-y-2">
          <h4 className="text-sm font-semibold">{group}</h4>
          <ul className="space-y-2">
            {fields.map((field, index) => {
              const kind = KIND_STYLE[field.kind]
              return (
                <li key={`${field.path}-${index}`} className="rounded-md border border-border p-2">
                  <div className="mb-1.5 flex items-center gap-2">
                    <Badge variant="outline" className={cn('text-[11px]', kind.className)}>
                      {kind.label}
                    </Badge>
                    <span className="text-xs capitalize text-muted-foreground">{pathLabel(field)}</span>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <p
                      className={cn(
                        'min-h-[1.5rem] whitespace-pre-wrap rounded px-2 py-1 text-sm',
                        show(field.before) ? 'bg-destructive/5 line-through decoration-destructive/40' : 'italic text-muted-foreground',
                      )}
                    >
                      <span className="sr-only">Before: </span>
                      {show(field.before) || '—'}
                    </p>
                    <p
                      className={cn(
                        'min-h-[1.5rem] whitespace-pre-wrap rounded px-2 py-1 text-sm',
                        show(field.after) ? 'bg-success/10' : 'italic text-muted-foreground',
                      )}
                    >
                      <span className="sr-only">After: </span>
                      {show(field.after) || '—'}
                    </p>
                  </div>
                </li>
              )
            })}
          </ul>
        </section>
      ))}
    </div>
  )
}
