/**
 * ATS optimizer types — mirror `backend/app/modules/ats/schemas.py`.
 * Kept in the feature (not `types/api.ts`) per the resume-studio plan.
 */
import type { ISODateString, ResumeRead, UUID, WorkMode } from '@/types/api'

export const JOB_TARGET_STATUSES = [
  'SAVED',
  'PREPARING',
  'READY',
  'APPLIED',
  'INTERVIEW',
  'OFFER',
  'REJECTED',
  'ARCHIVED',
] as const
export type JobTargetStatus = (typeof JOB_TARGET_STATUSES)[number]

export type JdSource = 'PASTED' | 'UPLOADED' | 'URL' | 'BOARD' | 'JOB'
export type AtsAnalysisStatus = 'PENDING' | 'RUNNING' | 'DONE' | 'FAILED'
export type SuggestionKind =
  | 'ADD_SKILL'
  | 'REPLACE_BULLET'
  | 'REPLACE_SUMMARY'
  | 'REORDER_SECTION'
  | 'ADD_KEYWORD_CONTEXT'
  | 'MANUAL'
export type SuggestionStatus = 'PROPOSED' | 'APPLIED' | 'IGNORED' | 'EDITED'
export type Confidence = 'high' | 'medium' | 'low'

export interface StructuredJD {
  title: string | null
  company: string | null
  location: string | null
  work_mode: WorkMode | null
  seniority: string | null
  years_min: number | null
  years_max: number | null
  required_skills: string[]
  preferred_skills: string[]
  responsibilities: string[]
  qualifications: string[]
  preferred_qualifications: string[]
  education: string[]
  degree_required: boolean
  keywords: string[]
  deadline: ISODateString | null
  ai_polished: boolean
  notes: string[]
}

export interface JdParseResult {
  source: JdSource
  confidence: Confidence
  title: string | null
  company: string | null
  location: string | null
  url: string | null
  text: string
  structured: StructuredJD
  warnings: string[]
}

export interface BoardPostingRef {
  vendor: 'GREENHOUSE' | 'LEVER' | 'ASHBY' | 'SMARTRECRUITERS'
  token: string
  external_id: string
}

export interface OpenRole {
  title: string
  location: string | null
  url: string | null
  external_id: string
  vendor: BoardPostingRef['vendor']
  token: string
  work_mode: WorkMode | null
  posted_at: ISODateString | null
}

export interface CompanyLookupResult {
  query: string
  role: string | null
  company: { id: UUID | null; name: string; ats_type: string | null; board_url: string | null; token: string | null } | null
  method: 'REGISTRY' | 'KNOWN' | 'DETECTED' | 'NONE'
  supported: boolean
  total_open: number
  open_roles: OpenRole[]
  matching_roles: OpenRole[]
  message: string
}

export interface MethodologyCategory {
  key: string
  label: string
  weight: number
  description: string
}

export interface Methodology {
  version: string
  categories: MethodologyCategory[]
  weight_bounds: { min: number; max: number }
  disclaimer: string
  notes: string[]
}

export interface CategoryScore {
  key: string
  label: string
  score: number | null
  weight: number
  applicable: boolean
  evidence: string[]
}

export interface KeywordHit {
  keyword: string
  kind: 'skill' | 'keyword' | 'title'
  required: boolean | null
  where: string[]
}

export interface KeywordMiss {
  keyword: string
  kind: 'skill' | 'keyword' | 'title'
  required: boolean | null
  where_it_fits: string | null
  evidenced: boolean
}

export interface WeakItem {
  path: string
  text: string
  reason: string
}

export interface ParseRisk {
  code: string
  message: string
  severity: 'high' | 'medium' | 'low'
}

export interface Suggestion {
  id: UUID
  ordinal: number
  kind: SuggestionKind
  title: string
  rationale: string
  target_path: string | null
  before: string | null
  after: string | null
  safe: boolean
  requires_confirmation: boolean
  confirmation_label: string | null
  estimated_gain: number
  status: SuggestionStatus
  applied_version: number | null
  checks: Record<string, unknown>
}

export interface SnapshotSummary {
  id: UUID | null
  title: string | null
  company: string | null
  source: JdSource | null
  url: string | null
  created_at: ISODateString | null
}

export interface AtsAnalysis {
  id: UUID
  resume_id: UUID
  resume_name: string | null
  resume_version: number
  is_current: boolean
  job_target_id: UUID | null
  snapshot_id: UUID | null
  previous_analysis_id: UUID | null
  previous_score: number | null
  status: AtsAnalysisStatus
  progress: number
  error: string | null
  overall_score: number | null
  category_scores: CategoryScore[]
  matched_keywords: KeywordHit[]
  missing_keywords: KeywordMiss[]
  weak_items: WeakItem[]
  parse_risks: ParseRisk[]
  methodology_version: string
  weights: Record<string, number>
  ai_provider: string | null
  ai_model: string | null
  duration_ms: number | null
  completed_at: ISODateString | null
  created_at: ISODateString
  jd: SnapshotSummary
  suggestions: Suggestion[]
  disclaimer: string
}

export interface AnalysisListItem {
  id: UUID
  resume_id: UUID
  resume_name: string | null
  resume_version: number
  job_target_id: UUID | null
  status: AtsAnalysisStatus
  overall_score: number | null
  jd_title: string | null
  jd_company: string | null
  created_at: ISODateString
}

