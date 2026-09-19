/** Shared interview helpers: status colours, splitting upcoming vs past, prep sections. */
import { cn } from '@/lib/utils'
import { parseApiDate } from '@/features/automation/datetime'
import type { InterviewPrep, InterviewRead, InterviewStatus } from '@/types/api'

export const INTERVIEW_STATUS_LABELS: Record<InterviewStatus, string> = {
  SCHEDULED: 'Scheduled',
  COMPLETED: 'Completed',
  CANCELLED: 'Cancelled',
  RESCHEDULED: 'Rescheduled',
}

export function interviewStatusColor(status: InterviewStatus): string {
  switch (status) {
    case 'SCHEDULED':
      return 'bg-primary/10 text-primary border-primary/20'
    case 'COMPLETED':
      return 'bg-success/10 text-success border-success/20'
    case 'CANCELLED':
      return 'bg-muted text-muted-foreground border-transparent'
    case 'RESCHEDULED':
      return 'bg-warning/15 text-warning border-warning/25'
    default:
      return 'bg-muted text-muted-foreground border-transparent'
  }
}

/** Outcomes the "mark completed" flow offers. */
export const INTERVIEW_OUTCOMES = [
  { value: 'PASSED', label: 'Passed — moving to the next round' },
  { value: 'FAILED', label: 'Did not pass' },
  { value: 'PENDING', label: 'Waiting to hear back' },
  { value: 'NO_SHOW', label: 'Did not happen' },
] as const

export function outcomeLabel(outcome: string | null | undefined): string | null {
  if (!outcome) return null
  const known = INTERVIEW_OUTCOMES.find((entry) => entry.value === outcome)
  if (known) return known.label
  const spaced = outcome.replace(/_/g, ' ').toLowerCase()
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

/**
 * Mirrors the backend's `upcoming` rule: still scheduled (or rescheduled) and not yet
 * in the past. Interviews without a date count as upcoming so they are never lost.
 */
export function isUpcoming(interview: InterviewRead, now = Date.now()): boolean {
  if (interview.status !== 'SCHEDULED' && interview.status !== 'RESCHEDULED') return false
  const date = parseApiDate(interview.scheduled_at)
  return date ? date.getTime() >= now : true
}

export interface SplitInterviews {
  upcoming: InterviewRead[]
  past: InterviewRead[]
}

/** Upcoming soonest-first, past most-recent-first. */
export function splitInterviews(interviews: InterviewRead[] | undefined): SplitInterviews {
  const now = Date.now()
  const upcoming: InterviewRead[] = []
  const past: InterviewRead[] = []

  for (const interview of interviews ?? []) {
    ;(isUpcoming(interview, now) ? upcoming : past).push(interview)
  }

  const time = (interview: InterviewRead) => parseApiDate(interview.scheduled_at)?.getTime() ?? 0
  upcoming.sort((a, b) => (time(a) || Number.MAX_SAFE_INTEGER) - (time(b) || Number.MAX_SAFE_INTEGER))
  past.sort((a, b) => time(b) - time(a))

  return { upcoming, past }
}

export interface PrepSection {
  key: keyof Omit<InterviewPrep, 'generated_at'>
  title: string
  description: string
  questions: string[]
}

const PREP_SECTION_META: { key: PrepSection['key']; title: string; description: string }[] = [
  { key: 'technical', title: 'Likely technical questions', description: 'Drawn from the stack this role names.' },
  { key: 'behavioral', title: 'Behavioral questions', description: 'Have a story ready for each one.' },
  {
    key: 'company_specific',
    title: 'Company-specific preparation',
    description: 'What they will expect you to know about them.',
  },
  { key: 'job_specific', title: 'Job-specific preparation', description: 'Straight from the job description.' },
  {
    key: 'resume_based',
    title: 'Questions based on your resume',
    description: 'Anything on your resume is fair game.',
  },
]

/** True when the interview has a generated preparation sheet. */
export function hasPrep(interview: InterviewRead | null | undefined): boolean {
  const material = interview?.prep_material as InterviewPrep | undefined
  if (!material) return false
  return PREP_SECTION_META.some((section) => (material[section.key]?.length ?? 0) > 0)
}

/** The five prep sections, empty ones dropped. */
export function prepSections(interview: InterviewRead | null | undefined): PrepSection[] {
  const material = interview?.prep_material as InterviewPrep | undefined
  if (!material) return []
  return PREP_SECTION_META.map((meta) => ({
    ...meta,
    questions: Array.isArray(material[meta.key]) ? material[meta.key] : [],
  })).filter((section) => section.questions.length > 0)
}

/** Tailwind classes for an interview status pill. */
export function interviewStatusBadgeClass(status: InterviewStatus, className?: string): string {
  return cn(
    'inline-flex items-center whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium',
    interviewStatusColor(status),
    className,
  )
}
