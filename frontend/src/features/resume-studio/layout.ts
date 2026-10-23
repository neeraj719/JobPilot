/**
 * The neutral resume layout — a TypeScript mirror of `backend/app/modules/resumes/render.py::build_layout`.
 *
 * The live preview draws exactly what the PDF/DOCX exporters draw: same section order,
 * same date format, same "Title | Company" entry lines, same skipped empty sections. If
 * you change one, change the other (the backend test suite proves the exports round-trip).
 */
import { SECTION_KEYS, SECTION_LABELS, type ResumeTemplate, type SectionKey, type StudioResume } from './types'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const PRESENT_RE = /^(?:present|current|currently|now|to\s?date|till\s?date|ongoing)$/i
const BULLET_SPLIT_RE = /\n+|\s+[•▪●◦]\s+/
const BULLET_MARKER_RE = /^\s*(?:[-*•▪●◦–—·]|\d+[.)])\s*/

export function formatDate(value: string | null | undefined, fmt: ResumeTemplate['date_format'] = 'MMM YYYY'): string {
  const text = (value ?? '').trim()
  if (!text) return ''
  if (PRESENT_RE.test(text)) return 'Present'
  let year: number | null = null
  let month: number | null = null
  let m: RegExpMatchArray | null
  if ((m = text.match(/^(\d{4})-(\d{1,2})(?:-\d{1,2})?$/))) {
    year = Number(m[1])
    month = Number(m[2])
  } else if ((m = text.match(/^(\d{1,2})\/(\d{4})$/))) {
    month = Number(m[1])
    year = Number(m[2])
  } else if ((m = text.match(/^([A-Za-z]{3,9})\.?\s+(\d{4})$/))) {
    const index = MONTHS.findIndex((name) => name.toLowerCase() === m![1].slice(0, 3).toLowerCase())
    month = index >= 0 ? index + 1 : null
    year = Number(m[2])
  } else if (/^\d{4}$/.test(text)) {
    return text
  }
  if (year === null || month === null || month < 1 || month > 12) return text
  if (fmt === 'YYYY') return String(year)
  if (fmt === 'MM/YYYY') return `${String(month).padStart(2, '0')}/${year}`
  return `${MONTHS[month - 1]} ${year}`
}

export function dateRange(start: string | null | undefined, end: string | null | undefined, fmt: ResumeTemplate['date_format']): string {
  const a = formatDate(start, fmt)
  const b = formatDate(end, fmt)
  if (a && b) return `${a} – ${b}`
  return a || b
}

export function displayUrl(url: string | null | undefined): string {
  return (url ?? '').trim().replace(/^https?:\/\//i, '').replace(/^www\./i, '').replace(/\/+$/, '')
}

/** Bullet lines of a description (markers stripped, blanks dropped) — same as the backend. */
export function splitBullets(description: string | null | undefined): string[] {
  if (!description || !description.trim()) return []
  return description
    .split(BULLET_SPLIT_RE)
    .map((line) => line.replace(BULLET_MARKER_RE, '').trim())
    .filter(Boolean)
}

const clean = (value: unknown) => String(value ?? '').split(/\s+/).filter(Boolean).join(' ')
const join = (parts: unknown[], sep = ' | ') => parts.map(clean).filter(Boolean).join(sep)

export interface LayoutEntry {
  title: string
  detail: string
  dates: string
  bullets: string[]
  meta: string
}

export interface LayoutSection {
  key: SectionKey
  label: string
  paragraph: string
  inline: string
  bullets: string[]
  entries: LayoutEntry[]
}

export interface ResumeLayout {
  name: string
  headline: string
  contacts: string[]
  sections: LayoutSection[]
}

export function effectiveOrder(order: SectionKey[] | undefined, template: ResumeTemplate): SectionKey[] {
  const own = (order ?? []).filter((key) => (SECTION_KEYS as readonly string[]).includes(key))
  return own.length ? own : template.section_order
}

function techsNotIn(technologies: string[] | undefined, text: string): string[] {
  const lowered = (text ?? '').toLowerCase()
  return (technologies ?? []).map(clean).filter((t) => t && !lowered.includes(t.toLowerCase()))
}

export function buildLayout(data: Partial<StudioResume>, template: ResumeTemplate): ResumeLayout {
  const fmt = template.date_format
  const contacts = [
    clean(data.email),
    clean(data.phone),
    clean(data.location),
    displayUrl(data.links?.linkedin),
    displayUrl(data.links?.github),
    displayUrl(data.links?.portfolio),
  ].filter(Boolean)

  const sections: LayoutSection[] = []
  for (const key of effectiveOrder(data.section_order, template)) {
    const section: LayoutSection = { key, label: SECTION_LABELS[key], paragraph: '', inline: '', bullets: [], entries: [] }
    if (key === 'summary') section.paragraph = clean(data.summary)
    else if (key === 'skills') {
      const skills = (data.skills ?? []).map(clean).filter(Boolean)
      if (template.skills_style === 'bullets') section.bullets = skills
      else section.inline = skills.join(', ')
    } else if (key === 'experience') {
      for (const item of data.experience ?? []) {
        if (!item.title && !item.company) continue
        const extra = techsNotIn(item.technologies, item.description ?? '')
        section.entries.push({
          title: join([item.title, item.company]),
          detail: clean(item.location),
          dates: dateRange(item.start, item.end, fmt),
          bullets: splitBullets(item.description),
          meta: extra.length ? `Technologies: ${extra.join(', ')}` : '',
        })
      }
    } else if (key === 'projects') {
      for (const item of data.projects ?? []) {
        if (!item.name && !item.description) continue
        const techs = techsNotIn(item.technologies, item.description ?? '')
        section.entries.push({
          title: clean(item.name) || 'Project',
          detail: displayUrl(item.url),
          dates: '',
          bullets: splitBullets(item.description),
          meta: techs.length ? `Technologies: ${techs.join(', ')}` : '',
        })
      }
    } else if (key === 'education') {
      for (const item of data.education ?? []) {
        if (!item.institution && !item.degree) continue
        let degree = clean(item.degree)
        const field = clean(item.field)
        if (degree && field && !degree.toLowerCase().includes(field.toLowerCase())) degree = `${degree} in ${field}`
        section.entries.push({
          title: join([degree || field, item.institution]),
          detail: '',
          dates: dateRange(item.start, item.end, fmt),
          bullets: [],
          meta: '',
        })
      }
    } else if (key === 'certifications') {
      section.bullets = (data.certifications ?? []).filter((c) => c.name).map((c) => join([c.name, c.issuer, c.year]))
    } else if (key === 'achievements') {
      section.bullets = (data.achievements ?? []).map(clean).filter(Boolean)
    } else if (key === 'languages') {
      section.inline = (data.languages ?? []).map(clean).filter(Boolean).join(', ')
    }
    if (section.paragraph || section.inline || section.bullets.length || section.entries.length) sections.push(section)
  }

  return { name: clean(data.name) || 'Your Name', headline: clean(data.headline), contacts, sections }
}

/** The line under the name (the two-line header puts the headline first on it). */
export function contactLine(layout: ResumeLayout, template: ResumeTemplate): string {
  const parts = [...layout.contacts]
  if (layout.headline && template.header_layout === 'two-line') parts.unshift(layout.headline)
  return parts.join(' | ')
}