export interface JdInput {
  text?: string
  title?: string | null
  company?: string | null
  url?: string | null
  source?: JdSource
  structured?: StructuredJD
  snapshot_id?: UUID
  job_target_id?: UUID
  job_id?: UUID
}

export interface AnalysisCreate {
  resume_id: UUID
  jd: JdInput
  weights?: Record<string, number>
}

export interface AppliedItem {
  id: UUID
  kind: SuggestionKind
  title: string
  edited: boolean
}

export interface SkippedItem {
  id: UUID
  reason: string
}

export interface ApplyResult {
  resume: ResumeRead
  analysis: AtsAnalysis
  previous_analysis_id: UUID
  previous_score: number | null
  applied: AppliedItem[]
  skipped: SkippedItem[]
  restorable_version: number | null
}

export interface Explanation {
  suggestion_id: UUID | null
  what: string
  why: string
  evidence: string[]
  source: 'AI' | 'USER' | 'SYSTEM'
}

export interface AutoOptimizeResult {
  mode: 'new_resume' | 'new_version'
  resume: ResumeRead
  source_resume_id: UUID
  analysis: AtsAnalysis
  previous_score: number | null
  applied: AppliedItem[]
  skipped: SkippedItem[]
  explanations: Explanation[]
}

export interface UndoResult {
  resume: ResumeRead
  analysis: AtsAnalysis
  restored_version: number
}

export interface ResumeRef {
  id: UUID
  name: string
  kind: string
  current_version: number
  archived: boolean
}

export interface SnapshotRead {
  id: UUID
  job_target_id: UUID | null
  source: JdSource
  url: string | null
  fetched_at: ISODateString | null
  title: string | null
  company: string | null
  raw_text: string
  structured: StructuredJD
  text_sha256: string
  changed_from_previous: boolean
  changes: {
    added_required?: string[]
    removed_required?: string[]
    added_preferred?: string[]
    removed_preferred?: string[]
  }
  created_at: ISODateString
}

export interface JobTarget {
  id: UUID
  company_name: string
  company_id: UUID | null
  role_title: string
  job_url: string | null
  location: string | null
  work_mode: WorkMode | null
  required_skills: string[]
  deadline: ISODateString | null
  status: JobTargetStatus
  notes: string | null
  follow_up_at: ISODateString | null
  source_resume: ResumeRef | null
  tailored_resume: ResumeRef | null
  tailored_resume_version: number | null
  submitted_resume_version: number | null
  application_id: UUID | null
  job_id: UUID | null
  latest_snapshot_id: UUID | null
  last_analysis_id: UUID | null
  last_score: number | null
  last_analyzed_at: ISODateString | null
  missing_requirements: string[]
  created_at: ISODateString
  updated_at: ISODateString
}

export interface ActivityItem {
  at: ISODateString
  kind: 'snapshot' | 'analysis' | 'status' | 'tailored' | 'note' | 'created' | 'applied'
  message: string
  ref_id: UUID | null
}

export interface JobTargetDetail extends JobTarget {
  latest_snapshot: SnapshotRead | null
  snapshots: SnapshotRead[]
  last_analysis: AtsAnalysis | null
  activity: ActivityItem[]
}

export interface SnapshotCreate {
  source: 'PASTED' | 'URL' | 'BOARD'
  text?: string
  url?: string
  board?: BoardPostingRef
  title?: string
  structured?: StructuredJD
  use_ai?: boolean
}

export interface TargetCreate {
  company_name?: string
  role_title?: string
  job_url?: string | null
  location?: string | null
  work_mode?: WorkMode | null
  deadline?: ISODateString | null
  notes?: string | null
  follow_up_at?: ISODateString | null
  source_resume_id?: UUID | null
  job_id?: UUID | null
  status?: JobTargetStatus
  jd?: SnapshotCreate
  /** Save an optimizer analysis as a target: reuse its JD snapshot and link the analysis. */
  snapshot_id?: UUID
  analysis_id?: UUID
}

export type TargetUpdate = Partial<Omit<TargetCreate, 'jd' | 'job_id' | 'snapshot_id' | 'analysis_id'>> & { application_id?: UUID | null }

export interface SnapshotResult {
  snapshot: SnapshotRead
  created: boolean
  target: JobTarget
}

export interface TailorResult {
  target: JobTarget
  resume: ResumeRead
  analysis: AtsAnalysis
  source_analysis_id: UUID
  source_score: number | null
  explanations: Explanation[]
}

export interface FieldChange {
  path: string
  before: unknown
  after: unknown
  kind: 'added' | 'removed' | 'changed'
}

export interface CompareSide {
  id: UUID
  name: string
  version: number
  parsed_data: Record<string, unknown>
  score: number | null
}

export interface CompareResult {
  source: CompareSide
  tailored: CompareSide
  fields: FieldChange[]
  summary: { added: number; removed: number; changed: number }
  explanations: Explanation[]
  diff_provider: 'ats' | 'builder'
}

export interface AtsSummary {
  total_targets: number
  targets_by_status: Record<JobTargetStatus, number>
  recent_analyses: AnalysisListItem[]
  in_progress: JobTarget[]
  upcoming: JobTarget[]
}

export interface TargetListParams {
  status?: JobTargetStatus[]
  company?: string
  search?: string
  page?: number
  page_size?: number
}
