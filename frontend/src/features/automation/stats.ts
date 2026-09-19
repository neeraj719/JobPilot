/**
 * Readers for `AutomationRun.stats`.
 *
 * The pipeline writes plain counters into `stats`, with one exception: `filter_reasons`
 * is a `{reason: count}` map explaining why jobs were dropped. `AutomationRunStats` is
 * typed as numbers-only (several pages index it dynamically), so that one key is read
 * through the narrowing helper below instead of widening the shared type.
 */
import type { AutomationRunStats } from '@/types/api'

/** A counter from `stats`, or 0 when it is missing. */
export function statCount(stats: AutomationRunStats | undefined, key: string): number {
  const value: unknown = stats ? (stats as Record<string, unknown>)[key] : undefined
  return typeof value === 'number' ? value : 0
}

/** `{below_min_score: 24, too_old: 5, ...}`, or `null` when the run recorded none. */
export function readFilterReasons(stats: AutomationRunStats | undefined): Record<string, number> | null {
  const raw: unknown = stats ? (stats as Record<string, unknown>).filter_reasons : undefined
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null

  const reasons: Record<string, number> = {}
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof value === 'number' && value > 0) reasons[key] = value
  }
  return Object.keys(reasons).length > 0 ? reasons : null
}
