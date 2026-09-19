import { type ClassValue, clsx } from 'clsx'
import { format, formatDistanceToNowStrict, isValid, parseISO } from 'date-fns'
import { twMerge } from 'tailwind-merge'

import type {
  AnswerStatus,
  ApplicationStatus,
  AutomationState,
  CompanyPriority,
  EmailClassification,
  EmploymentType,
  InterviewType,
  JobSourceType,
  NotificationType,
  WorkMode,
} from '@/types/api'

/** Tailwind-aware className merge — the single helper every component uses. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

/* ------------------------------------------------------------------ */
/* Dates                                                               */
/* ------------------------------------------------------------------ */

export type DateInput = string | number | Date | null | undefined

/** Coerce anything the API might hand us into a `Date`, or `null` when unusable. */
export function toDate(value: DateInput): Date | null {
  if (value === null || value === undefined || value === '') return null
  const date = value instanceof Date ? value : typeof value === 'number' ? new Date(value) : parseISO(value)
  return isValid(date) ? date : null
}

/** e.g. `12 Mar 2025`. Returns `fallback` for missing/invalid values. */
export function formatDate(value: DateInput, pattern = 'd MMM yyyy', fallback = '—'): string {
  const date = toDate(value)
  return date ? format(date, pattern) : fallback
}

/** e.g. `12 Mar 2025, 4:30 pm`. */
export function formatDateTime(value: DateInput, fallback = '—'): string {
  return formatDate(value, "d MMM yyyy, h:mm aaa", fallback)
}

/** e.g. `3 days ago` / `in 2 hours`. */
export function formatRelative(value: DateInput, fallback = '—'): string {
  const date = toDate(value)
  if (!date) return fallback
  const distance = formatDistanceToNowStrict(date)
  return date.getTime() > Date.now() ? `in ${distance}` : `${distance} ago`
}

/** True when the timestamp falls on today's calendar date. */
export function isToday(value: DateInput): boolean {
  const date = toDate(value)
  if (!date) return false
  const now = new Date()
  return (
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  )
}

/* ------------------------------------------------------------------ */
/* Numbers, money and text                                             */
/* ------------------------------------------------------------------ */

/**
 * Format an annual salary.
 *
 * INR is rendered the way the Indian job market reads it — lakhs per annum,
 * e.g. `1200000` becomes `₹12.0 LPA` (and crores above 1,00,00,000).
 * Every other currency uses a compact notation, e.g. `$120K`.
 */
export function formatCurrency(amount: number | null | undefined, currency = 'INR'): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return '—'
  const code = (currency || 'INR').toUpperCase()

  if (code === 'INR') {
    if (Math.abs(amount) >= 10_000_000) {
      const cr = amount / 10_000_000
      return `₹${cr.toFixed(cr >= 10 ? 1 : 2)} Cr`
    }
    if (Math.abs(amount) >= 100_000) {
      return `₹${(amount / 100_000).toFixed(1)} LPA`
    }
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    }).format(amount)
  }

  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: code,
      notation: 'compact',
      maximumFractionDigits: 1,
    }).format(amount)
  } catch {
    // Unknown currency code — fall back to a plain compact number with the code.
    return `${code} ${formatCompactNumber(amount)}`
  }
}

/** `₹8.0 – ₹12.0 LPA`, collapsing to a single value when only one bound is known. */
export function formatSalaryRange(
  min: number | null | undefined,
  max: number | null | undefined,
  currency = 'INR',
  fallback = 'Not disclosed',
): string {
  if (min == null && max == null) return fallback
  if (min != null && max != null) {
    if (min === max) return formatCurrency(min, currency)
    return `${formatCurrency(min, currency)} – ${formatCurrency(max, currency)}`
  }
  return min != null ? `${formatCurrency(min, currency)}+` : `Up to ${formatCurrency(max, currency)}`
}

