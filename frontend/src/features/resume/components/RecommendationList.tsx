import { Check, CheckCircle2, ChevronDown, Circle, Copy, ListChecks } from 'lucide-react'
import * as React from 'react'

import { EmptyState } from '@/components/common/EmptyState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { toast } from '@/components/ui/toaster'
import { cn } from '@/lib/utils'
import {
  ACTION_LABELS,
  CATEGORY_LABELS,
  PRIORITY_LABELS,
  groupByPriority,
  useDoneRecommendations,
} from '@/features/resume/recommendations'
import type { Recommendation, RecommendationPriority } from '@/types/api'

const PRIORITY_DOT: Record<RecommendationPriority, string> = {
  HIGH: 'bg-destructive',
  MEDIUM: 'bg-warning',
  LOW: 'bg-muted-foreground/50',
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = React.useState(false)

  React.useEffect(() => {
    if (!copied) return
    const timer = window.setTimeout(() => setCopied(false), 1500)
    return () => window.clearTimeout(timer)
  }, [copied])

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-sm"
      aria-label="Copy suggested text"
      title="Copy suggested text"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text)
          setCopied(true)
        } catch {
          toast.error('Could not copy to the clipboard')
        }
      }}
    >
      {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
    </Button>
  )
}

function RecommendationItem({
  item,
  done,
  onToggleDone,
}: {
  item: Recommendation
  done: boolean
  onToggleDone: () => void
}) {
  const [open, setOpen] = React.useState(false)
  const evidenceId = React.useId()

  return (
    <li className={cn('rounded-md border border-border p-3 transition-opacity', done && 'opacity-60')}>
      <div className="flex items-start gap-3">
        <button
          type="button"
          onClick={onToggleDone}
          className="mt-0.5 shrink-0 rounded-full text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-pressed={done}
          aria-label={done ? `Mark “${item.title}” as not done` : `Mark “${item.title}” as done`}
          title={done ? 'Mark as not done' : 'Mark as done'}
        >
          {done ? <CheckCircle2 className="size-5 text-success" aria-hidden /> : <Circle className="size-5" aria-hidden />}
        </button>
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className={cn('text-sm font-medium', done && 'line-through')}>{item.title}</span>
            <Badge variant="outline">{CATEGORY_LABELS[item.category]}</Badge>
            {item.action ? <Badge variant="muted">{ACTION_LABELS[item.action]}</Badge> : null}
            {item.estimated_score_gain > 0 ? (
              <Badge variant="muted" title="Average match score gain across your target jobs">
                +{item.estimated_score_gain} avg match
              </Badge>
            ) : null}
          </div>
          <p className="text-sm text-muted-foreground">{item.detail}</p>

          {item.suggested_text ? (
            <div className="flex items-start gap-2 rounded-md bg-muted/60 p-2">
              <p className="min-w-0 flex-1 whitespace-pre-line text-sm">{item.suggested_text}</p>
              <CopyButton text={item.suggested_text} />
            </div>
          ) : null}

          {item.evidence.length > 0 ? (
            <div>
              <button
                type="button"
                className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
                aria-expanded={open}
                aria-controls={evidenceId}
                onClick={() => setOpen((value) => !value)}
              >
                <ChevronDown className={cn('size-3.5 transition-transform', open && 'rotate-180')} aria-hidden />
                {open ? 'Hide evidence' : `Why (${item.evidence.length})`}
              </button>
              {open ? (
                <ul id={evidenceId} className="mt-2 space-y-1 text-xs text-muted-foreground">
                  {item.evidence.map((evidence, index) => (
                    <li key={`${evidence.job_id ?? evidence.field ?? ''}-${index}`} className="flex gap-1.5">
                      <span aria-hidden>•</span>
                      <span className="min-w-0 break-words">{evidence.label}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </li>
  )
}

export interface RecommendationListProps {
  resumeId: string
  items: Recommendation[]
}

/** Recommendations grouped by priority, with a local "Mark as done" toggle. */
export function RecommendationList({ resumeId, items }: RecommendationListProps) {
  const { done, toggle } = useDoneRecommendations(resumeId)
  const remaining = items.filter((item) => !done.has(item.id)).length

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Recommendations</CardTitle>
        <CardDescription>
          {items.length === 0
            ? 'Nothing to fix right now.'
            : `${remaining} of ${items.length} still open. Every suggestion comes from your resume and target jobs; only change what is true.`}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <EmptyState
            size="sm"
            icon={ListChecks}
            title="Your resume covers what your target jobs ask for"
            description="Refresh the analysis after new jobs are discovered."
          />
        ) : (
          <div className="space-y-5">
            {groupByPriority(items).map(([priority, group]) => (
              <section key={priority} aria-label={PRIORITY_LABELS[priority]} className="space-y-2">
                <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <span aria-hidden className={cn('size-2 rounded-full', PRIORITY_DOT[priority])} />
                  {PRIORITY_LABELS[priority]}
                  <span className="font-normal tabular-nums">({group.length})</span>
                </h3>
                <ul className="space-y-2">
                  {group.map((item) => (
                    <RecommendationItem
                      key={item.id}
                      item={item}
                      done={done.has(item.id)}
                      onToggleDone={() => toggle(item.id)}
                    />
                  ))}
                </ul>
              </section>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
