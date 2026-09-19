/**
 * Zod schema + mappers for the automation config form and the password change.
 *
 * Mirrors `automation.service.validate_config_update`: HH:MM schedule, a daily limit the
 * server caps at 100, non-negative per-platform limits and auto-submit sources restricted
 * to adapters that support automated applications.
 */
import { z } from 'zod'

import type { AutomationConfigRead, AutomationConfigUpdate, JobSourceType } from '@/types/api'

/** Server cap (`settings.MAX_DAILY_APPLICATION_LIMIT`). */
export const MAX_DAILY_APPLICATION_LIMIT = 100

/** A short, readable IANA list; the server accepts any zone `zoneinfo` knows. */
export const COMMON_TIMEZONES = [
  'Asia/Kolkata',
  'Asia/Dubai',
  'Asia/Singapore',
  'Asia/Tokyo',
  'Australia/Sydney',
  'Europe/London',
  'Europe/Berlin',
  'Europe/Amsterdam',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Sao_Paulo',
  'UTC',
] as const

const intField = (min: number, max: number, label: string, required = true) =>
  z
    .string()
    .trim()
    .refine((value) => {
      if (value === '') return !required
      const parsed = Number(value)
      return Number.isInteger(parsed) && parsed >= min && parsed <= max
    }, `Enter a whole ${label} between ${min} and ${max}`)

const floatField = (min: number, max: number, label: string) =>
  z
    .string()
    .trim()
    .refine((value) => {
      if (value === '') return false
      const parsed = Number(value)
      return Number.isFinite(parsed) && parsed >= min && parsed <= max
    }, `Enter a ${label} between ${min} and ${max}`)

export const automationSchema = z
  .object({
    enabled: z.boolean(),
    schedule_time: z
      .string()
      .trim()
      .regex(/^([01]\d|2[0-3]):[0-5]\d$/, 'Use HH:MM in 24-hour format'),
    timezone: z.string().trim().min(1, 'Pick a timezone'),
    daily_application_limit: intField(1, MAX_DAILY_APPLICATION_LIMIT, 'number'),
    /** source -> raw input string; empty means "no separate limit". */
    per_platform_limit: z.record(z.string()),
    min_match_score: z.number().min(0).max(100),
    prioritize_priority_companies: z.boolean(),
    only_posted_within_hours: intField(1, 24 * 30, 'number of hours'),
    enabled_sources: z.array(z.string()),
    delay_between_actions_seconds: floatField(0, 60, 'number of seconds'),
    retry_limit: intField(0, 10, 'number'),
    auto_submit_enabled: z.boolean(),
    auto_submit_sources: z.array(z.string()),
    auto_generate_cover_letters: z.boolean(),
    notify_on_input_required: z.boolean(),
  })
  .superRefine((values, ctx) => {
    for (const [source, raw] of Object.entries(values.per_platform_limit)) {
      if (raw.trim() === '') continue
      const parsed = Number(raw)
      if (!Number.isInteger(parsed) || parsed < 0 || parsed > MAX_DAILY_APPLICATION_LIMIT) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['per_platform_limit'],
          message: `“${source}” must be a whole number between 0 and ${MAX_DAILY_APPLICATION_LIMIT}`,
        })
        return
      }
    }
    if (values.auto_submit_enabled && values.auto_submit_sources.length === 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['auto_submit_sources'],
        message: 'Pick at least one source, or turn auto-submit off',
      })
    }
  })

export type AutomationValues = z.infer<typeof automationSchema>

export function automationDefaults(config: AutomationConfigRead | undefined): AutomationValues {
  const perPlatform: Record<string, string> = {}
  for (const [source, limit] of Object.entries(config?.per_platform_limit ?? {})) {
    perPlatform[source] = limit === null || limit === undefined ? '' : String(limit)
  }
  return {
    enabled: config?.enabled ?? false,
    schedule_time: config?.schedule_time ?? '09:00',
    timezone: config?.timezone ?? 'Asia/Kolkata',
    daily_application_limit: String(config?.daily_application_limit ?? 20),
    per_platform_limit: perPlatform,
    min_match_score: config?.min_match_score ?? 75,
    prioritize_priority_companies: config?.prioritize_priority_companies ?? true,
    only_posted_within_hours: String(config?.only_posted_within_hours ?? 24),
    enabled_sources: config?.enabled_sources ?? [],
    delay_between_actions_seconds: String(config?.delay_between_actions_seconds ?? 2),
    retry_limit: String(config?.retry_limit ?? 3),
    auto_submit_enabled: config?.auto_submit_enabled ?? false,
    auto_submit_sources: config?.auto_submit_sources ?? [],
    auto_generate_cover_letters: config?.auto_generate_cover_letters ?? true,
    notify_on_input_required: config?.notify_on_input_required ?? true,
  }
}

