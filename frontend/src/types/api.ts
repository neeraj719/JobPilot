/**
 * TypeScript mirror of the backend contract.
 *
 * Enums mirror `backend/app/models/enums.py` one-for-one; response shapes mirror
 * `docs/CONTRACTS.md`. Where the contract leaves a field shape open, a sensible name is
 * chosen and flagged with a `NOTE:` comment — page agents should reconcile those against
 * the live OpenAPI schema at `/openapi.json` before relying on them.
 *
 * Each enum is declared as a `const` tuple plus a derived union so the values can also be
 * iterated at runtime (filter dropdowns, chart legends, ...).
 */

/* ------------------------------------------------------------------ */
/* Enums                                                               */
/* ------------------------------------------------------------------ */

export const USER_ROLES = ['USER', 'ADMIN'] as const
export type UserRole = (typeof USER_ROLES)[number]

export const WORK_MODES = ['REMOTE', 'HYBRID', 'ONSITE'] as const
export type WorkMode = (typeof WORK_MODES)[number]

export const EMPLOYMENT_TYPES = ['FULL_TIME', 'PART_TIME', 'CONTRACT', 'INTERNSHIP', 'FREELANCE'] as const
export type EmploymentType = (typeof EMPLOYMENT_TYPES)[number]

export const EXPERIENCE_LEVELS = ['INTERN', 'ENTRY', 'MID', 'SENIOR', 'LEAD', 'PRINCIPAL'] as const
export type ExperienceLevel = (typeof EXPERIENCE_LEVELS)[number]

export const COMPANY_PRIORITIES = ['P1', 'P2', 'P3', 'AVOID'] as const
export type CompanyPriority = (typeof COMPANY_PRIORITIES)[number]

export const JOB_SOURCE_TYPES = [
  'NAUKRI',
  'INDEED',
  'LINKEDIN',
  'HIRIST',
  'WELLFOUND',
  'INTERNSHALA',
  'GLASSDOOR',
  'FOUNDIT',
  'COMPANY_CAREERS',
  'GREENHOUSE',
  'LEVER',
  'WORKDAY',
  'DEMO_ATS',
  'OTHER',
] as const
export type JobSourceType = (typeof JOB_SOURCE_TYPES)[number]

export const APPLICATION_TYPES = ['EASY_APPLY', 'EXTERNAL_FORM', 'ATS_FORM', 'EMAIL', 'UNKNOWN'] as const
export type ApplicationType = (typeof APPLICATION_TYPES)[number]

export const APPLICATION_STATUSES = [
  'DISCOVERED',
  'QUEUED',
  'IN_PROGRESS',
  'APPLIED',
  'APPLICATION_RECEIVED',
  'ASSESSMENT',
  'INTERVIEW',
  'RECRUITER_CONTACTED',
  'REJECTED',
  'WITHDRAWN',
  'OFFER',
  'NO_RESPONSE',
  'SKIPPED',
] as const
export type ApplicationStatus = (typeof APPLICATION_STATUSES)[number]

/** Statuses that count as "the company replied" (mirrors `RESPONSE_STATUSES`). */
export const RESPONSE_STATUSES: readonly ApplicationStatus[] = [
  'APPLICATION_RECEIVED',
  'ASSESSMENT',
  'INTERVIEW',
  'RECRUITER_CONTACTED',
  'REJECTED',
  'OFFER',
]

/** Statuses meaning the application was actually sent (mirrors `SUBMITTED_STATUSES`). */
export const SUBMITTED_STATUSES: readonly ApplicationStatus[] = [
  ...RESPONSE_STATUSES,
  'APPLIED',
  'NO_RESPONSE',
  'WITHDRAWN',
]

export const AUTOMATION_STATES = [
  'IDLE',
  'RUNNING',
  'SUCCESS',
  'FAILED',
  'PAUSED',
  'REQUIRES_USER',
  'RETRYING',
] as const
export type AutomationState = (typeof AUTOMATION_STATES)[number]

export const PAUSE_REASONS = [
  'CAPTCHA',
  'OTP',
  'TWO_FACTOR',
  'LOGIN_REQUIRED',
  'ACCOUNT_REGISTRATION_REQUIRED',
  'UNKNOWN_QUESTION',
  'LEGAL_DECLARATION',
  'WORK_AUTHORIZATION',
  'DEMOGRAPHIC_QUESTION',
  'USER_REVIEW',
  'WEBSITE_CHANGED',
  'OTHER',
] as const
export type PauseReason = (typeof PAUSE_REASONS)[number]

