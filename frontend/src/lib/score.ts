/**
 * One place for score colours. Every score in the app (match %, ATS estimate, resume
 * health) goes through `scoreTone()`, so a 72 never looks green on one page and amber on
 * the next. Two scales exist because they mean different things:
 *
 *  - `match`   — how well a *job* fits you: 85+ strong, 70+ decent, below that just
 *                "not a match" (muted, not red: a low match is not a failure of yours).
 *  - `quality` — how good *your resume* is (ATS estimate, health): 80+ strong, 60+ needs
 *                work, below that weak (red: it is something to fix).
 *
 * Colour never carries the meaning alone: pair it with the number and/or `scoreLabel()`.
 */

export type ScoreTone = 'success' | 'warning' | 'destructive' | 'muted'
export type ScoreScale = 'match' | 'quality'

const BANDS: Record<ScoreScale, { strong: number; fair: number; weak: ScoreTone }> = {
  match: { strong: 85, fair: 70, weak: 'muted' },
  quality: { strong: 80, fair: 60, weak: 'destructive' },
}

export function scoreTone(score: number | null | undefined, scale: ScoreScale = 'quality'): ScoreTone {
  if (score === null || score === undefined || Number.isNaN(score)) return 'muted'
  const band = BANDS[scale]
  if (score >= band.strong) return 'success'
  if (score >= band.fair) return 'warning'
  return band.weak
}

export function scoreLabel(score: number | null | undefined, scale: ScoreScale = 'quality'): string {
  if (score === null || score === undefined || Number.isNaN(score)) return 'Not scored'
  const tone = scoreTone(score, scale)
  if (scale === 'match') return tone === 'success' ? 'Strong match' : tone === 'warning' ? 'Decent match' : 'Weak match'
  return tone === 'success' ? 'Strong' : tone === 'warning' ? 'Needs work' : 'Weak'
}

/** Text colour for the score figure itself (passes 4.5:1 on cards in both themes). */
export const SCORE_TEXT: Record<ScoreTone, string> = {
  success: 'text-success',
  warning: 'text-warning',
  destructive: 'text-destructive',
  muted: 'text-muted-foreground',
}

/** Fill for meters, bars and rings. */
export const SCORE_BAR: Record<ScoreTone, string> = {
  success: 'bg-success',
  warning: 'bg-warning',
  destructive: 'bg-destructive',
  muted: 'bg-muted-foreground/40',
}

/** SVG stroke for gauges drawn with `stroke="currentColor"` use `SCORE_TEXT`; this is for `stroke-*`. */
export const SCORE_STROKE: Record<ScoreTone, string> = {
  success: 'stroke-success',
  warning: 'stroke-warning',
  destructive: 'stroke-destructive',
  muted: 'stroke-muted-foreground/40',
}

/** Soft pill (tint + darker same-hue text + hairline). */
export const SCORE_PILL: Record<ScoreTone, string> = {
  success: 'bg-success-soft text-success-soft-foreground border-success/25',
  warning: 'bg-warning-soft text-warning-soft-foreground border-warning/25',
  destructive: 'bg-destructive-soft text-destructive-soft-foreground border-destructive/25',
  muted: 'bg-muted text-muted-foreground border-transparent',
}
