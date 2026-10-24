/**
 * Resume studio types — mirror `backend/app/modules/resumes/{schemas,templates}.py`.
 *
 * Kept here rather than in `src/types/api.ts` (shared file, plan §3). `StudioResume`
 * extends the shared `ParsedResume` with the additive studio fields.
 */
import type { ParsedResume, ResumeChangeSource, ResumeKind, ResumeRead } from '@/types/api'

export const SECTION_KEYS = [
  'summary',
  'skills',
  'experience',
  'projects',
  'education',
  'certifications',
  'achievements',
  'languages',
] as const
export type SectionKey = (typeof SECTION_KEYS)[number]

export const SECTION_LABELS: Record<SectionKey, string> = {
  summary: 'Summary',
  skills: 'Skills',
  experience: 'Experience',
  projects: 'Projects',
  education: 'Education',
  certifications: 'Certifications',
  achievements: 'Achievements',
  languages: 'Languages',
}

export interface StudioExperience {
  company?: string | null
  title?: string | null
  start?: string | null
  end?: string | null
  description?: string | null
  technologies: string[]
  location?: string | null
  url?: string | null
}

export interface StudioProject {
  name?: string | null
  description?: string | null
  technologies: string[]
  location?: string | null
  url?: string | null
}

/** `ParsedResume` plus the resume-studio fields (all optional on the wire). */
export interface StudioResume extends Omit<ParsedResume, 'experience' | 'projects'> {
  experience: StudioExperience[]
  projects: StudioProject[]
  headline?: string | null
  location?: string | null
  achievements?: string[]
  languages?: string[]
  section_order?: SectionKey[]
}

export interface TemplateFonts {
  css: string
  pdf: string
  pdf_bold: string
  pdf_italic: string
  docx: string
}

export interface ResumeTemplate {
  id: string
  name: string
  description: string
  section_order: SectionKey[]
  fonts: TemplateFonts
  heading_fonts: TemplateFonts
  sizes: { name: number; headline: number; heading: number; body: number; small: number }
  spacing: {
    margin_in: number
    line_height: number
    section_before: number
    section_after: number
    entry_gap: number
    bullet_indent: number
  }
  date_format: 'MMM YYYY' | 'MM/YYYY' | 'YYYY'
  accent: string
  header_layout: 'centered' | 'left' | 'two-line'
  heading_style: 'caps-rule' | 'accent-rule' | 'bold'
  skills_style: 'inline' | 'bullets'
  bullet: string
}

export interface ResumeDraftRead {
  resume_id: string
  draft_data: StudioResume | null
  draft_saved_at: string | null
  current_version: number
}

export type DiffKind = 'added' | 'removed' | 'changed'

export interface DiffField {
  path: string
  label: string | null
  before: unknown
  after: unknown
  kind: DiffKind
}

export interface ResumeDiff {
  fields: DiffField[]
  summary: { added: number; removed: number; changed: number }
  description: string
  before_label: string | null
  after_label: string | null
}

export interface HistoryItem {
  id: string
  resume_id: string
  resume_name: string
  resume_kind: ResumeKind
  resume_archived: boolean
  version_number: number
  is_current: boolean
  note: string | null
  change_source: ResumeChangeSource
  change_summary: string
  created_at: string
}

export interface HistoryPage {
  items: HistoryItem[]
  next_cursor: string | null
}

export interface HistoryParams {
  resume_id?: string
  change_source?: ResumeChangeSource
}

export interface ResumeSummary {
  total: number
  archived: number
  by_kind: Record<ResumeKind, number>
  recently_edited: {
    id: string
    name: string
    kind: ResumeKind
    target_role: string | null
    current_version: number
    has_draft: boolean
    updated_at: string
  }[]
  drafts_pending: number
  ai_versions_to_review: number
  default_resume_id: string | null
}

export interface BulletChecks {
  kept_details: boolean
  no_new_numbers: boolean
  no_new_claims: boolean
}

export interface BulletCandidate {
  text: string
  source: 'rule' | 'ai'
  checks: BulletChecks
  has_placeholder: boolean
}

export interface BulletSuggestions {
  original: string
  candidates: BulletCandidate[]
  note: string | null
  ai_used: boolean
  /** The model that answered (`null` when only the rules ran). */
  ai_provider?: string | null
  ai_model?: string | null
}

export type WritingField = 'summary' | 'bullet' | 'headline' | 'achievement' | 'description'

export interface ImprovedText {
  text: string
  changed: boolean
  source: 'rule' | 'ai'
  reason: string | null
  ai_provider?: string | null
  ai_model?: string | null
}

export interface SummaryDraft {
  text: string | null
  source: 'rule' | 'ai'
  reason: string | null
  ai_provider?: string | null
  ai_model?: string | null
}

export type ExportFormat = 'pdf' | 'docx'

/** A resume as the studio reads it (`parsed_data` typed with the studio fields). */
export type StudioResumeRead = Omit<ResumeRead, 'parsed_data'> & { parsed_data: Partial<StudioResume> }