export function formatCompactNumber(value: number | null | undefined, fallback = '—'): string {
  if (value === null || value === undefined || Number.isNaN(value)) return fallback
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

export function formatNumber(value: number | null | undefined, fallback = '—'): string {
  if (value === null || value === undefined || Number.isNaN(value)) return fallback
  return new Intl.NumberFormat('en-IN').format(value)
}

/** `0.42` -> `42%`. Accepts either a ratio (<= 1) or an already-scaled percentage. */
export function formatPercent(value: number | null | undefined, digits = 0, fallback = '—'): string {
  if (value === null || value === undefined || Number.isNaN(value)) return fallback
  const pct = Math.abs(value) <= 1 ? value * 100 : value
  return `${pct.toFixed(digits)}%`
}

/** `2` -> `2 yrs`, `0.5` -> `6 mos`. */
export function formatExperience(
  min: number | null | undefined,
  max?: number | null | undefined,
  fallback = 'Not specified',
): string {
  if (min == null && max == null) return fallback
  const unit = (n: number) => (n === 1 ? '1 yr' : `${Number.isInteger(n) ? n : n.toFixed(1)} yrs`)
  if (min != null && max != null) return min === max ? unit(min) : `${min}–${max} yrs`
  return min != null ? `${unit(min)}+` : `Up to ${unit(max as number)}`
}

/** `Ada Lovelace` -> `AL`. Always 1–2 uppercase letters. */
export function initials(name: string | null | undefined, fallback = '?'): string {
  if (!name) return fallback
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return fallback
  const first = parts[0]?.[0] ?? ''
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? '') : ''
  return (first + last).toUpperCase() || fallback
}

export function truncate(value: string | null | undefined, max = 120): string {
  if (!value) return ''
  return value.length <= max ? value : `${value.slice(0, max - 1).trimEnd()}…`
}

/** `SYSTEM_DESIGN` -> `System design`. Used for enum values without a hand-written label. */
export function humanizeEnum(value: string | null | undefined, fallback = '—'): string {
  if (!value) return fallback
  const lower = value.replace(/_/g, ' ').toLowerCase()
  return lower.charAt(0).toUpperCase() + lower.slice(1)
}

