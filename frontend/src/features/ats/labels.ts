import type { JdSource, JobTargetStatus, SuggestionKind } from '@/features/ats/types'

export const TARGET_STATUS_LABELS: Record<JobTargetStatus, string> = {
  SAVED: 'Saved',
  PREPARING: 'Preparing resume',
  READY: 'Ready to apply',
  APPLIED: 'Applied',
  INTERVIEW: 'Interview',
  OFFER: 'Offer',
  REJECTED: 'Rejected',
  ARCHIVED: 'Archived',
}

export const TARGET_STATUS_CLASSES: Record<JobTargetStatus, string> = {
  SAVED: 'border-border bg-muted text-muted-foreground',
  PREPARING: 'border-warning/40 bg-warning/15 text-foreground',
  READY: 'border-primary/40 bg-primary/10 text-primary',
  APPLIED: 'border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300',
  INTERVIEW: 'border-violet-500/40 bg-violet-500/10 text-violet-700 dark:text-violet-300',
  OFFER: 'border-success/40 bg-success/15 text-success',
  REJECTED: 'border-destructive/30 bg-destructive/10 text-destructive',
  ARCHIVED: 'border-border bg-muted/50 text-muted-foreground',
}

export const SUGGESTION_KIND_LABELS: Record<SuggestionKind, string> = {
  ADD_SKILL: 'Skill',
  REPLACE_BULLET: 'Bullet',
  REPLACE_SUMMARY: 'Summary',
  REORDER_SECTION: 'Order',
  ADD_KEYWORD_CONTEXT: 'Wording',
  MANUAL: 'Your action',
}

export const JD_SOURCE_LABELS: Record<JdSource, string> = {
  PASTED: 'Pasted',
  UPLOADED: 'Uploaded',
  URL: 'Posting URL',
  BOARD: 'Company job board',
  JOB: 'Discovered job',
}

/** Same colour bands as the match score: 80+ strong, 60+ fair, below that weak. */
export function scoreTone(score: number | null | undefined): 'success' | 'warning' | 'destructive' | 'muted' {
  if (score === null || score === undefined) return 'muted'
  if (score >= 80) return 'success'
  if (score >= 60) return 'warning'
  return 'destructive'
}

export const TONE_TEXT: Record<ReturnType<typeof scoreTone>, string> = {
  success: 'text-success',
  warning: 'text-warning',
  destructive: 'text-destructive',
  muted: 'text-muted-foreground',
}

export const TONE_BAR: Record<ReturnType<typeof scoreTone>, string> = {
  success: 'bg-success',
  warning: 'bg-warning',
  destructive: 'bg-destructive',
  muted: 'bg-muted-foreground/40',
}

export function formatDelta(delta: number): string {
  if (delta === 0) return '±0'
  return delta > 0 ? `+${delta}` : String(delta)
}