export const ANSWER_SOURCES = ['PROFILE', 'RESUME', 'PREFERENCE', 'AI_GENERATED', 'USER', 'DEFAULT'] as const
export type AnswerSource = (typeof ANSWER_SOURCES)[number]

export const ANSWER_STATUSES = ['ANSWERED', 'NEEDS_USER_INPUT', 'SKIPPED'] as const
export type AnswerStatus = (typeof ANSWER_STATUSES)[number]

export const FIELD_TYPES = [
  'TEXT',
  'EMAIL',
  'PHONE',
  'NUMBER',
  'TEXTAREA',
  'SELECT',
  'RADIO',
  'CHECKBOX',
  'FILE',
  'DATE',
  'URL',
  'HIDDEN',
  'UNKNOWN',
] as const
export type FieldType = (typeof FIELD_TYPES)[number]

export const APPLICATION_EVENT_TYPES = [
  'CREATED',
  'STATUS_CHANGED',
  'AUTOMATION',
  'ANSWERS_GENERATED',
  'FORM_FILLED',
  'PAUSED',
  'RESUMED',
  'APPROVED',
  'SUBMITTED',
  'EMAIL_LINKED',
  'NOTE',
  'USER_ACTION',
  'ERROR',
] as const
export type ApplicationEventType = (typeof APPLICATION_EVENT_TYPES)[number]

export const ACTORS = ['SYSTEM', 'USER', 'AUTOMATION', 'EMAIL', 'SCHEDULER'] as const
export type Actor = (typeof ACTORS)[number]

export const DOCUMENT_TYPES = ['RESUME', 'COVER_LETTER', 'OTHER'] as const
export type DocumentType = (typeof DOCUMENT_TYPES)[number]

export const RESUME_PARSE_STATUSES = ['PENDING', 'PARSED', 'FAILED'] as const
export type ResumeParseStatus = (typeof RESUME_PARSE_STATUSES)[number]

export const EMAIL_PROVIDERS = ['GMAIL'] as const
export type EmailProvider = (typeof EMAIL_PROVIDERS)[number]

export const INTEGRATION_STATUSES = ['CONNECTED', 'DISCONNECTED', 'ERROR'] as const
export type IntegrationStatus = (typeof INTEGRATION_STATUSES)[number]

export const EMAIL_CLASSIFICATIONS = [
  'APPLICATION_RECEIVED',
  'RECRUITER_MESSAGE',
  'INTERVIEW',
  'ASSESSMENT',
  'REJECTION',
  'OFFER',
  'OTHER',
] as const
export type EmailClassification = (typeof EMAIL_CLASSIFICATIONS)[number]

export const INTERVIEW_TYPES = [
  'PHONE_SCREEN',
  'TECHNICAL',
  'SYSTEM_DESIGN',
  'BEHAVIORAL',
  'HR',
  'ONSITE',
  'ASSESSMENT',
  'OTHER',
] as const
export type InterviewType = (typeof INTERVIEW_TYPES)[number]

export const INTERVIEW_STATUSES = ['SCHEDULED', 'COMPLETED', 'CANCELLED', 'RESCHEDULED'] as const
export type InterviewStatus = (typeof INTERVIEW_STATUSES)[number]

export const AUTOMATION_RUN_TRIGGERS = ['SCHEDULED', 'MANUAL'] as const
export type AutomationRunTrigger = (typeof AUTOMATION_RUN_TRIGGERS)[number]

export const AUTOMATION_RUN_STATUSES = ['RUNNING', 'SUCCESS', 'PARTIAL', 'FAILED', 'PAUSED', 'CANCELLED'] as const
export type AutomationRunStatus = (typeof AUTOMATION_RUN_STATUSES)[number]