export function automationToPayload(values: AutomationValues): AutomationConfigUpdate {
  const perPlatform: Record<string, number> = {}
  for (const [source, raw] of Object.entries(values.per_platform_limit)) {
    if (raw.trim() === '') continue
    perPlatform[source] = Number(raw)
  }

  return {
    enabled: values.enabled,
    schedule_time: values.schedule_time,
    timezone: values.timezone,
    daily_application_limit: Number(values.daily_application_limit),
    per_platform_limit: perPlatform,
    min_match_score: values.min_match_score,
    prioritize_priority_companies: values.prioritize_priority_companies,
    only_posted_within_hours: Number(values.only_posted_within_hours),
    enabled_sources: values.enabled_sources as JobSourceType[],
    delay_between_actions_seconds: Number(values.delay_between_actions_seconds),
    retry_limit: Number(values.retry_limit),
    auto_submit_enabled: values.auto_submit_enabled,
    auto_submit_sources: values.auto_submit_enabled ? (values.auto_submit_sources as JobSourceType[]) : [],
    auto_generate_cover_letters: values.auto_generate_cover_letters,
    notify_on_input_required: values.notify_on_input_required,
  }
}

/* ------------------------------------------------------------------ */
/* Password                                                            */
/* ------------------------------------------------------------------ */

export const passwordSchema = z
  .object({
    current_password: z.string().min(1, 'Enter your current password'),
    // Mirrors `auth.schemas.PASSWORD_POLICY`: 8–128 chars with at least one letter and one digit.
    new_password: z
      .string()
      .min(8, 'Use at least 8 characters')
      .max(128, 'Keep it under 128 characters')
      .refine((value) => /[A-Za-z]/.test(value), 'Include at least one letter')
      .refine((value) => /\d/.test(value), 'Include at least one digit'),
    confirm_password: z.string().min(1, 'Repeat the new password'),
  })
  .superRefine((values, ctx) => {
    if (values.new_password !== values.confirm_password) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['confirm_password'],
        message: 'The two passwords do not match',
      })
    }
    if (values.new_password === values.current_password) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['new_password'],
        message: 'Choose a password you have not used here before',
      })
    }
  })

export type PasswordValues = z.infer<typeof passwordSchema>

/* ------------------------------------------------------------------ */
/* Notification preferences (device-only)                              */
/* ------------------------------------------------------------------ */

export const NOTIFICATION_SETTINGS_KEY = 'jobpilot.notificationPreferences'

/** The API has no notification-preference endpoint, so these live in localStorage. */
export const NOTIFICATION_PREFERENCE_TYPES = [
  'JOB_FOUND',
  'INPUT_REQUIRED',
  'APPLICATION_SUBMITTED',
  'RECRUITER_RESPONSE',
  'INTERVIEW_SCHEDULED',
  'ASSESSMENT_RECEIVED',
  'REJECTION',
  'OFFER',
  'AUTOMATION_FAILED',
  'AUTOMATION_COMPLETED',
  'SYSTEM',
] as const

export type NotificationPreferenceType = (typeof NOTIFICATION_PREFERENCE_TYPES)[number]
export type NotificationPreferences = Record<NotificationPreferenceType, boolean>

export function defaultNotificationPreferences(): NotificationPreferences {
  return NOTIFICATION_PREFERENCE_TYPES.reduce((acc, type) => {
    acc[type] = true
    return acc
  }, {} as NotificationPreferences)
}

export function readNotificationPreferences(): NotificationPreferences {
  const defaults = defaultNotificationPreferences()
  try {
    const raw = window.localStorage.getItem(NOTIFICATION_SETTINGS_KEY)
    if (!raw) return defaults
    const parsed = JSON.parse(raw) as Partial<Record<string, unknown>>
    for (const type of NOTIFICATION_PREFERENCE_TYPES) {
      if (typeof parsed[type] === 'boolean') defaults[type] = parsed[type] as boolean
    }
  } catch {
    // Corrupt or unavailable storage — fall back to "everything on".
  }
  return defaults
}

export function writeNotificationPreferences(preferences: NotificationPreferences): void {
  try {
    window.localStorage.setItem(NOTIFICATION_SETTINGS_KEY, JSON.stringify(preferences))
  } catch {
    // Private mode / storage disabled: the toggles still work for this session.
  }
}