/** `Senior Backend Engineer` -> `senior-backend-engineer`. */
export function slugify(value: string): string {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return count === 1 ? singular : plural
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

/* ------------------------------------------------------------------ */
/* Enum labels + colours                                               */
/* ------------------------------------------------------------------ */

/**
 * Badge classes are expressed as `bg`/`text`/`border` triples over the theme tokens so
 * they stay legible in both light and dark mode.
 */
export const APPLICATION_STATUS_LABELS: Record<ApplicationStatus, string> = {
  DISCOVERED: 'Discovered',
  QUEUED: 'Queued',
  IN_PROGRESS: 'In progress',
  APPLIED: 'Applied',
  APPLICATION_RECEIVED: 'Received',
  ASSESSMENT: 'Assessment',
  INTERVIEW: 'Interview',
  RECRUITER_CONTACTED: 'Recruiter contacted',
  REJECTED: 'Rejected',
  WITHDRAWN: 'Withdrawn',
  OFFER: 'Offer',
  NO_RESPONSE: 'No response',
  SKIPPED: 'Skipped',
}

const APPLICATION_STATUS_CLASSES: Record<ApplicationStatus, string> = {
  DISCOVERED: 'bg-muted text-muted-foreground border-transparent',
  QUEUED: 'bg-info/10 text-info border-info/20',
  IN_PROGRESS: 'bg-primary/10 text-primary border-primary/20',
  APPLIED: 'bg-primary/10 text-primary border-primary/20',
  APPLICATION_RECEIVED: 'bg-info/10 text-info border-info/20',
  ASSESSMENT: 'bg-warning/15 text-warning border-warning/25',
  INTERVIEW: 'bg-success/10 text-success border-success/20',
  RECRUITER_CONTACTED: 'bg-info/10 text-info border-info/20',
  REJECTED: 'bg-destructive/10 text-destructive border-destructive/20',
  WITHDRAWN: 'bg-muted text-muted-foreground border-transparent',
  OFFER: 'bg-success/15 text-success border-success/30',
  NO_RESPONSE: 'bg-muted text-muted-foreground border-transparent',
  SKIPPED: 'bg-muted text-muted-foreground border-transparent',
}

/** Tailwind classes for an application status badge. */
export function statusColor(status: ApplicationStatus | null | undefined): string {
  if (!status) return 'bg-muted text-muted-foreground border-transparent'
  return APPLICATION_STATUS_CLASSES[status] ?? 'bg-muted text-muted-foreground border-transparent'
}

export function statusLabel(status: ApplicationStatus | null | undefined, fallback = 'Not applied'): string {
  if (!status) return fallback
  return APPLICATION_STATUS_LABELS[status] ?? humanizeEnum(status)
}

export const AUTOMATION_STATE_LABELS: Record<AutomationState, string> = {
  IDLE: 'Idle',
  RUNNING: 'Running',
  SUCCESS: 'Succeeded',
  FAILED: 'Failed',
  PAUSED: 'Paused',
  REQUIRES_USER: 'Needs you',
  RETRYING: 'Retrying',
}

export function automationStateColor(state: AutomationState | null | undefined): string {
  switch (state) {
    case 'RUNNING':
    case 'RETRYING':
      return 'bg-primary/10 text-primary border-primary/20'
    case 'SUCCESS':
      return 'bg-success/10 text-success border-success/20'
    case 'FAILED':
      return 'bg-destructive/10 text-destructive border-destructive/20'
    case 'REQUIRES_USER':
      return 'bg-warning/15 text-warning border-warning/25'
    case 'PAUSED':
      return 'bg-info/10 text-info border-info/20'
    default:
      return 'bg-muted text-muted-foreground border-transparent'
  }
}

export const PRIORITY_LABELS: Record<CompanyPriority, string> = {
  P1: 'P1 · Dream',
  P2: 'P2 · Standard',
  P3: 'P3 · Low',
  AVOID: 'Avoid',
}

export function priorityColor(priority: CompanyPriority | null | undefined): string {
  switch (priority) {
    case 'P1':
      return 'bg-primary/10 text-primary border-primary/25'
    case 'P2':
      return 'bg-info/10 text-info border-info/20'
    case 'P3':
      return 'bg-muted text-muted-foreground border-transparent'
    case 'AVOID':
      return 'bg-destructive/10 text-destructive border-destructive/25'
    default:
      return 'bg-muted text-muted-foreground border-transparent'
  }
}

/** Colour bands for a 0–100 match score: 85+ green, 70+ amber, else muted. */
export function matchScoreColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return 'bg-muted text-muted-foreground border-transparent'
  if (score >= 85) return 'bg-success/10 text-success border-success/25'
  if (score >= 70) return 'bg-warning/15 text-warning border-warning/25'
  return 'bg-muted text-muted-foreground border-transparent'
}

/** Bar/segment fill colour matching `matchScoreColor`'s bands. */
export function matchScoreBarColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return 'bg-muted-foreground/40'
  if (score >= 85) return 'bg-success'
  if (score >= 70) return 'bg-warning'
  return 'bg-muted-foreground/50'
}

export const SOURCE_LABELS: Record<JobSourceType, string> = {
  NAUKRI: 'Naukri',
  INDEED: 'Indeed',
  LINKEDIN: 'LinkedIn',
  HIRIST: 'Hirist',
  WELLFOUND: 'Wellfound',
  INTERNSHALA: 'Internshala',
  GLASSDOOR: 'Glassdoor',
  FOUNDIT: 'Foundit',
  COMPANY_CAREERS: 'Company careers',
  GREENHOUSE: 'Greenhouse',
  LEVER: 'Lever',
  WORKDAY: 'Workday',
  DEMO_ATS: 'Demo ATS',
  OTHER: 'Other',
}

