import { Check, CircleAlert, Info, Sparkles, X } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { cn } from '@/lib/utils'

import type { BulletCandidate, BulletChecks } from '../../types'

const CHECK_LABELS: Record<keyof BulletChecks, string> = {
  kept_details: 'Keeps your details',
  no_new_numbers: 'No new numbers',
  no_new_claims: 'No new skills or claims',
}

export interface SuggestionPanelProps {
  title: string
  original: string
  loading: boolean
  error?: string | null
  candidates: BulletCandidate[]
  note?: string | null
  onApply: (text: string, candidate: BulletCandidate) => void
  onClose: () => void
  onRetry?: () => void
}

/**
 * Original on the left, AI/rule suggestions on the right, each with the fact checks it
 * passed. "Apply" only edits the local draft; saving a version is a separate step.
 */
export function SuggestionPanel({ title, original, loading, error, candidates, note, onApply, onClose, onRetry }: SuggestionPanelProps) {
  return (
    <div className="mt-2 rounded-lg border border-ai/25 bg-ai-soft/60 p-3" role="region" aria-label={title} aria-busy={loading}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-sm font-medium">
          <Sparkles className="size-4 text-ai" aria-hidden />
          {title}
        </p>
        <Button type="button" variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close suggestions">
          <X aria-hidden />
        </Button>
      </div>
      <div className="grid gap-3 2xl:grid-cols-2">
        <div>
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Your text</p>
          <p className="rounded-md border border-border bg-card p-2 text-sm">{original}</p>
        </div>
        <div>
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Suggestions</p>
          {loading ? (
            <div className="flex items-center gap-2 rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground">
              <Spinner size="sm" /> Checking against your resume facts…
            </div>
          ) : error ? (
            <div className="space-y-2 rounded-md border border-destructive/30 bg-destructive/5 p-2 text-sm text-destructive">
              <p className="flex items-center gap-1.5">
                <CircleAlert className="size-4" aria-hidden /> {error}
              </p>
              {onRetry ? (
                <Button type="button" size="sm" variant="outline" onClick={onRetry}>
                  Try again
                </Button>
              ) : null}
            </div>
          ) : candidates.length === 0 ? (
            <p className="rounded-md border border-dashed border-border p-2 text-sm text-muted-foreground">
              {note ?? 'No safe suggestion for this text.'}
            </p>
          ) : (
            <ul className="space-y-2">
              {candidates.map((candidate, index) => (
                <li key={index} className="rounded-md border border-border bg-card p-2">
                  <p className="text-sm">
                    {candidate.text.split(/(\[[^\]]*\])/).map((part, i) =>
                      /^\[[^\]]*\]$/.test(part) ? (
                        <mark key={i} className="rounded bg-warning/25 px-0.5 text-foreground">
                          {part}
                        </mark>
                      ) : (
                        <span key={i}>{part}</span>
                      ),
                    )}
                  </p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1">
                    <Badge variant="outline" className="text-[10px]">
                      {candidate.source === 'ai' ? 'AI, checked' : 'Rule-based'}
                    </Badge>
                    {(Object.keys(CHECK_LABELS) as (keyof BulletChecks)[]).map((key) => (
                      <span
                        key={key}
                        className={cn(
                          'inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[10px]',
                          candidate.checks[key] ? 'bg-success/10 text-success' : 'bg-warning/15 text-warning',
                        )}
                      >
                        {candidate.checks[key] ? <Check className="size-3" aria-hidden /> : <CircleAlert className="size-3" aria-hidden />}
                        {candidate.checks[key] ? CHECK_LABELS[key] : key === 'kept_details' ? 'Drops some details' : CHECK_LABELS[key]}
                      </span>
                    ))}
                  </div>
                  <div className="mt-2 flex gap-2">
                    <Button type="button" size="sm" onClick={() => onApply(candidate.text, candidate)}>
                      Apply
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {note && candidates.length > 0 ? (
            <p className="mt-2 flex items-start gap-1.5 text-xs text-muted-foreground">
              <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              {note}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  )
}