export const NOTIFICATION_TYPES = [
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
export type NotificationType = (typeof NOTIFICATION_TYPES)[number]

export const AUDIT_LEVELS = ['INFO', 'WARN', 'ERROR'] as const
export type AuditLevel = (typeof AUDIT_LEVELS)[number]

export const BROWSER_SESSION_STATUSES = ['ACTIVE', 'EXPIRED', 'REVOKED'] as const
export type BrowserSessionStatus = (typeof BROWSER_SESSION_STATUSES)[number]

/** Sub-scores reported by `matching/scoring.py` (plain strings on the model). */
export type ExperienceMatch = 'STRONG' | 'GOOD' | 'UNDER' | 'OVER' | 'UNKNOWN'
export type LocationMatch = 'MATCH' | 'REMOTE_OK' | 'MISMATCH' | 'UNKNOWN'
export type SalaryMatch = 'ABOVE' | 'WITHIN' | 'BELOW' | 'UNKNOWN'

/* ------------------------------------------------------------------ */
/* Envelopes                                                           */
/* ------------------------------------------------------------------ */

/** Body of every non-2xx response: `{"error": {code, message, details?}}`. */
export interface ApiErrorBody {
  error: {
    code: string
    message: string
    details?: unknown
  }
}

/** Standard paginated list envelope (see CONTRACTS section 0). */
export interface PageResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

/** Query params accepted by every list endpoint. */
export interface PageParams {
  page?: number
  page_size?: number
}

export type UUID = string
/** ISO-8601, timezone-aware UTC. */
export type ISODateString = string

/* ------------------------------------------------------------------ */
/* auth + users                                                        */
/* ------------------------------------------------------------------ */

export interface UserRead {
  id: UUID
  email: string
  full_name: string
  role: UserRole
  is_active: boolean
  is_verified: boolean
  created_at: ISODateString
  last_login_at: ISODateString | null
}

export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: UserRead
}

export interface LoginRequest {
  email: string
  password: string
}

export interface RegisterRequest {
  email: string
  password: string
  full_name: string
}

export interface ChangePasswordRequest {
  current_password: string
  new_password: string
}

/* ------------------------------------------------------------------ */
/* profiles + preferences                                              */
/* ------------------------------------------------------------------ */

export interface ExperienceEntry {
  company?: string | null
  title?: string | null
  start?: string | null
  end?: string | null
  description?: string | null
  technologies?: string[]
}

export interface EducationEntry {
  institution?: string | null
  degree?: string | null
  field?: string | null
  start?: string | null
  end?: string | null
  grade?: string | null
}

export interface ProjectEntry {
  name?: string | null
  description?: string | null
  technologies?: string[]
  url?: string | null
}

export interface CertificationEntry {
  name?: string | null
  issuer?: string | null
  year?: string | number | null
}

export interface ProfileRead {
  full_name: string | null
  first_name: string | null
  last_name: string | null
  email: string | null
  phone: string | null
  address: string | null
  city: string | null
  state: string | null
  country: string | null
  postal_code: string | null
  linkedin_url: string | null
  github_url: string | null
  portfolio_url: string | null

  headline: string | null
  summary: string | null
  current_designation: string | null
  current_company: string | null
  years_of_experience: number | null
  current_salary: number | null
  previous_companies: ExperienceEntry[]
  education: EducationEntry[]
  skills: string[]
  technologies: string[]
  certifications: CertificationEntry[]
  projects: ProjectEntry[]
  achievements: string[]
  languages: string[]
  skill_experience: Record<string, number>

  work_authorization: Record<string, boolean>
  requires_sponsorship: boolean | null
  willing_to_relocate: boolean | null
  canonical_answers: Record<string, string>

  /** Derived by the profiles service. */
  completeness: number
  missing_fields: string[]
  created_at?: ISODateString
  updated_at?: ISODateString
}

export type ProfileUpdate = Partial<
  Omit<ProfileRead, 'completeness' | 'missing_fields' | 'created_at' | 'updated_at'>
>

export interface JobPreferenceRead {
  desired_titles: string[]
  min_salary: number | null
  desired_salary: number | null
  currency: string
  notice_period_days: number | null
  preferred_locations: string[]
  work_modes: WorkMode[]
  employment_types: EmploymentType[]
  experience_min: number | null
  experience_max: number | null
  preferred_technologies: string[]
  excluded_keywords: string[]
  min_match_score: number
  only_posted_within_hours: number | null
  created_at?: ISODateString
  updated_at?: ISODateString
}

export type JobPreferenceUpdate = Partial<Omit<JobPreferenceRead, 'created_at' | 'updated_at'>>

