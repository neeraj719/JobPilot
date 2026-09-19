/**
 * Client-side derivations for the analytics page.
 *
 * `GET /dashboard/charts` cannot answer "response rate *by source*", "interview
 * conversion *by company priority*" or "how long until they reply", so those three are
 * computed from one page of `GET /applications`. The status sets below mirror
 * `RESPONSE_STATUSES` / `SUBMITTED_STATUSES` in `backend/app/models/enums.py` exactly,
 * so these numbers agree with the server's own `response_rate`.
 */
import { toDate } from '@/lib/utils'
import { RESPONSE_STATUSES, SUBMITTED_STATUSES } from '@/types/api'
import type { ApplicationRead, ApplicationStatus, CompanyPriority, DatePoint, JobSourceType } from '@/types/api'

/** Set lookups over the shared contract arrays — built once, not per row. */
const RESPONDED = new Set<ApplicationStatus>(RESPONSE_STATUSES)
const SUBMITTED = new Set<ApplicationStatus>(SUBMITTED_STATUSES)

export function isSubmitted(application: ApplicationRead): boolean {
  return SUBMITTED.has(application.status)
}

export function hasResponded(application: ApplicationRead): boolean {
  return application.last_response_at !== null || RESPONDED.has(application.status)
}

export function reachedInterview(application: ApplicationRead): boolean {
  return application.status === 'INTERVIEW' || application.status === 'OFFER'
}

function rate(part: number, whole: number): number {
  return whole > 0 ? (part / whole) * 100 : 0
}

/* ------------------------------------------------------------------ */
/* Response rate by source                                             */
/* ------------------------------------------------------------------ */

export interface SourceRateRow {
  source: JobSourceType
  sent: number
  responded: number
  interviews: number
  responseRate: number
}

export function responseRateBySource(applications: ApplicationRead[]): SourceRateRow[] {
  const buckets = new Map<JobSourceType, SourceRateRow>()
  for (const application of applications) {
    if (!isSubmitted(application) || !application.source) continue
    const row = buckets.get(application.source) ?? {
      source: application.source,
      sent: 0,
      responded: 0,
      interviews: 0,
      responseRate: 0,
    }
    row.sent += 1
    if (hasResponded(application)) row.responded += 1
    if (reachedInterview(application)) row.interviews += 1
    buckets.set(application.source, row)
  }
  return [...buckets.values()]
    .map((row) => ({ ...row, responseRate: rate(row.responded, row.sent) }))
    .sort((a, b) => b.sent - a.sent || a.source.localeCompare(b.source))
}

/* ------------------------------------------------------------------ */
/* Interview conversion by company priority                            */
/* ------------------------------------------------------------------ */

export interface PriorityRateRow {
  priority: CompanyPriority
  sent: number
  responded: number
  interviews: number
  offers: number
  interviewRate: number
  responseRate: number
}

const PRIORITY_ORDER: CompanyPriority[] = ['P1', 'P2', 'P3', 'AVOID']

export function conversionByPriority(applications: ApplicationRead[]): PriorityRateRow[] {
  const buckets = new Map<CompanyPriority, PriorityRateRow>()
  for (const application of applications) {
    if (!isSubmitted(application)) continue
    const priority = application.priority
    const row = buckets.get(priority) ?? {
      priority,
      sent: 0,
      responded: 0,
      interviews: 0,
      offers: 0,
      interviewRate: 0,
      responseRate: 0,
    }
    row.sent += 1
    if (hasResponded(application)) row.responded += 1
    if (reachedInterview(application)) row.interviews += 1
    if (application.status === 'OFFER') row.offers += 1
    buckets.set(priority, row)
  }
  return [...buckets.values()]
    .map((row) => ({
      ...row,
      interviewRate: rate(row.interviews, row.sent),
      responseRate: rate(row.responded, row.sent),
    }))
    .sort((a, b) => PRIORITY_ORDER.indexOf(a.priority) - PRIORITY_ORDER.indexOf(b.priority))
}

/* ------------------------------------------------------------------ */
/* Time to response                                                    */
/* ------------------------------------------------------------------ */

export interface TimeToResponse {
  /** Mean days between submitting and the recorded response, or `null` with no sample. */
  averageDays: number | null
  medianDays: number | null
  fastestDays: number | null
  slowestDays: number | null
  /** How many applications contributed — always shown next to the average. */
  sample: number
}

const MS_PER_DAY = 86_400_000

/**
 * Days from submission to the recorded response.
 *
 * `last_response_at` is the *latest* response the backend has seen, so for an
 * application with several updates this is an upper bound on the true time-to-first
 * reply. The UI labels it accordingly rather than claiming more precision than the
 * list endpoint carries.
 */
export function timeToResponse(applications: ApplicationRead[]): TimeToResponse {
  const spans: number[] = []
  for (const application of applications) {
    const applied = toDate(application.applied_at)
    const responded = toDate(application.last_response_at)
    if (!applied || !responded) continue
    const days = (responded.getTime() - applied.getTime()) / MS_PER_DAY
    if (days >= 0) spans.push(days)
  }
  if (spans.length === 0) {
    return { averageDays: null, medianDays: null, fastestDays: null, slowestDays: null, sample: 0 }
  }
  spans.sort((a, b) => a - b)
  const mid = Math.floor(spans.length / 2)
  const median = spans.length % 2 === 0 ? ((spans[mid - 1] ?? 0) + (spans[mid] ?? 0)) / 2 : (spans[mid] ?? 0)
  return {
    averageDays: spans.reduce((sum, value) => sum + value, 0) / spans.length,
    medianDays: median,
    fastestDays: spans[0] ?? null,
    slowestDays: spans[spans.length - 1] ?? null,
    sample: spans.length,
  }
}

/* ------------------------------------------------------------------ */
/* CSV export                                                          */
/* ------------------------------------------------------------------ */

function escapeCsv(value: string | number): string {
  const text = String(value)
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

export function toCsv(headers: string[], rows: (string | number)[][]): string {
  return [headers, ...rows].map((row) => row.map(escapeCsv).join(',')).join('\r\n')
}

/** Merge the two per-day series into one table, aligned on date. */
export function dailySeriesCsv(applicationsPerDay: DatePoint[], responsesPerDay: DatePoint[]): string {
  const responses = new Map(responsesPerDay.map((point) => [point.date, point.count]))
  return toCsv(
    ['date', 'applications', 'responses'],
    applicationsPerDay.map((point) => [point.date, point.count, responses.get(point.date) ?? 0]),
  )
}

/** Trigger a client-side download for text we already hold. */
export function downloadCsv(filename: string, csv: string): void {
  // The BOM keeps Excel from mangling non-ASCII company names.
  const blob = new Blob([`﻿${csv}`], { type: 'text/csv;charset=utf-8;' })
  const href = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = href
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(href)
}
