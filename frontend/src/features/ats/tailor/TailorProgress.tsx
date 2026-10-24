import { Check, Minus } from 'lucide-react'
import * as React from 'react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'
import type { AtsAnalysis } from '@/features/ats/types'

/** Where the run is: the one request (rules), the background AI pass, the final fetch. */
export type TailorPhase = 'request' | 'ai' | 'final'

type StageState = 'done' | 'active' | 'pending' | 'skipped'

/** `n of m` of the AI pass, from the analysis's tailoring rows (`checks.tailor_pass`). */
export function aiSteps(analysis: AtsAnalysis | undefined): { done: number; total: number } {
  const rows = (analysis?.suggestions ?? []).filter((s) => (s.checks as Record<string, unknown>)?.tailor_pass && s.kind !== 'REORDER_SECTION')
  const done = rows.filter((s) => (s.checks as Record<string, unknown>).tailor_state !== 'pending').length
  return { done, total: rows.length }
}

/** Advances 0 -> 1 -> 2 while the request runs (the server does these three in one call). */
function useRequestStage(active: boolean): number {
  const [stage, setStage] = React.useState(0)
  React.useEffect(() => {
    if (!active) return
    setStage(0)
    const timers = [window.setTimeout(() => setStage(1), 650), window.setTimeout(() => setStage(2), 1400)]
    return () => timers.forEach((t) => window.clearTimeout(t))
  }, [active])
  return stage
}

function Marker({ state }: { state: StageState }) {
  return (
    <span
      className={cn(
        'relative flex size-6 shrink-0 items-center justify-center rounded-full border text-xs',
        state === 'done' && 'border-success bg-success text-success-foreground',
        state === 'active' && 'border-primary bg-primary/10',
        state === 'pending' && 'border-border bg-card',
        state === 'skipped' && 'border-border bg-muted text-muted-foreground',
      )}
      aria-hidden
    >
      {state === 'done' ? <Check className="size-3.5" /> : null}
      {state === 'skipped' ? <Minus className="size-3.5" /> : null}
      {state === 'active' ? <span className="size-2 rounded-full bg-primary motion-safe:animate-pulse" /> : null}
    </span>
  )
}

export interface TailorProgressProps {
  phase: TailorPhase
  /** The tailored copy's first analysis (polled while the AI pass runs). */
  analysis?: AtsAnalysis
  /** `rules_only` once the server said no model answers. */
  aiPass?: 'running' | 'rules_only' | null
  resumeName?: string | null
}

/** The run as a list of stages that follows the server (no spinner). */
export function TailorProgress({ phase, analysis, aiPass, resumeName }: TailorProgressProps) {
  const requestStage = useRequestStage(phase === 'request')
  const steps = aiSteps(analysis)
  const rulesOnly = aiPass === 'rules_only'

  const stageState = (index: number): StageState => {
    if (phase === 'request') return index < requestStage ? 'done' : index === requestStage ? 'active' : 'pending'
    if (index < 3) return 'done'
    if (index === 3) return rulesOnly ? 'skipped' : phase === 'ai' ? 'active' : 'done'
    return phase === 'final' ? 'active' : 'pending'
  }

  const aiLabel = rulesOnly
    ? 'AI rewrite: skipped, no AI model is configured (rules only)'
    : steps.total > 0
      ? `AI rewrite (${Math.min(steps.done + (phase === 'ai' && steps.done < steps.total ? 1 : 0), steps.total)} of ${steps.total})`
      : 'AI rewrite'

  const stages = ['Reading the job description', 'Scoring your resume', 'Applying safe changes', aiLabel, 'Final score']

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle>Optimizing{resumeName ? ` “${resumeName}”` : ''}</CardTitle>
        <CardDescription>
          A tailored copy is being made. Your original stays as it is. The AI step can take a minute with a local model.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ol className="space-y-3" aria-live="polite" role="status">
          {stages.map((label, index) => {
            const state = stageState(index)
            return (
              <li key={index} className="flex items-start gap-3">
                <Marker state={state} />
                <div className="min-w-0 flex-1 space-y-1.5 pt-0.5">
                  <p className={cn('text-sm', state === 'active' ? 'font-medium text-foreground' : state === 'done' ? 'text-foreground' : 'text-muted-foreground')}>
                    {label}
                    <span className="sr-only">{state === 'done' ? ' (done)' : state === 'active' ? ' (in progress)' : state === 'skipped' ? '' : ' (waiting)'}</span>
                  </p>
                  {index === 3 && state === 'active' ? (
                    <Progress value={analysis?.progress ?? 40} aria-label="AI rewrite progress" className="h-1.5" />
                  ) : null}
                </div>
              </li>
            )
          })}
        </ol>
      </CardContent>
    </Card>
  )
}
