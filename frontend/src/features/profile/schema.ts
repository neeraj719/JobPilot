/**
 * Zod schemas + form<->API mappers for the four profile sections.
 *
 * Numeric inputs are kept as strings in the form state (empty string = "not answered")
 * and coerced on submit, which keeps `null` round-tripping cleanly through
 * `PUT /profile` / `PUT /preferences/job` without NaN games.
 */
import { z } from 'zod'

import { EMPLOYMENT_TYPES, WORK_MODES } from '@/types/api'
import type {
  EmploymentType,
  JobPreferenceRead,
  JobPreferenceUpdate,
  ProfileRead,
  ProfileUpdate,
  WorkMode,
} from '@/types/api'

/* ------------------------------------------------------------------ */
/* Primitives                                                          */
/* ------------------------------------------------------------------ */

const text = (max: number) => z.string().trim().max(max, `Keep this under ${max} characters`)

const url = (max = 500) =>
  z
    .string()
    .trim()
    .max(max, `Keep this under ${max} characters`)
    .refine((value) => value === '' || /^https?:\/\/\S+$/i.test(value), 'Use a full URL starting with https://')

const email = z
  .string()
  .trim()
  .max(255)
  .refine((value) => value === '' || z.string().email().safeParse(value).success, 'Enter a valid email address')

/** A numeric text field: empty means "unset", anything else must parse inside [min, max]. */
const numeric = (min = 0, max = Number.MAX_SAFE_INTEGER, label = 'number') =>
  z
    .string()
    .trim()
    .refine((value) => {
      if (value === '') return true
      const parsed = Number(value)
      return Number.isFinite(parsed) && parsed >= min && parsed <= max
    }, `Enter a ${label} between ${min} and ${max}`)

export function toNumberOrNull(value: string): number | null {
  const trimmed = value.trim()
  if (trimmed === '') return null
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : null
}

export function fromNumber(value: number | null | undefined): string {
  return value === null || value === undefined ? '' : String(value)
}

