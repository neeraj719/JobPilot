import { Sparkles } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { formatDate, humanizeEnum } from '@/lib/utils'
import type { SnapshotRead, StructuredJD } from '@/features/ats/types'

function Chips({ items, tone, highlight }: { items: string[]; tone: 'required' | 'preferred'; highlight?: Set<string> }) {
  if (items.length === 0) return <p className="text-sm text-muted-foreground">None stated</p>
  return (
    <ul className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <li
          key={item}
          className={
            tone === 'required'
              ? 'rounded-full border border-primary/30 bg-primary/10 px-2.5 py-0.5 text-xs font-medium'
              : 'rounded-full border border-border bg-muted px-2.5 py-0.5 text-xs font-medium'
          }
        >
          {item}
          {highlight?.has(item.toLowerCase()) ? <span className="ml-1 text-[10px] font-semibold uppercase text-warning">new</span> : null}
        </li>
      ))}
    </ul>
  )
}

/** What a job description asks for, as JobPilot read it. */
export function StructuredJdView({ structured, changes }: { structured: StructuredJD; changes?: SnapshotRead['changes'] }) {
  const added = new Set([...(changes?.added_required ?? []), ...(changes?.added_preferred ?? [])].map((s) => s.toLowerCase()))
  const removed = [...(changes?.removed_required ?? []), ...(changes?.removed_preferred ?? [])]
  const years =
    structured.years_min !== null
      ? structured.years_max !== null
        ? `${structured.years_min}–${structured.years_max} years`
        : `${structured.years_min}+ years`
      : null
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 text-xs">
        {structured.seniority ? <Badge variant="outline">{humanizeEnum(structured.seniority)}</Badge> : null}
        {years ? <Badge variant="outline">{years}</Badge> : null}
        {structured.work_mode ? <Badge variant="outline">{humanizeEnum(structured.work_mode)}</Badge> : null}
        {structured.location ? <Badge variant="outline">{structured.location}</Badge> : null}
        {structured.degree_required ? <Badge variant="outline">Degree required</Badge> : null}
        {structured.deadline ? <Badge variant="warning">Apply by {formatDate(structured.deadline)}</Badge> : null}
        {structured.ai_polished ? (
          <Badge variant="secondary" title="Classification refined by the AI model; every item still appears in the posting">
            <Sparkles aria-hidden />
            AI-refined
          </Badge>
        ) : null}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <section className="space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Required skills</h4>
          <Chips items={structured.required_skills} tone="required" highlight={added} />
        </section>
        <section className="space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Nice to have</h4>
          <Chips items={structured.preferred_skills} tone="preferred" highlight={added} />
        </section>
      </div>
      {removed.length ? (
        <p className="text-xs text-muted-foreground">
          No longer asked for: <span className="line-through">{removed.join(', ')}</span>
        </p>
      ) : null}
      {structured.qualifications.length ? (
        <section className="space-y-1.5">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Requirements</h4>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {structured.qualifications.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </section>
      ) : null}
      {structured.responsibilities.length ? (
        <section className="space-y-1.5">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Responsibilities</h4>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {structured.responsibilities.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </section>
      ) : null}
      {structured.notes.length ? (
        <ul className="space-y-0.5 text-xs text-muted-foreground">
          {structured.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
