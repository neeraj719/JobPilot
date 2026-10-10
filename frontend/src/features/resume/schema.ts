/**
 * Form schema for the "Extracted information" editor.
 *
 * It mirrors `ai.schemas.ParsedResume` exactly — the backend ignores unknown keys, so a
 * field that is not in that model would silently vanish on save. Numbers travel as
 * strings and are coerced in `toParsedResume`.
 */
import { z } from 'zod'

import type { ParsedResume } from '@/types/api'

const text = (max: number) => z.string().trim().max(max, `Keep this under ${max} characters`)

export const parsedResumeSchema = z.object({
  name: text(255),
  email: z
    .string()
    .trim()
    .max(255)
    .refine((value) => value === '' || z.string().email().safeParse(value).success, 'Enter a valid email address'),
  phone: text(50),
  summary: text(5000),
  total_experience_years: z
    .string()
    .trim()
    .refine((value) => {
      if (value === '') return true
      const parsed = Number(value)
      return Number.isFinite(parsed) && parsed >= 0 && parsed <= 60
    }, 'Enter a number of years between 0 and 60'),
  skills: z.array(z.string()),
  experience: z.array(
    z.object({
      company: text(255),
      title: text(255),
      start: text(40),
      end: text(40),
      description: text(4000),
      technologies: z.array(z.string()),
    }),
  ),
  education: z.array(
    z.object({
      institution: text(255),
      degree: text(255),
      field: text(255),
      start: text(40),
      end: text(40),
    }),
  ),
  projects: z.array(
    z.object({
      name: text(255),
      description: text(2000),
      technologies: z.array(z.string()),
    }),
  ),
  certifications: z.array(
    z.object({
      name: text(255),
      issuer: text(255),
      year: text(20),
    }),
  ),
  linkedin: text(500),
  github: text(500),
  portfolio: text(500),
})

export type ParsedResumeValues = z.infer<typeof parsedResumeSchema>

function str(value: unknown): string {
  return value === null || value === undefined ? '' : String(value)
}

export function parsedResumeDefaults(data: ParsedResume | Record<string, never> | undefined): ParsedResumeValues {
  const parsed = (data ?? {}) as Partial<ParsedResume>
  return {
    name: str(parsed.name),
    email: str(parsed.email),
    phone: str(parsed.phone),
    summary: str(parsed.summary),
    total_experience_years: str(parsed.total_experience_years),
    skills: parsed.skills ?? [],
    experience: (parsed.experience ?? []).map((entry) => ({
      company: str(entry?.company),
      title: str(entry?.title),
      start: str(entry?.start),
      end: str(entry?.end),
      description: str(entry?.description),
      technologies: entry?.technologies ?? [],
    })),
    education: (parsed.education ?? []).map((entry) => ({
      institution: str(entry?.institution),
      degree: str(entry?.degree),
      field: str(entry?.field),
      start: str(entry?.start),
      end: str(entry?.end),
    })),
    projects: (parsed.projects ?? []).map((entry) => ({
      name: str(entry?.name),
      description: str(entry?.description),
      technologies: entry?.technologies ?? [],
    })),
    certifications: (parsed.certifications ?? []).map((entry) => ({
      name: str(entry?.name),
      issuer: str(entry?.issuer),
      year: str(entry?.year),
    })),
    linkedin: str(parsed.links?.linkedin),
    github: str(parsed.links?.github),
    portfolio: str(parsed.links?.portfolio),
  }
}

function orNull(value: string): string | null {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

export function toParsedResume(values: ParsedResumeValues): ParsedResume {
  const years = values.total_experience_years.trim()
  return {
    name: orNull(values.name),
    email: orNull(values.email),
    phone: orNull(values.phone),
    summary: orNull(values.summary),
    total_experience_years: years === '' ? null : Number(years),
    skills: values.skills,
    experience: values.experience
      .filter((entry) => entry.company.trim() || entry.title.trim())
      .map((entry) => ({
        company: orNull(entry.company),
        title: orNull(entry.title),
        start: orNull(entry.start),
        end: orNull(entry.end),
        description: orNull(entry.description),
        technologies: entry.technologies,
      })),
    education: values.education
      .filter((entry) => entry.institution.trim() || entry.degree.trim())
      .map((entry) => ({
        institution: orNull(entry.institution),
        degree: orNull(entry.degree),
        field: orNull(entry.field),
        start: orNull(entry.start),
        end: orNull(entry.end),
      })),
    projects: values.projects
      .filter((entry) => entry.name.trim() || entry.description.trim())
      .map((entry) => ({
        name: orNull(entry.name),
        description: orNull(entry.description),
        technologies: entry.technologies,
      })),
    certifications: values.certifications
      .filter((entry) => entry.name.trim())
      .map((entry) => ({
        name: orNull(entry.name),
        issuer: orNull(entry.issuer),
        year: orNull(entry.year),
      })),
    links: {
      linkedin: orNull(values.linkedin),
      github: orNull(values.github),
      portfolio: orNull(values.portfolio),
    },
  }
}