function orNull(value: string): string | null {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

/** `true | false | null` <-> a three-way radio group. */
export type TriState = 'yes' | 'no' | 'unknown'

export function toTri(value: boolean | null | undefined): TriState {
  if (value === true) return 'yes'
  if (value === false) return 'no'
  return 'unknown'
}

export function fromTri(value: TriState): boolean | null {
  if (value === 'yes') return true
  if (value === 'no') return false
  return null
}

/* ------------------------------------------------------------------ */
/* Personal                                                            */
/* ------------------------------------------------------------------ */

export const personalSchema = z.object({
  full_name: text(255),
  first_name: text(120),
  last_name: text(120),
  email,
  phone: text(50),
  address: text(500),
  city: text(120),
  state: text(120),
  country: text(120),
  postal_code: text(20),
  linkedin_url: url(),
  github_url: url(),
  portfolio_url: url(),
})

export type PersonalValues = z.infer<typeof personalSchema>

export function personalDefaults(profile: ProfileRead | undefined): PersonalValues {
  return {
    full_name: profile?.full_name ?? '',
    first_name: profile?.first_name ?? '',
    last_name: profile?.last_name ?? '',
    email: profile?.email ?? '',
    phone: profile?.phone ?? '',
    address: profile?.address ?? '',
    city: profile?.city ?? '',
    state: profile?.state ?? '',
    country: profile?.country ?? '',
    postal_code: profile?.postal_code ?? '',
    linkedin_url: profile?.linkedin_url ?? '',
    github_url: profile?.github_url ?? '',
    portfolio_url: profile?.portfolio_url ?? '',
  }
}

export function personalToPayload(values: PersonalValues): ProfileUpdate {
  return {
    full_name: orNull(values.full_name),
    first_name: orNull(values.first_name),
    last_name: orNull(values.last_name),
    email: orNull(values.email),
    phone: orNull(values.phone),
    address: orNull(values.address),
    city: orNull(values.city),
    state: orNull(values.state),
    country: orNull(values.country),
    postal_code: orNull(values.postal_code),
    linkedin_url: orNull(values.linkedin_url),
    github_url: orNull(values.github_url),
    portfolio_url: orNull(values.portfolio_url),
  }
}

/* ------------------------------------------------------------------ */
/* Professional                                                        */
/* ------------------------------------------------------------------ */

const experienceRow = z.object({
  company: text(255),
  title: text(255),
  start: text(40),
  end: text(40),
  description: text(4000),
})

const educationRow = z.object({
  institution: text(255),
  degree: text(255),
  field: text(255),
  start: text(40),
  end: text(40),
  grade: text(40),
})

const certificationRow = z.object({
  name: text(255),
  issuer: text(255),
  year: text(20),
})

const projectRow = z.object({
  name: text(255),
  description: text(2000),
  technologies: z.array(z.string()),
  url: url(),
})

const skillYearsRow = z.object({
  skill: text(120),
  years: numeric(0, 60, 'number of years'),
})

export const professionalSchema = z.object({
  headline: text(255),
  summary: text(5000),
  current_designation: text(255),
  current_company: text(255),
  years_of_experience: numeric(0, 60, 'number of years'),
  current_salary: numeric(0, 1_000_000_000, 'salary'),
  previous_companies: z.array(experienceRow),
  education: z.array(educationRow),
  skills: z.array(z.string()),
  technologies: z.array(z.string()),
  skill_experience: z.array(skillYearsRow),
  certifications: z.array(certificationRow),
  projects: z.array(projectRow),
  achievements: z.array(z.object({ value: text(1000) })),
  languages: z.array(z.string()),
})

export type ProfessionalValues = z.infer<typeof professionalSchema>

function str(value: unknown): string {
  if (value === null || value === undefined) return ''
  return String(value)
}

export function professionalDefaults(profile: ProfileRead | undefined): ProfessionalValues {
  return {
    headline: profile?.headline ?? '',
    summary: profile?.summary ?? '',
    current_designation: profile?.current_designation ?? '',
    current_company: profile?.current_company ?? '',
    years_of_experience: fromNumber(profile?.years_of_experience),
    current_salary: fromNumber(profile?.current_salary),
    previous_companies: (profile?.previous_companies ?? []).map((entry) => ({
      company: str(entry?.company),
      title: str(entry?.title),
      start: str(entry?.start),
      end: str(entry?.end),
      description: str(entry?.description),
    })),
    education: (profile?.education ?? []).map((entry) => ({
      institution: str(entry?.institution),
      degree: str(entry?.degree),
      field: str(entry?.field),
      start: str(entry?.start),
      end: str(entry?.end),
      grade: str(entry?.grade),
    })),
    skills: profile?.skills ?? [],
    technologies: profile?.technologies ?? [],
    skill_experience: Object.entries(profile?.skill_experience ?? {}).map(([skill, years]) => ({
      skill,
      years: fromNumber(typeof years === 'number' ? years : null),
    })),
    certifications: (profile?.certifications ?? []).map((entry) => ({
      name: str(entry?.name),
      issuer: str(entry?.issuer),
      year: str(entry?.year),
    })),
    projects: (profile?.projects ?? []).map((entry) => ({
      name: str(entry?.name),
      description: str(entry?.description),
      technologies: entry?.technologies ?? [],
      url: str(entry?.url),
    })),
    achievements: (profile?.achievements ?? []).map((value) => ({ value: str(value) })),
    languages: profile?.languages ?? [],
  }
}

/** Drop rows the user added but never filled in. */
function nonEmptyRows<T extends Record<string, unknown>>(rows: T[], keys: (keyof T)[]): T[] {
  return rows.filter((row) => keys.some((key) => String(row[key] ?? '').trim() !== ''))
}

export function professionalToPayload(values: ProfessionalValues): ProfileUpdate {
  const skillExperience: Record<string, number> = {}
  for (const row of values.skill_experience) {
    const skill = row.skill.trim()
    const years = toNumberOrNull(row.years)
    if (skill && years !== null) skillExperience[skill] = years
  }

  return {
    headline: orNull(values.headline),
    summary: orNull(values.summary),
    current_designation: orNull(values.current_designation),
    current_company: orNull(values.current_company),
    years_of_experience: toNumberOrNull(values.years_of_experience),
    current_salary: toNumberOrNull(values.current_salary),
    previous_companies: nonEmptyRows(values.previous_companies, ['company', 'title']).map((row) => ({
      company: orNull(row.company),
      title: orNull(row.title),
      start: orNull(row.start),
      end: orNull(row.end),
      description: orNull(row.description),
    })),
    education: nonEmptyRows(values.education, ['institution', 'degree']).map((row) => ({
      institution: orNull(row.institution),
      degree: orNull(row.degree),
      field: orNull(row.field),
      start: orNull(row.start),
      end: orNull(row.end),
      grade: orNull(row.grade),
    })),
    skills: values.skills,
    technologies: values.technologies,
    skill_experience: skillExperience,
    certifications: nonEmptyRows(values.certifications, ['name']).map((row) => ({
      name: orNull(row.name),
      issuer: orNull(row.issuer),
      year: orNull(row.year),
    })),
    projects: nonEmptyRows(values.projects, ['name', 'description']).map((row) => ({
      name: orNull(row.name),
      description: orNull(row.description),
      technologies: row.technologies,
      url: orNull(row.url),
    })),
    achievements: values.achievements.map((row) => row.value.trim()).filter(Boolean),
    languages: values.languages,
  }
}

/* ------------------------------------------------------------------ */
/* Eligibility                                                         */
/* ------------------------------------------------------------------ */

export const eligibilitySchema = z.object({
  work_authorization: z.array(
    z.object({
      country: z
        .string()
        .trim()
        .max(60, 'Use a short country name or ISO code')
        .refine((value) => value !== '', 'Country is required'),
      authorized: z.boolean(),
    }),
  ),
  requires_sponsorship: z.enum(['yes', 'no', 'unknown']),
  willing_to_relocate: z.enum(['yes', 'no', 'unknown']),
})

export type EligibilityValues = z.infer<typeof eligibilitySchema>

export function eligibilityDefaults(profile: ProfileRead | undefined): EligibilityValues {
  return {
    work_authorization: Object.entries(profile?.work_authorization ?? {}).map(([country, authorized]) => ({
      country,
      authorized: Boolean(authorized),
    })),
    requires_sponsorship: toTri(profile?.requires_sponsorship),
    willing_to_relocate: toTri(profile?.willing_to_relocate),
  }
}

export function eligibilityToPayload(values: EligibilityValues): ProfileUpdate {
  const authorization: Record<string, boolean> = {}
  for (const row of values.work_authorization) {
    const country = row.country.trim()
    if (country) authorization[country] = row.authorized
  }
  return {
    work_authorization: authorization,
    requires_sponsorship: fromTri(values.requires_sponsorship),
    willing_to_relocate: fromTri(values.willing_to_relocate),
  }
}

/* ------------------------------------------------------------------ */
/* Job preferences                                                     */
/* ------------------------------------------------------------------ */

export const CURRENCIES = ['INR', 'USD', 'EUR', 'GBP', 'SGD', 'AED', 'AUD', 'CAD'] as const

export const jobPreferenceSchema = z
  .object({
    desired_titles: z.array(z.string()),
    min_salary: numeric(0, 1_000_000_000, 'salary'),
    desired_salary: numeric(0, 1_000_000_000, 'salary'),
    currency: z.string().trim().min(1, 'Pick a currency').max(8),
    notice_period_days: numeric(0, 365, 'number of days'),
    preferred_locations: z.array(z.string()),
    work_modes: z.array(z.enum(WORK_MODES)),
    employment_types: z.array(z.enum(EMPLOYMENT_TYPES)),
    experience_min: numeric(0, 60, 'number of years'),
    experience_max: numeric(0, 60, 'number of years'),
    preferred_technologies: z.array(z.string()),
    excluded_keywords: z.array(z.string()),
    min_match_score: z.number().min(0).max(100),
    only_posted_within_hours: numeric(1, 24 * 90, 'number of hours'),
  })
  .superRefine((values, ctx) => {
    const expMin = toNumberOrNull(values.experience_min)
    const expMax = toNumberOrNull(values.experience_max)
    if (expMin !== null && expMax !== null && expMin > expMax) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['experience_max'],
        message: 'Maximum experience must be at least the minimum',
      })
    }
    const minSalary = toNumberOrNull(values.min_salary)
    const desiredSalary = toNumberOrNull(values.desired_salary)
    if (minSalary !== null && desiredSalary !== null && minSalary > desiredSalary) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['desired_salary'],
        message: 'Target salary should be at least your minimum',
      })
    }
  })