export function sourceLabel(source: JobSourceType | null | undefined, fallback = 'Unknown'): string {
  if (!source) return fallback
  return SOURCE_LABELS[source] ?? humanizeEnum(source)
}

export const WORK_MODE_LABELS: Record<WorkMode, string> = {
  REMOTE: 'Remote',
  HYBRID: 'Hybrid',
  ONSITE: 'On-site',
}

export const EMPLOYMENT_TYPE_LABELS: Record<EmploymentType, string> = {
  FULL_TIME: 'Full time',
  PART_TIME: 'Part time',
  CONTRACT: 'Contract',
  INTERNSHIP: 'Internship',
  FREELANCE: 'Freelance',
}

export const ANSWER_STATUS_LABELS: Record<AnswerStatus, string> = {
  ANSWERED: 'Answered',
  NEEDS_USER_INPUT: 'Needs your input',
  SKIPPED: 'Skipped',
}

export function answerStatusColor(status: AnswerStatus | null | undefined): string {
  switch (status) {
    case 'ANSWERED':
      return 'bg-success/10 text-success border-success/20'
    case 'NEEDS_USER_INPUT':
      return 'bg-warning/15 text-warning border-warning/25'
    default:
      return 'bg-muted text-muted-foreground border-transparent'
  }
}

export const EMAIL_CLASSIFICATION_LABELS: Record<EmailClassification, string> = {
  APPLICATION_RECEIVED: 'Application received',
  RECRUITER_MESSAGE: 'Recruiter message',
  INTERVIEW: 'Interview',
  ASSESSMENT: 'Assessment',
  REJECTION: 'Rejection',
  OFFER: 'Offer',
  OTHER: 'Other',
}

export function emailClassificationColor(classification: EmailClassification | null | undefined): string {
  switch (classification) {
    case 'INTERVIEW':
    case 'OFFER':
      return 'bg-success/10 text-success border-success/20'
    case 'ASSESSMENT':
      return 'bg-warning/15 text-warning border-warning/25'
    case 'REJECTION':
      return 'bg-destructive/10 text-destructive border-destructive/20'
    case 'RECRUITER_MESSAGE':
    case 'APPLICATION_RECEIVED':
      return 'bg-info/10 text-info border-info/20'
    default:
      return 'bg-muted text-muted-foreground border-transparent'
  }
}

export const INTERVIEW_TYPE_LABELS: Record<InterviewType, string> = {
  PHONE_SCREEN: 'Phone screen',
  TECHNICAL: 'Technical',
  SYSTEM_DESIGN: 'System design',
  BEHAVIORAL: 'Behavioral',
  HR: 'HR',
  ONSITE: 'On-site',
  ASSESSMENT: 'Assessment',
  OTHER: 'Other',
}

export const NOTIFICATION_TYPE_LABELS: Record<NotificationType, string> = {
  JOB_FOUND: 'New jobs',
  INPUT_REQUIRED: 'Input required',
  APPLICATION_SUBMITTED: 'Application submitted',
  RECRUITER_RESPONSE: 'Recruiter response',
  INTERVIEW_SCHEDULED: 'Interview scheduled',
  ASSESSMENT_RECEIVED: 'Assessment received',
  REJECTION: 'Rejection',
  OFFER: 'Offer',
  AUTOMATION_FAILED: 'Automation failed',
  AUTOMATION_COMPLETED: 'Automation completed',
  SYSTEM: 'System',
}

export function notificationColor(type: NotificationType | null | undefined): string {
  switch (type) {
    case 'OFFER':
    case 'INTERVIEW_SCHEDULED':
    case 'APPLICATION_SUBMITTED':
      return 'text-success'
    case 'INPUT_REQUIRED':
    case 'ASSESSMENT_RECEIVED':
      return 'text-warning'
    case 'REJECTION':
    case 'AUTOMATION_FAILED':
      return 'text-destructive'
    case 'JOB_FOUND':
    case 'RECRUITER_RESPONSE':
      return 'text-info'
    default:
      return 'text-muted-foreground'
  }
}