/* ------------------------------------------------------------------ */
/* resumes                                                             */
/* ------------------------------------------------------------------ */

export interface ParsedResume {
  name?: string | null
  email?: string | null
  phone?: string | null
  summary?: string | null
  skills: string[]
  experience: ExperienceEntry[]
  education: EducationEntry[]
  projects: ProjectEntry[]
  certifications: CertificationEntry[]
  total_experience_years?: number | null
  links?: {
    linkedin?: string | null
    github?: string | null
    portfolio?: string | null
  }
}

export interface ResumeRead {
  id: UUID
  name: string
  target_role: string | null
  is_default: boolean
  original_filename: string
  mime_type: string
  size_bytes: number
  parse_status: ResumeParseStatus
  parse_error: string | null
  parsed_at: ISODateString | null
  parsed_data: ParsedResume | Record<string, never>
  current_version: number
  created_at: ISODateString
  updated_at: ISODateString
}

/** NOTE: shape inferred from the `ResumeVersion` model — confirm against OpenAPI. */
export interface ResumeVersionRead {
  id: UUID
  version_number: number
  note: string | null
  parsed_data: ParsedResume | Record<string, never>
  created_at: ISODateString
}

/* ------------------------------------------------------------------ */
/* companies                                                           */
/* ------------------------------------------------------------------ */

export interface CompanyRead {
  id: UUID
  name: string
  normalized_name: string
  domain: string | null
  website: string | null
  careers_url: string | null
  logo_url: string | null
  industry: string | null
  size: string | null
  headquarters: string | null
  description: string | null
  ats_type: string | null
  tags: string[]
  /** Priority the current user assigned (null when they never set one). */
  priority: CompanyPriority | null
  open_jobs: number
  applications: number
}

export interface CompanyPreferenceRead {
  id: UUID
  company_id: UUID | null
  company_name: string
  normalized_name: string
  priority: CompanyPriority
  notes: string | null
  created_at?: ISODateString
  updated_at?: ISODateString
}

export interface CompanyPreferenceUpsert {
  company_name: string
  priority: CompanyPriority
  notes?: string | null
}

/* ------------------------------------------------------------------ */
/* jobs + matching                                                     */
/* ------------------------------------------------------------------ */

/** Slim company reference embedded in `JobCard`. */
export interface JobCardCompany {
  id: UUID
  name: string
  logo_url: string | null
  domain: string | null
}

export interface JobCard {
  id: UUID
  title: string
  company: JobCardCompany
  location: string | null
  work_mode: WorkMode | null
  employment_type: EmploymentType | null
  salary_min: number | null
  salary_max: number | null
  salary_currency: string | null
  experience_min: number | null
  experience_max: number | null
  sources: JobSourceType[]
  primary_source: JobSourceType | null
  posted_at: ISODateString | null
  application_type: ApplicationType
  match_score: number | null
  company_priority: CompanyPriority
  application_status: ApplicationStatus | null
  application_id: UUID | null
  missing_skills: string[]
}

/** One platform a job was seen on. */
export interface JobSourceRead {
  id: UUID
  source: JobSourceType
  external_id: string
  url: string
  apply_url: string | null
  application_type: ApplicationType
  posted_at: ISODateString | null
  discovered_at: ISODateString
  last_seen_at: ISODateString
}

export interface JobDetail extends JobCard {
  description: string
  required_skills: string[]
  preferred_skills: string[]
  canonical_url: string | null
  apply_url: string | null
  is_active: boolean
  /** Full per-platform listings behind this (deduplicated) job. */
  source_links: JobSourceRead[]
  match: JobMatchRead | null
  application: ApplicationRead | null
  created_at: ISODateString
  updated_at: ISODateString
}

export interface SkillMatch {
  matched: string[]
  missing: string[]
  total: number
}

export interface JobMatchRead {
  id: UUID
  job_id: UUID
  resume_id: UUID | null
  match_score: number
  skill_score: number
  experience_score: number
  location_score: number
  salary_score: number | null
  title_score: number
  company_priority: CompanyPriority | null
  skill_match: SkillMatch
  experience_match: ExperienceMatch | null
  location_match: LocationMatch | null
  salary_match: SalaryMatch | null
  missing_skills: string[]
  explanation: string
  details: Record<string, unknown>
  analyzed_at: ISODateString
  model_used: string | null
}