export type JobPreferenceValues = z.infer<typeof jobPreferenceSchema>

export function jobPreferenceDefaults(preferences: JobPreferenceRead | undefined): JobPreferenceValues {
  return {
    desired_titles: preferences?.desired_titles ?? [],
    min_salary: fromNumber(preferences?.min_salary),
    desired_salary: fromNumber(preferences?.desired_salary),
    currency: preferences?.currency ?? 'INR',
    notice_period_days: fromNumber(preferences?.notice_period_days),
    preferred_locations: preferences?.preferred_locations ?? [],
    work_modes: (preferences?.work_modes ?? []) as WorkMode[],
    employment_types: (preferences?.employment_types ?? []) as EmploymentType[],
    experience_min: fromNumber(preferences?.experience_min),
    experience_max: fromNumber(preferences?.experience_max),
    preferred_technologies: preferences?.preferred_technologies ?? [],
    excluded_keywords: preferences?.excluded_keywords ?? [],
    min_match_score: preferences?.min_match_score ?? 75,
    only_posted_within_hours: fromNumber(preferences?.only_posted_within_hours),
  }
}

export function jobPreferenceToPayload(values: JobPreferenceValues): JobPreferenceUpdate {
  return {
    desired_titles: values.desired_titles,
    min_salary: toNumberOrNull(values.min_salary),
    desired_salary: toNumberOrNull(values.desired_salary),
    currency: values.currency,
    notice_period_days: toNumberOrNull(values.notice_period_days),
    preferred_locations: values.preferred_locations,
    work_modes: values.work_modes,
    employment_types: values.employment_types,
    experience_min: toNumberOrNull(values.experience_min),
    experience_max: toNumberOrNull(values.experience_max),
    preferred_technologies: values.preferred_technologies,
    excluded_keywords: values.excluded_keywords,
    min_match_score: values.min_match_score,
    only_posted_within_hours: toNumberOrNull(values.only_posted_within_hours),
  }
}

