/**
 * The 13 pipeline steps, in the order `backend/app/modules/automation/pipeline.py`
 * records them. The stepper renders this list even before a run reports a step, so an
 * in-flight run shows the work still ahead of it as PENDING.
 */
import type { AutomationRunRead, AutomationRunStep, AutomationStepStatus } from '@/types/api'

export interface StepDefinition {
  /** Matches `AutomationRunStep.step`. */
  key: string
  label: string
  hint: string
}

export const PIPELINE_STEPS: StepDefinition[] = [
  { key: 'search', label: 'Search', hint: 'Pick the platforms to query for your target titles' },
  { key: 'collect', label: 'Collect', hint: 'Pull listings from every enabled source' },
  { key: 'dedupe', label: 'Deduplicate', hint: 'Merge the same posting found on several platforms' },
  { key: 'analyze', label: 'Analyse', hint: 'Score each new job against your resume' },
  { key: 'filter', label: 'Filter', hint: 'Drop anything below your rules' },
  { key: 'prioritize', label: 'Prioritise', hint: 'Dream companies and the strongest matches first' },
  { key: 'enforce_limits', label: 'Enforce limits', hint: 'Respect the daily and per-platform budget' },
  { key: 'queue', label: 'Queue', hint: 'Create an application for each survivor' },
  { key: 'generate_answers', label: 'Generate answers', hint: 'Answer the form from your profile and resume' },
  { key: 'autofill', label: 'Autofill', hint: 'Fill the real form in the browser' },
  { key: 'approval_queue', label: 'Approval queue', hint: 'Park anything that needs a human' },
  { key: 'auto_submit', label: 'Auto-submit', hint: 'Submit only what you allowed to go automatically' },
  { key: 'finish', label: 'Finish', hint: 'Write the summary and notify you' },
]

const STEP_LABELS: Record<string, string> = Object.fromEntries(
  PIPELINE_STEPS.map((step) => [step.key, step.label]),
)

/** `generate_answers` -> `Generate answers`, for steps the backend adds later. */
export function stepLabel(key: string | null | undefined): string {
  if (!key) return '—'
  const known = STEP_LABELS[key]
  if (known) return known
  const spaced = key.replace(/_/g, ' ')
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

export interface ResolvedStep extends StepDefinition {
  status: AutomationStepStatus
  recorded: AutomationRunStep | null
}

/**
 * Merge the run's recorded steps onto the canonical list.
 *
 * Steps the run never reached are PENDING; the one named by `current_step` on a
 * RUNNING run is RUNNING; anything the backend recorded that we do not know about is
 * appended so a future pipeline step is never hidden.
 */
export function resolveSteps(run: AutomationRunRead | null | undefined): ResolvedStep[] {
  if (!run) return PIPELINE_STEPS.map((step) => ({ ...step, status: 'PENDING', recorded: null }))

  const byKey = new Map<string, AutomationRunStep>()
  for (const recorded of run.steps ?? []) byKey.set(recorded.step, recorded)

  const isLive = run.status === 'RUNNING'
  const resolved: ResolvedStep[] = PIPELINE_STEPS.map((step) => {
    const recorded = byKey.get(step.key) ?? null
    byKey.delete(step.key)
    let status: AutomationStepStatus = recorded?.status ?? 'PENDING'
    if (isLive && run.current_step === step.key && !recorded?.finished_at) status = 'RUNNING'
    return { ...step, status, recorded }
  })

  for (const [key, recorded] of byKey) {
    resolved.push({
      key,
      label: stepLabel(key),
      hint: '',
      status: recorded.status ?? 'SUCCESS',
      recorded,
    })
  }

  return resolved
}

/** The step that broke a FAILED/PARTIAL run, if one was recorded. */
export function failedStep(run: AutomationRunRead | null | undefined): AutomationRunStep | null {
  return (run?.steps ?? []).find((step) => step.status === 'FAILED') ?? null
}

/** How far through the pipeline a run is, as a 0–100 percentage. */
export function runProgress(run: AutomationRunRead | null | undefined): number {
  if (!run) return 0
  if (run.status !== 'RUNNING') return 100
  const done = (run.steps ?? []).filter((step) => step.status !== 'RUNNING').length
  return Math.min(100, Math.round((done / PIPELINE_STEPS.length) * 100))
}