export type JobSortOption = 'match' | 'posted' | 'salary'

export interface JobListParams extends PageParams {
  q?: string
  min_score?: number
  max_score?: number
  salary_min?: number
  location?: string
  work_mode?: WorkMode
  company?: string
  experience_min?: number
  experience_max?: number
  source?: JobSourceType
  posted_within_hours?: number
  /** An `ApplicationStatus`, or the literal `"NONE"` for jobs without an application. */
  status?: ApplicationStatus | 'NONE'
  priority?: CompanyPriority
  sort?: JobSortOption
}

export interface DiscoverSourceResult {
  source: JobSourceType
  found: number
  new: number
  error?: string | null
}

export interface DiscoverResult {
  jobs_found: number
  jobs_new: number
  duplicates_merged: number
  sources: DiscoverSourceResult[]
}

export interface MatchingSummary {
  total_jobs: number
  analyzed: number
  matched_at_or_above_min: number
  high_match: number
  queued: number
}

/* ------------------------------------------------------------------ */
/* adapters                                                            */
/* ------------------------------------------------------------------ */

export interface AdapterInfo {
  source: JobSourceType
  display_name: string
  is_mock: boolean
  supports_auto_apply: boolean
  requires_account: boolean
  terms_note: string
  /** Added by `GET /jobs/sources`. */
  job_count?: number
}

/* ------------------------------------------------------------------ */
/* applications                                                        */
/* ------------------------------------------------------------------ */

export interface ApplicationRead {
  id: UUID
  job_id: UUID
  resume_id: UUID | null
  automation_run_id: UUID | null
  status: ApplicationStatus
  priority: CompanyPriority
  match_score: number | null
  source: JobSourceType | null
  queue_position: number | null

  automation_state: AutomationState
  pause_reason: PauseReason | null
  pause_message: string | null
  retry_count: number
  last_error: string | null
  review_required: boolean
  approved_at: ISODateString | null
  auto_submit: boolean

  cover_letter: string | null
  applied_at: ISODateString | null
  submitted_via: string | null
  external_application_id: string | null
  external_url: string | null
  confirmation_message: string | null

  last_update_at: ISODateString | null
  last_response_at: ISODateString | null
  next_action: string | null
  next_action_due: ISODateString | null
  notes: string | null
  skipped_reason: string | null
  created_at: ISODateString
  updated_at: ISODateString

  /** Denormalised for list rendering. NOTE: confirm the exact key names against OpenAPI. */
  job_title?: string
  company_name?: string
  company_logo_url?: string | null
  location?: string | null
}

export interface FormSnapshotField {
  key: string
  label: string
  selector?: string | null
  field_type: FieldType
  mapped_to?: string | null
  value?: string | null
  status?: AnswerStatus
  required: boolean
}

export interface FormSnapshotBlocker {
  kind: PauseReason
  selector?: string | null
  message: string
}

export interface FormSnapshot {
  url?: string
  fields: FormSnapshotField[]
  blockers: FormSnapshotBlocker[]
}

export interface ApplicationAnswerRead {
  id: UUID
  order: number
  question_key: string
  question_text: string
  field_type: FieldType
  options: string[]
  required: boolean
  answer: string | null
  answer_source: AnswerSource | null
  status: AnswerStatus
  confidence: number | null
  rationale: string | null
  is_sensitive: boolean
  field_selector: string | null
  mapped_profile_field: string | null
}

export interface ApplicationEventRead {
  id: UUID
  application_id: UUID
  event_type: ApplicationEventType
  actor: Actor
  from_status: ApplicationStatus | null
  to_status: ApplicationStatus | null
  message: string
  meta: Record<string, unknown>
  created_at: ISODateString
}

export interface ApplicationDocumentRead {
  id: UUID
  resume_id: UUID | null
  document_type: DocumentType
  filename: string
  content: string | null
  created_at: ISODateString
}

export interface ReviewField {
  key: string
  label: string
  value: string | null
  status: AnswerStatus
  source: AnswerSource | null
  required: boolean
  is_sensitive: boolean
}

export interface ReviewSummary {
  company: string
  job_title: string
  resume_name: string | null
  salary_expectation: string | null
  location: string | null
  fields: ReviewField[]
  missing: string[]
  sensitive: string[]
  can_submit: boolean
  blockers: string[]
}

