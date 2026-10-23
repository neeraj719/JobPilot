import type { JdSource, JobTargetStatus, SuggestionKind } from '@/features/ats/types'
import { SCORE_BAR, SCORE_TEXT, type ScoreTone, scoreTone as sharedScoreTone } from '@/lib/score'

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
  PREPARING: 'border-warning/30 bg-warning-soft text-warning-soft-foreground',
  READY: 'border-primary/30 bg-primary/10 text-primary',
  APPLIED: 'border-info/25 bg-info-soft text-info-soft-foreground',
  INTERVIEW: 'border-success/25 bg-success-soft text-success-soft-foreground',
  /* The one solid pill: an offer is the outcome the whole app works towards. */
  OFFER: 'border-transparent bg-success text-success-foreground',
  REJECTED: 'border-destructive/25 bg-destructive-soft text-destructive-soft-foreground',
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

/** ATS estimate bands (the shared `quality` scale): 80+ strong, 60+ fair, below that weak. */
export function scoreTone(score: number | null | undefined): ScoreTone {
  return sharedScoreTone(score, 'quality')
}

export const TONE_TEXT: Record<ScoreTone, string> = SCORE_TEXT

export const TONE_BAR: Record<ScoreTone, string> = SCORE_BAR

export function formatDelta(delta: number): string {
  if (delta === 0) return '±0'
  return delta > 0 ? `+${delta}` : String(delta)
}