/* ------------------------------------------------------------------ */
/* Completeness labels                                                 */
/* ------------------------------------------------------------------ */

/** Human labels for the `missing_fields` keys returned by `compute_completeness`. */
export const MISSING_FIELD_LABELS: Record<string, string> = {
  full_name: 'Full name',
  email: 'Email',
  phone: 'Phone',
  city: 'City',
  country: 'Country',
  linkedin_url: 'LinkedIn URL',
  current_designation: 'Current designation',
  years_of_experience: 'Years of experience',
  skills: 'Skills',
  education: 'Education',
  summary: 'Professional summary',
  work_authorization: 'Work authorization',
  requires_sponsorship: 'Sponsorship requirement',
  notice_period_days: 'Notice period',
  desired_salary: 'Target salary',
}

export type ProfileTab = 'personal' | 'professional' | 'eligibility' | 'preferences'

/** Which tab a missing field lives on, so the hint can deep-link to it. */
export const MISSING_FIELD_TABS: Record<string, ProfileTab> = {
  full_name: 'personal',
  email: 'personal',
  phone: 'personal',
  city: 'personal',
  country: 'personal',
  linkedin_url: 'personal',
  current_designation: 'professional',
  years_of_experience: 'professional',
  skills: 'professional',
  education: 'professional',
  summary: 'professional',
  work_authorization: 'eligibility',
  requires_sponsorship: 'eligibility',
  notice_period_days: 'preferences',
  desired_salary: 'preferences',
}