export interface ApplicationDetail extends ApplicationRead {
  form_snapshot: FormSnapshot | Record<string, never>
  answers: ApplicationAnswerRead[]
  events: ApplicationEventRead[]
  documents: ApplicationDocumentRead[]
  emails: EmailMessageRead[]
  interviews: InterviewRead[]
  job: JobDetail
  review: ReviewSummary
}

export interface QueueItem {
  application: ApplicationRead
  job: JobCard
  position: number
}

export interface ApplicationListParams extends PageParams {
  status?: ApplicationStatus
  source?: JobSourceType
  company?: string
  from?: string
  to?: string
  q?: string
  sort?: string
}

export interface QueueParams extends PageParams {
  priority?: CompanyPriority
  status?: ApplicationStatus
}

export interface AnswerUpdate {
  id: UUID
  answer: string
}

/* ------------------------------------------------------------------ */
/* interviews                                                          */
/* ------------------------------------------------------------------ */

export interface InterviewPrep {
  technical: string[]
  behavioral: string[]
  company_specific: string[]
  job_specific: string[]
  resume_based: string[]
  generated_at?: ISODateString
}

export interface InterviewRead {
  id: UUID
  application_id: UUID
  interview_type: InterviewType
  status: InterviewStatus
  round_number: number
  scheduled_at: ISODateString | null
  duration_minutes: number | null
  location_or_link: string | null
  interviewer: string | null
  notes: string | null
  outcome: string | null
  prep_material: InterviewPrep | Record<string, never>
  source_email_id: UUID | null
  created_at: ISODateString
  updated_at: ISODateString

  /** Denormalised for calendar rendering. NOTE: confirm against OpenAPI. */
  company_name?: string
  job_title?: string
}

/* ------------------------------------------------------------------ */
/* emails + integrations                                               */
/* ------------------------------------------------------------------ */

export interface EmailMessageRead {
  id: UUID
  application_id: UUID | null
  provider_message_id: string
  thread_id: string | null
  sender: string
  sender_domain: string | null
  recipient: string | null
  subject: string
  snippet: string | null
  /** Truncated to 2000 chars in list responses. */
  body_text: string | null
  received_at: ISODateString
  classification: EmailClassification
  classification_confidence: number | null
  classified_by: string | null
  classification_reason: string | null
  matched_by: string | null
  is_simulated: boolean
  is_read: boolean
  status_applied: boolean
  created_at: ISODateString
}

export interface EmailListParams extends PageParams {
  classification?: EmailClassification
  application_id?: UUID
  unlinked?: boolean
}

export interface GmailStatus {
  status: IntegrationStatus
  email_address: string | null
  scopes: string[]
  connected_at: ISODateString | null
  last_synced_at: ISODateString | null
  /** false when GOOGLE_CLIENT_ID / SECRET are not set on the server. */
  configured: boolean
  last_error?: string | null
}

export interface ConnectedAccountRead {
  id: UUID
  source: JobSourceType
  account_identifier: string | null
  status: IntegrationStatus
  is_mock: boolean
  connected_at: ISODateString | null
  last_used_at: ISODateString | null
  last_error: string | null
}

export interface IntegrationsOverview {
  gmail: GmailStatus
  accounts: ConnectedAccountRead[]
  adapters: AdapterInfo[]
}

export interface SyncResult {
  fetched: number
  new: number
  classified: number
  linked: number
  status_updates: number
}

/* ------------------------------------------------------------------ */
/* automation                                                          */
/* ------------------------------------------------------------------ */

export interface AutomationConfigRead {
  enabled: boolean
  schedule_time: string
  timezone: string
  daily_application_limit: number
  per_platform_limit: Record<string, number>
  min_match_score: number
  prioritize_priority_companies: boolean
  only_posted_within_hours: number
  enabled_sources: JobSourceType[]
  delay_between_actions_seconds: number
  retry_limit: number
  auto_submit_enabled: boolean
  auto_submit_sources: JobSourceType[]
  auto_generate_cover_letters: boolean
  notify_on_input_required: boolean
  last_run_at: ISODateString | null
  next_run_at: ISODateString | null
}

export type AutomationConfigUpdate = Partial<Omit<AutomationConfigRead, 'last_run_at' | 'next_run_at'>>

