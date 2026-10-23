/**
 * Editor form model (react-hook-form + zod) and its mapping to/from `StudioResume`.
 *
 * Bullets are edited as a list and stored as newline-separated `description` text — the
 * backend recommendations and "apply suggestions" read them that way.
 */
import { z } from 'zod'

import { splitBullets } from './layout'
import { SECTION_KEYS, type SectionKey, type StudioResume } from './types'

const text = (max: number) => z.string().max(max, `Keep this under ${max} characters`)
const bullet = z.object({ text: text(600) })

export const editorSchema = z.object({
  name: text(255),
  headline: text(255),
  email: z
    .string()
    .trim()
    .max(255)
    .refine((value) => value === '' || z.string().email().safeParse(value).success, 'Enter a valid email address'),
  phone: text(50),
  location: text(255),
  summary: text(3000),
  total_experience_years: z
    .string()
    .trim()
    .refine((value) => value === '' || (Number.isFinite(Number(value)) && Number(value) >= 0 && Number(value) <= 60), 'Between 0 and 60'),
  linkedin: text(500),
  github: text(500),
  portfolio: text(500),
  skills: z.array(z.string().max(80)).max(150),
  experience: z
    .array(
      z.object({
        company: text(255),
        title: text(255),
        start: text(40),
        end: text(40),
        location: text(255),
        url: text(500),
        bullets: z.array(bullet).max(30),
        technologies: z.array(z.string().max(80)),
      }),
    )
    .max(40),
  projects: z
    .array(
      z.object({
        name: text(255),
        url: text(500),
        bullets: z.array(bullet).max(20),
        technologies: z.array(z.string().max(80)),
      }),
    )
    .max(40),
  education: z
    .array(z.object({ institution: text(255), degree: text(255), field: text(255), start: text(40), end: text(40) }))
    .max(20),
  certifications: z.array(z.object({ name: text(255), issuer: text(255), year: text(20) })).max(40),
  achievements: z.array(bullet).max(40),
  languages: z.array(z.string().max(80)).max(30),
  section_order: z.array(z.enum(SECTION_KEYS)),
})

export type EditorValues = z.infer<typeof editorSchema>

const s = (value: unknown) => (value === null || value === undefined ? '' : String(value))
const orNull = (value: string) => (value.trim() === '' ? null : value.trim())
const bullets = (description: string | null | undefined) => splitBullets(description).map((line) => ({ text: line }))
const joinBullets = (items: { text: string }[]) =>
  items
    .map((item) => item.text.trim())
    .filter(Boolean)
    .join('\n') || null

export function toEditorValues(data: Partial<StudioResume> | null | undefined): EditorValues {
  const d = data ?? {}
  return {
    name: s(d.name),
    headline: s(d.headline),
    email: s(d.email),
    phone: s(d.phone),
    location: s(d.location),
    summary: s(d.summary),
    total_experience_years: s(d.total_experience_years),
    linkedin: s(d.links?.linkedin),
    github: s(d.links?.github),
    portfolio: s(d.links?.portfolio),
    skills: [...(d.skills ?? [])],
    experience: (d.experience ?? []).map((e) => ({
      company: s(e.company),
      title: s(e.title),
      start: s(e.start),
      end: s(e.end),
      location: s(e.location),
      url: s(e.url),
      bullets: bullets(e.description),
      technologies: [...(e.technologies ?? [])],
    })),
    projects: (d.projects ?? []).map((p) => ({
      name: s(p.name),
      url: s(p.url),
      bullets: bullets(p.description),
      technologies: [...(p.technologies ?? [])],
    })),
    education: (d.education ?? []).map((e) => ({
      institution: s(e.institution),
      degree: s(e.degree),
      field: s(e.field),
      start: s(e.start),
      end: s(e.end),
    })),
    certifications: (d.certifications ?? []).map((c) => ({ name: s(c.name), issuer: s(c.issuer), year: s(c.year) })),
    achievements: (d.achievements ?? []).map((a) => ({ text: a })),
    languages: [...(d.languages ?? [])],
    section_order: (d.section_order ?? []).filter((k): k is SectionKey => (SECTION_KEYS as readonly string[]).includes(k)),
  }
}

export function toStudioResume(values: EditorValues): StudioResume {
  const years = values.total_experience_years.trim()
  return {
    name: orNull(values.name),
    headline: orNull(values.headline),
    email: orNull(values.email),
    phone: orNull(values.phone),
    location: orNull(values.location),
    summary: orNull(values.summary),
    total_experience_years: years === '' ? null : Number(years),
    links: { linkedin: orNull(values.linkedin), github: orNull(values.github), portfolio: orNull(values.portfolio) },
    skills: values.skills.map((v) => v.trim()).filter(Boolean),
    experience: values.experience
      .filter((e) => e.company.trim() || e.title.trim())
      .map((e) => ({
        company: orNull(e.company),
        title: orNull(e.title),
        start: orNull(e.start),
        end: orNull(e.end),
        location: orNull(e.location),
        url: orNull(e.url),
        description: joinBullets(e.bullets),
        technologies: e.technologies,
      })),
    projects: values.projects
      .filter((p) => p.name.trim() || p.bullets.some((b) => b.text.trim()))
      .map((p) => ({ name: orNull(p.name), url: orNull(p.url), description: joinBullets(p.bullets), technologies: p.technologies })),
    education: values.education
      .filter((e) => e.institution.trim() || e.degree.trim())
      .map((e) => ({
        institution: orNull(e.institution),
        degree: orNull(e.degree),
        field: orNull(e.field),
        start: orNull(e.start),
        end: orNull(e.end),
      })),
    certifications: values.certifications
      .filter((c) => c.name.trim())
      .map((c) => ({ name: orNull(c.name), issuer: orNull(c.issuer), year: orNull(c.year) })),
    achievements: values.achievements.map((a) => a.text.trim()).filter(Boolean),
    languages: values.languages.map((v) => v.trim()).filter(Boolean),
    section_order: values.section_order,
  }
}

export const EMPTY_RESUME: StudioResume = {
  skills: [],
  experience: [],
  education: [],
  projects: [],
  certifications: [],
  achievements: [],
  languages: [],
  section_order: [],
  links: {},
}
