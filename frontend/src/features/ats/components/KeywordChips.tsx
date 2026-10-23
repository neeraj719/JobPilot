import { Check, Plus } from 'lucide-react'

import { SimpleTooltip } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { KeywordHit, KeywordMiss } from '@/features/ats/types'

const KIND_LABEL = { skill: 'skill', keyword: 'term', title: 'job title' } as const

/** Matched keywords (green) and missing ones, with where a missing one could fit. */
export function KeywordChips({ matched, missing }: { matched: KeywordHit[]; missing: KeywordMiss[] }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <section aria-label="Matched keywords" className="space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Matched ({matched.length})</h4>
        {matched.length === 0 ? <p className="text-sm text-muted-foreground">None of the posting's keywords were found.</p> : null}
        <ul className="flex flex-wrap gap-1.5">
          {matched.map((hit) => (
            <li key={`${hit.kind}:${hit.keyword}`}>
              <SimpleTooltip label={`Found in: ${hit.where.join(', ') || 'resume'}`} side="top">
                <span
                  tabIndex={0}
                  className="inline-flex items-center gap-1 rounded-full border border-success/30 bg-success/10 px-2.5 py-0.5 text-xs font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <Check className="size-3 text-success" aria-hidden />
                  {hit.keyword}
                  {hit.required ? <span className="text-[10px] uppercase text-muted-foreground">req</span> : null}
                </span>
              </SimpleTooltip>
            </li>
          ))}
        </ul>
      </section>
      <section aria-label="Missing keywords" className="space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Missing ({missing.length})</h4>
        {missing.length === 0 ? <p className="text-sm text-muted-foreground">Every keyword of the posting is on your resume.</p> : null}
        <ul className="space-y-1.5">
          {missing.map((miss) => (
            <li key={`${miss.kind}:${miss.keyword}`} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-sm">
              <span
                className={cn(
                  'inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium',
                  miss.required ? 'border-destructive/40 bg-destructive/10' : 'border-border bg-muted',
                )}
              >
                <Plus className="size-3 text-muted-foreground" aria-hidden />
                {miss.keyword}
                <span className="text-[10px] uppercase text-muted-foreground">
                  {miss.required ? 'required' : miss.required === false ? 'nice to have' : KIND_LABEL[miss.kind]}
                </span>
              </span>
              {miss.where_it_fits ? (
                <span className={cn('text-xs', miss.evidenced ? 'text-foreground' : 'text-muted-foreground')}>
                  {miss.evidenced ? 'Fits: ' : 'Could fit: '}
                  {miss.where_it_fits}
                </span>
              ) : (
                <span className="text-xs text-muted-foreground">Nothing on your resume shows it — add only if true</span>
              )}
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