export interface AutomationRunStats {
  jobs_found?: number
  jobs_new?: number
  duplicates_merged?: number
  jobs_analyzed?: number
  jobs_matched?: number
  high_match?: number
  queued?: number
  prepared?: number
  submitted?: number
  requires_user?: number
  failed?: number
  skipped_limit?: number
  [key: string]: number | undefined
}

export interface AutomationRunStep {
  step: string
  status: 'SUCCESS' | 'FAILED' | 'SKIPPED' | 'RUNNING'
  started_at?: ISODateString | null
  finished_at?: ISODateString | null
  message?: string
  data?: Record<string, unknown>
}

export interface AutomationRunRead {
  id: UUID
  trigger: AutomationRunTrigger
  status: AutomationRunStatus
  started_at: ISODateString
  finished_at: ISODateString | null
  current_step: string | null
  stats: AutomationRunStats
  steps: AutomationRunStep[]
  error: string | null
  config_snapshot?: Record<string, unknown>
}

export interface AutomationStatus {
  enabled: boolean
  next_run_at: ISODateString | null
  last_run: AutomationRunRead | null
  running: boolean
  today: {
    applications_submitted: number
    limit_remaining: number
  }
}

/* ------------------------------------------------------------------ */
/* dashboard                                                           */
/* ------------------------------------------------------------------ */

export interface DashboardPeriodStats {
  applications: number
  responses: number
  interviews: number
  rejections: number
  pending: number
  jobs_found: number
}

export interface DashboardTotals {
  jobs_found: number
  jobs_matched: number
  high_match: number
  queued: number
  applications: number
  responses: number
  interviews: number
  offers: number
  rejections: number
  pending_review: number
  requires_input: number
}

export interface AttentionItem {
  type: string
  title: string
  link: string
  count: number
}

export interface DashboardStats {
  today: DashboardPeriodStats
  week: DashboardPeriodStats
  month: DashboardPeriodStats
  totals: DashboardTotals
  response_rate: number
  interview_rate: number
  offer_rate: number
  attention: AttentionItem[]
}

export interface DatePoint {
  date: string
  count: number
}

export interface DashboardCharts {
  applications_per_day: DatePoint[]
  responses_per_day: DatePoint[]
  by_company: { name: string; count: number }[]
  by_source: { source: JobSourceType; count: number }[]
  by_status: { status: ApplicationStatus; count: number }[]
  funnel: { stage: string; count: number }[]
  match_distribution: { bucket: string; count: number }[]
}

export type ChartRange = '7d' | '30d' | '90d'

/** `GET /dashboard/activity` merges audit logs and application events. */
export interface ActivityItem {
  id: UUID
  kind: 'AUDIT' | 'EVENT'
  action: string
  message: string
  actor: Actor
  application_id: UUID | null
  created_at: ISODateString
  meta?: Record<string, unknown>
}

/* ------------------------------------------------------------------ */
/* notifications + audit                                               */
/* ------------------------------------------------------------------ */

export interface NotificationRead {
  id: UUID
  type: NotificationType
  title: string
  body: string | null
  link: string | null
  is_read: boolean
  meta: Record<string, unknown>
  created_at: ISODateString
}

export interface UnreadCount {
  count: number
}

export interface AuditLogRead {
  id: UUID
  user_id: UUID | null
  application_id: UUID | null
  automation_run_id: UUID | null
  actor: Actor
  level: AuditLevel
  action: string
  message: string
  meta: Record<string, unknown>
  ip_address: string | null
  created_at: ISODateString
}

export interface AuditListParams extends PageParams {
  application_id?: UUID
  automation_run_id?: UUID
  action_prefix?: string
}

/* ------------------------------------------------------------------ */
/* browser                                                             */
/* ------------------------------------------------------------------ */

export interface BrowserSessionRead {
  id: UUID
  source: JobSourceType
  status: BrowserSessionStatus
  last_used_at: ISODateString | null
  expires_at: ISODateString | null
  user_agent: string | null
  created_at: ISODateString
}

/* ------------------------------------------------------------------ */
/* misc                                                                */
/* ------------------------------------------------------------------ */

export interface AiStatus {
  provider: string
  model: string | null
  configured: boolean
}

export interface HealthStatus {
  status: string
  app: string
  env: string
  llm_provider: string
}
