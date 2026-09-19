/**
 * UTC-safe date helpers shared by the automation, emails and interviews pages.
 *
 * The API stores everything in UTC but serialises some columns as *naive* ISO strings
 * (`2026-09-22T11:08:04.989877`) and others with an explicit offset
 * (`2026-09-22T11:08:04Z`). `date-fns`' `parseISO` reads a naive string as **local**
 * time, which silently shifts every timestamp by the browser's offset — 5h30m in
 * Asia/Kolkata. `parseApiDate` normalises the naive form to UTC first, so the
 * formatters below always show the instant the backend meant.
 *
 * Lives under `features/automation/` because that is the first of the three areas this
 * module belongs to; emails and interviews import it from here.
 */
import { format, formatDistanceToNowStrict, isValid, parseISO } from 'date-fns'

export type ApiDateInput = string | number | Date | null | undefined

/** Matches a trailing `Z` or `±HH:MM` / `±HHMM` offset. */
const HAS_TIMEZONE = /(?:Z|[+-]\d{2}:?\d{2})$/i

/** Parse an API timestamp, treating offset-less values as UTC. Returns `null` when unusable. */
export function parseApiDate(value: ApiDateInput): Date | null {
  if (value === null || value === undefined || value === '') return null
  if (value instanceof Date) return isValid(value) ? value : null
  if (typeof value === 'number') {
    const fromNumber = new Date(value)
    return isValid(fromNumber) ? fromNumber : null
  }
  const trimmed = value.trim()
  if (!trimmed) return null
  const normalised = HAS_TIMEZONE.test(trimmed) ? trimmed : `${trimmed}Z`
  const parsed = parseISO(normalised)
  return isValid(parsed) ? parsed : null
}

/** `12 Mar 2026` in the viewer's timezone. */
export function formatApiDate(value: ApiDateInput, pattern = 'd MMM yyyy', fallback = '—'): string {
  const date = parseApiDate(value)
  return date ? format(date, pattern) : fallback
}

/** `12 Mar 2026, 4:30 pm`. */
export function formatApiDateTime(value: ApiDateInput, fallback = '—'): string {
  return formatApiDate(value, 'd MMM yyyy, h:mm aaa', fallback)
}

/** `09:32:11` — the clock format the audit log uses. */
export function formatApiClock(value: ApiDateInput, fallback = '--:--:--'): string {
  return formatApiDate(value, 'HH:mm:ss', fallback)
}

/** `3 days ago` / `in 2 hours`. */
export function formatApiRelative(value: ApiDateInput, fallback = '—'): string {
  const date = parseApiDate(value)
  if (!date) return fallback
  const distance = formatDistanceToNowStrict(date)
  return date.getTime() > Date.now() ? `in ${distance}` : `${distance} ago`
}

/** True when the timestamp is in the future. */
export function isFuture(value: ApiDateInput): boolean {
  const date = parseApiDate(value)
  return date ? date.getTime() > Date.now() : false
}

/**
 * Compact countdown to a future instant: `in 5h 20m`, `in 3d 4h`, `in 45s`.
 * Returns `null` for missing dates and `'now'` for anything already past.
 */
export function formatCountdown(value: ApiDateInput): string | null {
  const date = parseApiDate(value)
  if (!date) return null
  const deltaMs = date.getTime() - Date.now()
  if (deltaMs <= 0) return 'now'

  const totalMinutes = Math.floor(deltaMs / 60_000)
  if (totalMinutes < 1) return `in ${Math.max(1, Math.floor(deltaMs / 1000))}s`

  const days = Math.floor(totalMinutes / (60 * 24))
  const hours = Math.floor((totalMinutes % (60 * 24)) / 60)
  const minutes = totalMinutes % 60

  if (days > 0) return `in ${days}d${hours > 0 ? ` ${hours}h` : ''}`
  if (hours > 0) return `in ${hours}h${minutes > 0 ? ` ${minutes}m` : ''}`
  return `in ${minutes}m`
}

/** `1m 18s` / `640ms` — how long a run or a step took. */
export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms) || ms < 0) return '—'
  if (ms < 1000) return `${Math.round(ms)}ms`
  const totalSeconds = Math.round(ms / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes === 0) return `${seconds}s`
  const hours = Math.floor(minutes / 60)
  if (hours === 0) return `${minutes}m ${seconds}s`
  return `${hours}h ${minutes % 60}m`
}

/** Elapsed milliseconds between two API timestamps, or `null` when either is missing. */
export function durationBetween(start: ApiDateInput, end: ApiDateInput): number | null {
  const from = parseApiDate(start)
  const to = parseApiDate(end)
  if (!from || !to) return null
  return to.getTime() - from.getTime()
}

/**
 * `2026-09-22T16:38` — the value an `<input type="datetime-local">` expects, in the
 * viewer's timezone.
 */
export function toDateTimeLocalValue(value: ApiDateInput): string {
  const date = parseApiDate(value)
  if (!date) return ''
  return format(date, "yyyy-MM-dd'T'HH:mm")
}

/** Turn a `datetime-local` value back into an ISO instant the API accepts. */
export function fromDateTimeLocalValue(value: string | null | undefined): string | null {
  if (!value) return null
  const date = new Date(value)
  return isValid(date) ? date.toISOString() : null
}
