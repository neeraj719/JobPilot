import { Bot, Info } from 'lucide-react'

import { ErrorState } from '@/components/common/ErrorState'
import { CompareViewSkeleton } from '@/features/ats/components/AtsSkeletons'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { useCompare } from '@/features/ats/api'
import { formatDelta, scoreTone, TONE_TEXT } from '@/features/ats/labels'
import { WordDiff } from '@/features/ats/components/WordDiff'
import type { CompareSide } from '@/features/ats/types'

type Entry = { title?: string; company?: string; description?: string; name?: string }

function parsed(side: CompareSide) {
  const data = side.parsed_data as { summary?: string; skills?: string[]; experience?: Entry[]; projects?: Entry[] }
  return {
    summary: data.summary ?? '',
    skills: Array.isArray(data.skills) ? data.skills.map(String) : [],
    experience: Array.isArray(data.experience) ? data.experience : [],
    projects: Array.isArray(data.projects) ? data.projects : [],
  }
}

function SideHeader({ side, label }: { side: CompareSide; label: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <div className="min-w-0">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="truncate text-sm font-medium">
          {side.name} <span className="text-muted-foreground">v{side.version}</span>
        </p>
      </div>
      <span className={cn('text-lg font-semibold tabular-nums', TONE_TEXT[scoreTone(side.score)])} title="Estimated ATS compatibility">
        {side.score ?? '—'}
      </span>
    </div>
  )
}

/** Source vs tailored resume, side by side, with every change explained. */
export function CompareView({ targetId }: { targetId: string }) {
  const query = useCompare(targetId)
  if (query.isLoading) return <CompareViewSkeleton />
  if (query.error || !query.data) return <ErrorState error={query.error} onRetry={() => void query.refetch()} size="sm" />
  const { source, tailored, summary, explanations } = query.data
  const a = parsed(source)
  const b = parsed(tailored)
  const added = b.skills.filter((s) => !a.skills.includes(s))
  const delta = source.score !== null && tailored.score !== null ? tailored.score - source.score : null

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant="muted">{summary.added} added</Badge>
        <Badge variant="muted">{summary.changed} changed</Badge>
        <Badge variant="muted">{summary.removed} removed</Badge>
        {delta !== null ? <Badge variant={delta > 0 ? 'success' : 'muted'}>Estimate {formatDelta(delta)}</Badge> : null}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <SideHeader side={source} label="Original" />
        <SideHeader side={tailored} label="Tailored" />
      </div>

      <section className="space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Summary</h4>
        {a.summary === b.summary ? (
          <p className="text-sm text-muted-foreground">Unchanged.</p>
        ) : (
          <WordDiff before={a.summary || null} after={b.summary || null} />
        )}
      </section>

      <section className="space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Skills</h4>
        <div className="grid gap-4 md:grid-cols-2">
          <ul className="flex flex-wrap gap-1.5">
            {a.skills.map((s) => (
              <li key={s} className="rounded-full border border-border px-2 py-0.5 text-xs">
                {s}
              </li>
            ))}
          </ul>
          <ul className="flex flex-wrap gap-1.5">
            {b.skills.map((s) => (
              <li
                key={s}
                className={cn('rounded-full border px-2 py-0.5 text-xs', added.includes(s) ? 'border-success/40 bg-success/15 font-medium' : 'border-border')}
              >
                {added.includes(s) ? '+ ' : ''}
                {s}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="space-y-3">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Experience</h4>
        {b.experience.map((entry, index) => {
          const before = a.experience[index]?.description ?? ''
          const after = entry.description ?? ''
          return (
            <div key={index} className="space-y-1.5 rounded-md border border-border p-3">
              <p className="text-sm font-medium">{[entry.title, entry.company].filter(Boolean).join(' at ') || `Entry ${index + 1}`}</p>
              {before === after ? <p className="text-xs text-muted-foreground">Unchanged.</p> : <WordDiff before={before} after={after} />}
            </div>
          )
        })}
      </section>

      <section className="space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Why each change was made</h4>
        {explanations.length === 0 ? (
          <p className="text-sm text-muted-foreground">No automatic changes were recorded for this tailored resume.</p>
        ) : (
          <ul className="space-y-2">
            {explanations.map((item, index) => (
              <li key={item.suggestion_id ?? index} className="rounded-md border border-border p-3 text-sm">
                <p className="flex items-start gap-2 font-medium">
                  {item.source === 'AI' ? <Bot className="mt-0.5 size-4 shrink-0 text-primary" aria-label="AI suggestion" /> : <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />}
                  <span>{item.what}</span>
                </p>
                <p className="mt-1 text-muted-foreground">{item.why}</p>
                {item.evidence.length ? <p className="mt-1 text-xs text-muted-foreground">Evidence: {item.evidence.join('; ')}</p> : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
