# JobPilot AI — Module Contracts

This document is the **binding contract** between backend modules (and between backend and
frontend). Every module is implemented independently against these interfaces. If you need to
deviate, update this file in the same change.

Source of truth for data shapes: `backend/app/models/*.py` (SQLAlchemy) and `backend/app/models/enums.py`.
Core helpers: `backend/app/core/` (config, database, security, deps, exceptions, audit, rate_limit).

---

## 0. Conventions (all modules)

* Module layout: `backend/app/modules/<name>/{router.py, schemas.py, service.py}` (+ optional
  `repository.py`, `rules.py`, etc.). Routers are thin; business logic lives in services.
  Tests go in `backend/tests/test_<name>.py` and must run on SQLite with the mock LLM (see `tests/conftest.py`).
* Every router file exposes `router = APIRouter()`. Prefixes are applied in `app/main.py`
  (see the table in §1) — **do not** add the prefix inside the module.
* Auth: `user: User = Depends(get_current_user)` from `app.core.deps`. Every endpoint (except
  auth + health + demo ATS) requires auth and is scoped to the current user. Never return
  another user's rows. Admin-only endpoints use `Depends(require_admin)`.
* DB: `db: Session = Depends(get_db)` — the dependency commits on success / rolls back on error.
  Services take `db: Session` as first argument and **do not** call `db.commit()` unless they
  are invoked from a background job (use `session_scope()` there).
* IDs are UUIDs (serialized as strings). Datetimes are timezone-aware UTC, ISO-8601 in JSON.
* Errors: raise `AppError` subclasses from `app.core.exceptions`
  (`NotFoundError`, `ConflictError`, `ForbiddenError`, `ValidationFailed`, `AutomationPaused`...).
  Body shape: `{"error": {"code": str, "message": str, "details"?: any}}`.
* Pagination: list endpoints accept `page` (1-based, default 1) and `page_size` (default 20, max 100)
  and return `{"items": [...], "total": int, "page": int, "page_size": int}`.
  Pydantic base for this: define `PageResponse[T]` in `app/modules/common/schemas.py` — **module: common**
  (owned by the `auth+profiles` agent; other agents may import it once it exists, or define a local
  equivalent with the same shape).
* Pydantic v2 everywhere: `model_config = ConfigDict(from_attributes=True)` on read schemas.
* Audit: call `audit(db, action=..., message=..., user_id=..., actor=...)` from `app.core.audit` for
  every automated action and security-relevant user action. Action names are dotted:
  `auth.login`, `resume.uploaded`, `job.found`, `job.analyzed`, `application.created`,
  `application.answers_generated`, `application.form_detected`, `application.field_filled`,
  `application.paused`, `application.resumed`, `application.approved`, `application.submitted`,
  `application.failed`, `email.classified`, `email.linked`, `automation.run_started`,
  `automation.step`, `automation.run_finished`, `integration.connected`, ...
* Notifications: `from app.modules.notifications.service import notify` —
  `notify(db, user_id, type: NotificationType, title: str, body: str | None = None, link: str | None = None, meta: dict | None = None) -> Notification`.
* Logging: `logger = logging.getLogger(__name__)`. No `print`.
* Secrets: anything sensitive at rest goes through `encrypt_str/decrypt_str` (`app.core.security`).
  Never return encrypted blobs or raw credentials from the API.
* No hardcoded secrets, no bypassing CAPTCHA/OTP/2FA/anti-bot. When blocked → `REQUIRES_USER`.

---

## 1. Router prefixes (applied in `app/main.py`)

| Module | Prefix | Owner agent |
|---|---|---|
| auth | `/api/v1/auth` | auth+profiles |
| profiles | `/api/v1` (defines `/profile`, `/preferences/job`) | auth+profiles |
| companies | `/api/v1/companies` (defines `/`, `/{id}`, `/preferences`, `/preferences/{id}`) | auth+profiles |
| notifications | `/api/v1/notifications` | auth+profiles |
| audit | `/api/v1/audit` | auth+profiles |
| resumes | `/api/v1/resumes` | ai+resumes |
| ai | `/api/v1/ai` | ai+resumes |
| jobs | `/api/v1/jobs` | jobs+adapters+matching |
| matching | `/api/v1/matching` | jobs+adapters+matching |
| applications | `/api/v1/applications` | applications |
| interviews | `/api/v1/interviews` | applications |
| browser | `/api/v1/browser` | browser+demo_ats |
| demo_ats | `/demo-ats` (HTML, no auth) | browser+demo_ats |
| emails | `/api/v1/emails` | emails+integrations |
| integrations | `/api/v1/integrations` | emails+integrations |
| automation | `/api/v1/automation` | automation+dashboard |
| dashboard | `/api/v1/dashboard` | automation+dashboard |
| worker (`app/worker/`) | – | automation+dashboard |
| seed (`app/seed.py`) | – | automation+dashboard |

---

## 2. auth

Endpoints:
* `POST /register {email, password, full_name}` → `201 TokenResponse` (also creates empty `UserProfile`, `JobPreference`, `AutomationConfig`).
* `POST /login {email, password}` → `TokenResponse`, sets `refresh_token` HttpOnly cookie (path `/api/v1/auth`).
* `POST /refresh` (cookie) → `TokenResponse` (rotates refresh token; old one revoked).
* `POST /logout` → revokes refresh token, clears cookie.
* `GET /me` → `UserRead`.
* `PUT /me/password {current_password, new_password}`.

`TokenResponse = {access_token: str, token_type: "bearer", expires_in: int, user: UserRead}`
`UserRead = {id, email, full_name, role, is_active, is_verified, created_at, last_login_at}`
Password policy: ≥ 8 chars, at least one letter and one digit. Rate limit via `Depends(auth_rate_limit)`.

Service functions others may use: `auth.service.create_user(db, email, password, full_name) -> User`.

## 3. profiles

* `GET /profile` → `ProfileRead` (every column of `UserProfile` except ids, plus `completeness: int` 0–100 and `missing_fields: list[str]`).
* `PUT /profile ProfileUpdate` (all optional) → `ProfileRead`. Updating `full_name` auto-derives `first_name`/`last_name` if those are empty and vice versa.
* `GET /preferences/job` → `JobPreferenceRead`; `PUT /preferences/job JobPreferenceUpdate`.

Service (used by matching, applications, browser):
* `profiles.service.get_or_create_profile(db, user_id) -> UserProfile`
* `profiles.service.get_or_create_job_preference(db, user_id) -> JobPreference`
* `profiles.service.build_candidate_context(db, user_id, resume_id: UUID | None = None) -> CandidateContext`

`CandidateContext` (pydantic, in `profiles/schemas.py`) — the **flattened view the answer engine and field mapper read from**:
```
profile: ProfileRead
preferences: JobPreferenceRead
resume: ResumeRead | None          # default resume unless resume_id given
resume_path: str | None            # absolute file path for upload fields
flat: dict[str, Any]               # canonical keys → values (see §11 canonical keys)
```

## 4. companies

* `GET /` `?q=&priority=&page=` → page of `CompanyRead` (+ `priority: CompanyPriority | None` for the current user, `open_jobs: int`, `applications: int`).
* `GET /{id}` → `CompanyRead`.
* `GET /preferences` → `list[CompanyPreferenceRead]` grouped in frontend by priority.
* `PUT /preferences {items: [{company_name, priority, notes?}]}` → replaces the user's list (upsert by normalized name). Also `POST /preferences {company_name, priority}` (single upsert) and `DELETE /preferences/{id}`.

Service (used by jobs, matching, applications):
* `companies.service.normalize_company_name(name) -> str` (lowercase, strip legal suffixes inc/ltd/llc/pvt/technologies/labs, non-alnum removed).
* `companies.service.get_or_create_company(db, name, **attrs) -> Company`
* `companies.service.get_priority(db, user_id, company: Company) -> CompanyPriority` (default `P2`; matches by normalized name or `company_id`).
* `companies.service.blacklist_company(db, user_id, company_id) -> CompanyPreference` (sets AVOID; also skips open queued applications for that company).

## 5. notifications & audit

* `GET /notifications?unread_only=&page=` → page of `NotificationRead`; `POST /notifications/{id}/read`; `POST /notifications/read-all`; `GET /notifications/unread-count → {count}`.
* `GET /audit?application_id=&automation_run_id=&action_prefix=&page=` → page of `AuditLogRead`.

## 6. ai (`app/modules/ai`)

```python
class LLMProvider(ABC):
    name: str
    def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 800, temperature: float = 0.2) -> str
    def complete_json(self, prompt: str, *, schema: dict | type[BaseModel], system: str | None = None, max_tokens: int = 1500) -> dict
```
* Implementations: `MockLLMProvider` (deterministic, rule/template based, **default**), `OpenAIProvider`, `AnthropicProvider`. `get_llm_provider() -> LLMProvider` reads `settings.LLM_PROVIDER` (cached).
* The mock must produce sensible output for **every** prompt type used in the app (resume parsing, match explanation, answers, cover letter, email classification, interview prep). It should key off structured inputs passed as JSON in the prompt, not parse free text, i.e. every AI *task* below has a typed function that builds the prompt and knows how to call the mock deterministically.

Typed AI tasks (`ai/tasks.py`) — used by other modules:
* `parse_resume(text: str) -> ParsedResume` — `{name, email, phone, summary, skills[], experience[{company,title,start,end,description,technologies[]}], education[{institution,degree,field,start,end}], projects[{name,description,technologies[]}], certifications[{name,issuer,year}], total_experience_years: float | None, links{linkedin,github,portfolio}}`
* `explain_match(job: JobContext, candidate: CandidateContext, scores: dict) -> str`
* `generate_answer(question: str, field_type: str, options: list[str], job: JobContext, candidate: CandidateContext) -> GeneratedAnswer` — `{answer: str | None, source: AnswerSource, confidence: float, rationale: str, needs_user_input: bool}`. **Must never invent facts**: only synthesise free-text answers (why us, cover letter, describe a project) from provided context; for factual questions (salary, notice period, years with X, authorization, sponsorship, relocation) return values only if present in `candidate.flat`, else `needs_user_input=True`.
* `generate_cover_letter(job: JobContext, candidate: CandidateContext) -> str` (≤ 250 words).
* `classify_email(subject: str, sender: str, body: str) -> EmailClassificationResult` — `{classification: EmailClassification, confidence: float, reason: str, company_hint: str | None, job_title_hint: str | None}`.
* `generate_interview_prep(job: JobContext, candidate: CandidateContext, interview_type: str) -> InterviewPrep` — `{technical[], behavioral[], company_specific[], job_specific[], resume_based[]}`.

`JobContext` (pydantic in `ai/schemas.py`): `{id, title, company_name, company_description, location, work_mode, description, required_skills[], preferred_skills[], experience_min, experience_max, salary_min, salary_max, salary_currency, source}` with `JobContext.from_job(job: Job)`.

Endpoints: `GET /ai/status → {provider, model, configured: bool}`.

## 7. resumes

* `POST /` multipart `file` (+ optional `name`, `target_role`, `set_default`) → `ResumeRead` (201). Validates PDF/DOCX, ≤ `MAX_UPLOAD_MB`, stores under `UPLOAD_DIR/resumes/<user_id>/<uuid>.<ext>`, extracts text (pypdf / python-docx), parses with `ai.tasks.parse_resume`, creates `ResumeVersion` 1. First resume becomes default.
* `GET /` → `list[ResumeRead]`; `GET /{id}`; `PATCH /{id} {name?, target_role?, is_default?}`; `PUT /{id}/parsed-data ParsedResume` (user edits, bumps version); `POST /{id}/reparse`; `DELETE /{id}` (removes file; cannot delete the only default while applications reference it → reassign default); `GET /{id}/download` (streams file, auth required); `GET /{id}/versions`.

`ResumeRead = {id, name, target_role, is_default, original_filename, mime_type, size_bytes, parse_status, parse_error, parsed_at, parsed_data: ParsedResume | {}, current_version, created_at, updated_at}`.

Service: `resumes.service.get_default_resume(db, user_id) -> Resume | None`, `resumes.service.get_resume(db, user_id, resume_id) -> Resume`.

## 8. adapters (`app/modules/adapters`) — JobSourceAdapter

```python
@dataclass
class DiscoveredJob:            # normalised output of searchJobs()
    source: JobSourceType; external_id: str; url: str; title: str; company_name: str
    location: str | None; work_mode: WorkMode | None; employment_type: EmploymentType | None
    description: str; required_skills: list[str]; preferred_skills: list[str]
    experience_min: float | None; experience_max: float | None
    salary_min: int | None; salary_max: int | None; salary_currency: str | None
    posted_at: datetime | None; apply_url: str | None; application_type: ApplicationType
    company_domain: str | None = None; company_logo_url: str | None = None; raw: dict = field(default_factory=dict)

@dataclass
class SearchQuery: titles: list[str]; locations: list[str]; keywords: list[str]; posted_within_hours: int | None; limit: int = 50; work_modes: list[WorkMode] = ...

class JobSourceAdapter(ABC):
    source: JobSourceType; display_name: str; is_mock: bool; supports_auto_apply: bool; requires_account: bool; rate_limit_per_minute: int
    def authenticate(self, session: BrowserSessionHandle | None, credentials: dict | None) -> AuthResult
    def search_jobs(self, query: SearchQuery) -> list[DiscoveredJob]
    def get_job_details(self, external_id: str) -> DiscoveredJob | None
    def detect_application_type(self, job: DiscoveredJob) -> ApplicationType
    def start_application(self, ctx: ApplyContext) -> ApplyStepResult      # navigate to form
    def fill_application(self, ctx: ApplyContext) -> ApplyStepResult      # detect + map + fill; may return REQUIRES_USER
    def submit_application(self, ctx: ApplyContext) -> ApplyStepResult    # click submit, capture confirmation
    def get_application_status(self, external_application_id: str) -> ApplicationStatus | None
```
`ApplyStepResult = {state: AutomationState, message: str, pause_reason: PauseReason | None, form_snapshot: dict | None, external_application_id: str | None, confirmation_message: str | None, screenshot_path: str | None}`.
`ApplyContext = {application: Application, job: Job, candidate: CandidateContext, answers: list[ApplicationAnswer], page: playwright Page | None, db: Session, settings}`.

* `adapters/registry.py`: `get_adapter(source: JobSourceType) -> JobSourceAdapter`, `list_adapters() -> list[AdapterInfo]` (`{source, display_name, is_mock, supports_auto_apply, requires_account, terms_note}`).
* Mock adapters (`adapters/mock/*.py`): NAUKRI, LINKEDIN, INDEED, HIRIST, WELLFOUND, INTERNSHALA, GLASSDOOR, FOUNDIT — each returns a realistic, deterministic catalogue (seeded, ~15–25 jobs each, Indian + remote market, INR salaries, several **intentional cross-platform duplicates** of the same posting, e.g. the same Google/Microsoft/Amazon roles appearing on LinkedIn + company careers + Naukri). Mock `fill_application/submit_application` simulate an EASY_APPLY flow with delays and return SUCCESS (or REQUIRES_USER for a small deterministic subset to demo pausing).
* `DemoAtsAdapter` (source `DEMO_ATS`, `is_mock=False`): lists jobs from the demo ATS JSON endpoint and drives the **real Playwright** flow against `DEMO_ATS_BASE_URL/demo-ats/...` using the browser module. `GreenhouseAdapter`/`LeverAdapter` stubs may share the generic form-fill logic via `browser.autofill` and declare `requires_account=False`.
* Real third-party sites are **not** scraped in the MVP. Each adapter has a `terms_note` string explaining what a production implementation must respect (official APIs, ToS, rate limits, user-owned session, no CAPTCHA bypass).

## 9. jobs

* `GET /` filters: `q, min_score, max_score, salary_min, location, work_mode, company, experience_min, experience_max, source, posted_within_hours, status (application status or "NONE"), priority, sort (match|posted|salary), page, page_size` → page of `JobCard`.
* `GET /{id}` → `JobDetail` (`JobCard` + description, sources, match details, application).
* `POST /{id}/analyze` → `JobMatchRead` (runs matching for the current user with default resume; `?resume_id=`).
* `POST /discover {sources?: [JobSourceType], limit?: int}` → `DiscoverResult {jobs_found, jobs_new, duplicates_merged, sources: [{source, found, new, error?}]}` — runs adapters with the user's preferences as `SearchQuery`, ingests via `jobs.service.ingest_discovered(db, user_id, jobs) -> IngestResult`, then analyzes new jobs.
* `POST /{id}/skip {reason?}` → marks/creates the application as `SKIPPED` for this user.
* `POST /{id}/queue` → creates `Application` in `QUEUED` (delegates to `applications.service.queue_job`).
* `GET /sources` → `list[AdapterInfo]` + per-source counts.

`JobCard = {id, title, company: {id, name, logo_url, domain}, location, work_mode, employment_type, salary_min, salary_max, salary_currency, experience_min, experience_max, sources: [JobSourceType], primary_source, posted_at, application_type, match_score: int | None, company_priority: CompanyPriority, application_status: ApplicationStatus | None, application_id: UUID | None, missing_skills: [str]}`.

Dedup (`jobs/dedupe.py`): `compute_dedupe_hash(company_norm, title_norm, location_norm)`; on ingest, match by (source, external_id) → same JobSource; else by canonical_url; else by dedupe_hash; else by fuzzy (`rapidfuzz` token_set_ratio ≥ 90 on title within same company + description similarity ≥ 0.8) → attach a new `JobSource` to the existing Job. `normalize_title` strips seniority noise punctuation, collapses "SDE II"/"Software Development Engineer 2" style variants.

## 10. matching

* `matching.service.analyze_job(db, user_id, job: Job, resume: Resume | None = None) -> JobMatch` (upsert on `(job_id, user_id)`).
* `matching.service.analyze_jobs(db, user_id, jobs: list[Job]) -> list[JobMatch]`.
* Scoring (`matching/scoring.py`, pure functions, unit-tested): weights `skills 0.40, title 0.15, experience 0.20, location 0.10, salary 0.10, preferences/company 0.05`. Salary unknown → redistribute its weight. Company priority does **not** inflate the score beyond +5 for P1 / +2 for P2; `AVOID` forces score 0 and `explanation="Company is on your avoid list"`. Missing skills = required skills not matched (with alias normalisation via `Skill` table + built-in alias map).
* Output fields as per `JobMatch` model. `experience_match ∈ {STRONG, GOOD, UNDER, OVER, UNKNOWN}`, `location_match ∈ {MATCH, REMOTE_OK, MISMATCH, UNKNOWN}`, `salary_match ∈ {ABOVE, WITHIN, BELOW, UNKNOWN}`.
* Endpoints: `POST /matching/analyze-all` (re-analyze all active jobs for the user, returns counts); `GET /matching/summary → {total_jobs, analyzed, matched_at_or_above_min, high_match (≥85), queued}`.

## 11. applications (+ queue, answers, approval, cover letter, events)

Canonical field keys (used by answers, field mapper and `CandidateContext.flat`):
```
first_name last_name full_name email phone address city state country postal_code
linkedin_url github_url portfolio_url website
current_designation current_company years_of_experience current_salary expected_salary desired_salary min_salary
notice_period_days notice_period_text willing_to_relocate requires_sponsorship work_authorization
skills technologies summary headline education highest_degree university
resume_file cover_letter
skill_years:<skill>           # e.g. skill_years:react → from profile.skill_experience or resume
custom:<slug>                 # any free-text/custom question
```
* Queue: `GET /queue?priority=&status=` → page of `QueueItem {application: ApplicationRead, job: JobCard, position}` ordered by (priority P1<P2<P3, match_score desc, posted_at desc). Statuses shown: QUEUED, IN_PROGRESS (automation_state RUNNING/REQUIRES_USER/PAUSED/FAILED), and "Ready" = QUEUED with answers generated & no NEEDS_USER_INPUT.
* `GET /` filters `status, source, company, from, to, q, sort, page` → page of `ApplicationRead`.
* `GET /{id}` → `ApplicationDetail` (`ApplicationRead` + `answers[]`, `events[]`, `documents[]`, `emails[]`, `interviews[]`, `job: JobDetail`, `review: ReviewSummary`).
* `POST /{id}/start` → sets `IN_PROGRESS`, generates answers (`applications.answers.generate_answers(db, application, candidate)`), optionally cover letter, then hands to browser/adapters: `applications.service.start_application(db, application_id, user_id, run_in_background: bool = True) -> ApplicationRead`. Background execution uses a thread + `session_scope()`; progress via `automation_state`, `events` and audit logs.
* `POST /{id}/answers/generate` → regenerates answers (keeps USER-provided ones).
* `PUT /{id}/answers {answers: [{id, answer}]}` → user edits; status becomes ANSWERED, source USER.
* `POST /{id}/approve` → requires **no** `NEEDS_USER_INPUT` answers for required fields; sets `approved_at`, then submits via the adapter (`submit_application`); on success `status=APPLIED`, `applied_at=now`, `automation_state=SUCCESS`, notification `APPLICATION_SUBMITTED`. Returns `ApplicationRead`.
* `POST /{id}/submit` → alias of approve for MVP (kept for API symmetry).
* `POST /{id}/resume-automation {answers?: [...]}` → after user resolved a pause (CAPTCHA done / question answered) continue (`AutomationState.RUNNING`).
* `POST /{id}/skip {reason?}` → `SKIPPED`.
* `PATCH /{id}/status {status, note?}` → manual status change (records `ApplicationEvent STATUS_CHANGED`, actor USER). Moving to `INTERVIEW` auto-creates an `Interview` if none exists.
* `PATCH /{id} {notes?, next_action?, next_action_due?, resume_id?}`.
* `POST /{id}/cover-letter` → generate; `PUT /{id}/cover-letter {content}` → save; returns `{cover_letter}`.
* `GET /{id}/events` → `list[ApplicationEventRead]`.
* `POST /{id}/withdraw`.
* `GET /review-summary → {pending_review: int, requires_input: int, ready_to_submit: int}`.

Service functions used by other modules:
* `applications.service.queue_job(db, user_id, job_id, *, run_id=None, priority=None, auto_submit=False) -> Application` (idempotent; if an application exists returns it).
* `applications.service.transition(db, application, new_status, *, actor, message, meta=None) -> Application` (records event, updates `last_update_at`, sets `last_response_at` for response statuses, triggers notifications for INTERVIEW/OFFER/REJECTED/ASSESSMENT/RECRUITER_CONTACTED).
* `applications.service.record_event(db, application, event_type, message, *, actor=Actor.SYSTEM, meta=None)`.
* `applications.service.pause(db, application, reason: PauseReason, message: str, *, form_snapshot=None)` → `automation_state=REQUIRES_USER`, notification `INPUT_REQUIRED`, audit.
* `applications.service.mark_failed(db, application, error: str)` → increments retry_count, `FAILED` or `RETRYING` per `retry_limit`.
* `applications.service.mark_submitted(db, application, *, external_application_id=None, confirmation_message=None, via="AUTOMATION")`.
* `applications.answers.generate_answers(db, application, candidate: CandidateContext, questions: list[FormQuestion] | None = None) -> list[ApplicationAnswer]` — when `questions` is None, use the standard question set for the job's application type (name/email/phone/linkedin/github/resume/experience/expected salary/notice period/why us/authorization). Sensitive keys (`work_authorization`, `requires_sponsorship`, `custom:*legal*`, `custom:*gender*|*ethnicity*|*disability*|*veteran*`) set `is_sensitive=True` and are **never auto-answered by AI** — profile value or `NEEDS_USER_INPUT`.
* `applications.review.build_review(db, application) -> ReviewSummary {company, job_title, resume_name, salary_expectation, location, fields: [...], missing: [str], sensitive: [str], can_submit: bool, blockers: [str]}`.

Interviews (`modules/interviews`, same owner):
* `GET /interviews?upcoming=&application_id=` ; `POST /interviews {application_id, interview_type, scheduled_at, ...}` ; `PATCH /interviews/{id}` ; `POST /interviews/{id}/prep` → generates `prep_material` via `ai.tasks.generate_interview_prep` ; `DELETE /interviews/{id}`.

## 12. browser (`app/modules/browser`) — Playwright architecture

* `browser/session.py`: `BrowserManager` — one Playwright instance per process (lazy, sync API); `open_context(user_id, source) -> BrowserSessionHandle` creates an **isolated** `BrowserContext` per (user, source), restoring encrypted `storage_state` from `BrowserSession` if present and saving it back on close. Never share contexts between users.
* `browser/detector.py`: `detect_form(page) -> DetectedForm {url, fields: [DetectedField], submit_selector, blockers: [Blocker]}` where `DetectedField = {selector, label, name, id, placeholder, field_type: FieldType, required, options[], autocomplete, section}`; label resolution order: `<label for>`, `aria-label`, `aria-labelledby`, wrapping label, placeholder, preceding text, `name`. `Blocker = {kind: PauseReason, selector, message}` — detects CAPTCHA (iframe src recaptcha/hcaptcha/turnstile, `.g-recaptcha`, text "captcha"), OTP/2FA inputs (`autocomplete=one-time-code`, labels containing "OTP"/"verification code"), login walls (password field present + "sign in" text), account registration prompts.
* `browser/mapper.py`: `FieldMapper.map(field: DetectedField) -> Mapping {canonical_key: str | None, confidence: float, reason: str, is_sensitive: bool}` — reusable rules (regex/keyword synonyms) table: e.g. "mobile|phone|contact number" → `phone`; "current ctc|current salary" → `current_salary`; "expected ctc|expected salary|salary expectation" → `expected_salary`; "notice period" → `notice_period_days`; "total experience|years of experience" → `years_of_experience`; "linkedin" → `linkedin_url`; "github" → `github_url`; "portfolio|website" → `portfolio_url`; "resume|cv|upload" (file) → `resume_file`; "cover letter" → `cover_letter`; "years .* (react|node|python…)" → `skill_years:<skill>`; "authori[sz]ed to work|work permit|visa" → `work_authorization` (sensitive); "sponsorship" → `requires_sponsorship` (sensitive); gender/race/veteran/disability → `custom:demographic_*` (sensitive → REQUIRES_USER). Unknown → `custom:<slug(label)>`.
* `browser/autofill.py`: `fill_form(page, detected: DetectedForm, answers: list[ApplicationAnswer]) -> FillResult {filled: [...], skipped: [...], needs_user: [...]}` — supports text/textarea/select/radio/checkbox/file (`set_input_files` with resume path). Respects `settings.BROWSER_ACTION_DELAY_MS` between actions. Takes a screenshot to `UPLOAD_DIR/screenshots/<application_id>/<step>.png` after fill.
* `browser/runner.py`: `ApplicationRunner.run(application_id) ` orchestrates: open context → `adapter.start_application` → `detect_form` → blockers? → `pause(...)` and stop → map fields → merge with pre-generated answers (generate answers for newly discovered questions via `generate_answers(..., questions=...)`) → `fill_form` → build `form_snapshot` → if any NEEDS_USER_INPUT for required → `pause(UNKNOWN_QUESTION)`; else `automation_state=PAUSED`, `pause_reason=USER_REVIEW`, notification "ready for review". Submission only happens from `applications.service.approve()` (human-in-the-loop), or automatically if `application.auto_submit and config.auto_submit_enabled and source in config.auto_submit_sources`. Any exception → `mark_failed` (+ screenshot + audit `application.failed`). Retries temporary network errors up to `retry_limit` (state RETRYING).
* `browser/router.py`: `GET /browser/sessions` (list own sessions w/o state), `DELETE /browser/sessions/{id}`, `GET /browser/screenshots/{application_id}/{name}` (auth, own applications only).
* **No CAPTCHA/OTP/2FA solving, no stealth plugins, no bot-detection evasion.** Detection → pause → user.

Demo ATS (`app/demo_ats`), served at `/demo-ats` (Jinja2 templates, no auth, deliberately Greenhouse-like markup):
* `GET /demo-ats/` company list; `GET /demo-ats/jobs.json` → JSON list of demo postings (used by `DemoAtsAdapter.search_jobs`) — ~8 postings across 3–4 fictional-but-realistic demo companies plus mirrors of a few P1 roles (e.g. "Northwind Labs", "Acme Cloud", and demo mirrors labelled "(Demo Careers)" for Google/Microsoft/Amazon-style roles).
* `GET /demo-ats/jobs/{slug}` job description page with an **Apply** button → `GET /demo-ats/jobs/{slug}/apply` form with fields: First Name, Last Name, Email, Phone, Location (City), LinkedIn Profile, GitHub URL, Portfolio (optional), Resume/CV (file), Total Years of Experience (number), Years of experience with React (number), Current CTC, Expected CTC, Notice Period (select: Immediate/15 days/30 days/60 days/90 days), "Are you legally authorized to work in India?" (radio Yes/No), "Why do you want to work at {company}?" (textarea), a **custom question the profile cannot answer** (e.g. "What is your preferred start date?" or "Describe your experience with Kubernetes") to trigger `REQUIRES_USER`, and a consent checkbox. `?captcha=1` query flag renders a fake `<div class="g-recaptcha">` so the CAPTCHA pause can be demoed (never solved).
* `POST /demo-ats/jobs/{slug}/apply` stores the submission (table-less: append JSON to `UPLOAD_DIR/demo_ats_submissions.jsonl`), renders a confirmation page containing `Application ID: DEMO-XXXXXX` and text "Thank you for applying", and — if the applicant email belongs to a JobPilot user — enqueues a **simulated** confirmation email via `emails.service.ingest_simulated_email(...)` so the email-classification part of the demo works without Gmail.

## 13. emails + integrations

Integrations:
* `GET /integrations` → `{gmail: GmailStatus {status, email_address, scopes, connected_at, last_synced_at, configured: bool}, accounts: [ConnectedAccountRead], adapters: [AdapterInfo]}`.
* `POST /integrations/gmail/connect` → `{authorization_url}` (state stored on `EmailIntegration.oauth_state`; scopes from `settings.GMAIL_SCOPES` only — **read-only**). If Google is not configured → `ValidationFailed("Gmail OAuth is not configured")` with code `not_configured`.
* `GET /integrations/gmail/callback?code&state` → exchanges code, stores `encrypt_str(json.dumps(credentials))`, redirects to `FRONTEND_URL/emails?connected=1`.
* `POST /integrations/gmail/sync` → `SyncResult {fetched, new, classified, linked, status_updates}`.
* `DELETE /integrations/gmail` → revoke token (best effort) + wipe credentials.
* `GET /integrations/accounts`, `POST /integrations/accounts {source, account_identifier?, credentials?: {username,password}}` (encrypted at rest; mock adapters ignore them), `DELETE /integrations/accounts/{id}`.

Emails:
* `GET /emails?classification=&application_id=&unlinked=&page=` → page of `EmailMessageRead` (never includes raw credentials; `body_text` truncated to 2000 chars in list).
* `GET /emails/{id}`; `POST /emails/{id}/link {application_id}`; `POST /emails/{id}/classify {classification}` (manual override, applies status update); `POST /emails/{id}/read`.
* `POST /emails/simulate {application_id?, kind: EmailClassification, subject?, body?, sender?}` → creates a realistic simulated email (`is_simulated=True`) and runs the same pipeline. Used by the demo and tests.

Service: `emails.service.ingest_message(db, user_id, msg: IncomingEmail) -> EmailMessage` → classify (`emails/classifier.py`: rules first (subject/sender keyword sets with confidence), LLM fallback when confidence < 0.6) → link (`emails/linker.py`: by company domain / `Company.email_domains` / company name in sender or subject / job title in subject, restricted to the user's applications with `SUBMITTED_STATUSES`; most recent wins) → if linked and classification maps via `CLASSIFICATION_TO_STATUS` and the new status is "further along" than current, call `applications.service.transition(...)` with actor `EMAIL` and set `status_applied=True`; INTERVIEW creates an `Interview` row; notifications per type. `ingest_simulated_email(db, user_id, subject, body, sender, application_id=None)` wraps it.
* Gmail client (`emails/gmail_client.py`): thin wrapper over the Gmail API (`users.messages.list` with `q="newer_than:30d (subject:(application OR interview OR offer OR assessment OR recruiter OR position OR role) OR from:(greenhouse OR lever OR workday OR naukri OR linkedin OR indeed))"`, `users.messages.get format=full`), refreshes tokens, re-encrypts on refresh.

## 14. automation + dashboard + worker + seed

Automation:
* `GET /automation/config` → `AutomationConfigRead`; `PUT /automation/config AutomationConfigUpdate` (validates `daily_application_limit ≤ MAX_DAILY_APPLICATION_LIMIT`, `schedule_time` HH:MM, timezone valid, `auto_submit_sources ⊆ adapters with supports_auto_apply`, `source_modes` keys ∈ `JobSourceType`, values ∈ `SourceApplyMode`, and `AUTO_APPLY` only for adapters with `supports_auto_apply` → else 422 `auto_apply_unsupported`).
* **Per-source apply mode** (`AutomationConfig.source_modes: {source: AUTO_APPLY | DISCOVER_ONLY}`). Resolved by exactly one function, `automation.service.resolve_source_mode(config, source)`: stored entry → else `AUTO_APPLY` iff the adapter `supports_auto_apply` → and an adapter without `supports_auto_apply` can never resolve to `AUTO_APPLY` (stored value is downgraded, logged at debug). `AutomationConfigRead.source_modes` carries the *resolved* value for every registered source; `run.config_snapshot.source_modes` records the mode each searched source actually ran in.
* `POST /automation/run {dry_run?: bool}` → starts a run in a background thread → `AutomationRunRead` (status RUNNING). Only one RUNNING run per user (else `ConflictError`).
* `GET /automation/runs?page=` ; `GET /automation/runs/{id}` (with `steps`, `stats`) ; `POST /automation/runs/{id}/cancel`.
* `GET /automation/status → {enabled, next_run_at, last_run: AutomationRunRead | None, running: bool, today: {applications_submitted, limit_remaining}}`.

Pipeline (`automation/pipeline.py`) — `run_pipeline(user_id, trigger, run_id=None, dry_run=False)` executing, each as a recorded step with SUCCESS/FAILED/SKIPPED + stats:
`search → collect → dedupe (ingest) → analyze → filter (min score, posted-within, AVOID, excluded keywords, already applied/skipped) → prioritize (P1 first, then score) → enforce limits (daily limit − submitted today; per-platform limits; `DISCOVER_ONLY` candidates pass through without consuming budget) → queue (`DISCOVER_ONLY` candidates are **not** queued: counted in `stats.discover_only` and listed in the step's `data.discover_only`) → generate answers (+cover letters; a browser-backed application is deferred — left QUEUED — only when no browser is available, whatever its source) → autofill (every `uses_browser` adapter via ApplicationRunner; mock EASY_APPLY in-process) → approval queue (PAUSED/USER_REVIEW) → auto-submit only where allowed (`_auto_submit_allowed`: `auto_submit_enabled` ∧ source ∈ `auto_submit_sources` ∧ adapter `supports_auto_apply`; refuses anything with an unanswered required question) → finish (notification AUTOMATION_COMPLETED with summary)`. `delay_between_actions_seconds` between applications; failures never abort the run — they are recorded and continue; an exception in a step marks the run PARTIAL/FAILED with `error`.

Worker (`app/worker/`): `scheduler.py` `build_scheduler() -> BackgroundScheduler` with (a) a minute-tick job that finds enabled configs whose `schedule_time` in their `timezone` has passed today and `last_run_at` isn't today → `run_pipeline(SCHEDULED)`, (b) hourly Gmail sync for connected integrations, (c) nightly job marking `APPLIED` older than 21 days with no response as `NO_RESPONSE`. `main.py` runs it in the foreground (docker `worker` service). Uses a Redis lock (`SET NX EX`) so API and worker never run the same user's pipeline concurrently (in-memory fallback when Redis is down).

Dashboard:
* `GET /dashboard/stats` → 
```
{ today: {applications, responses, interviews, rejections, pending, jobs_found},
  week: {...same}, month: {...same},
  totals: {jobs_found, jobs_matched, high_match, queued, applications, responses, interviews, offers, rejections, pending_review, requires_input},
  response_rate: float, interview_rate: float, offer_rate: float,
  attention: [{type, title, link, count}] }
```
* `GET /dashboard/charts?range=7d|30d|90d` → `{applications_per_day: [{date, count}], responses_per_day: [...], by_company: [{name, count}], by_source: [{source, count}], by_status: [{status, count}], funnel: [{stage, count}], match_distribution: [{bucket, count}]}`.
* `GET /dashboard/activity?limit=` → recent `AuditLogRead` + `ApplicationEventRead` merged timeline.

Seed (`app/seed.py`, `python -m app.seed`, idempotent): demo user (`settings.DEMO_USER_EMAIL/PASSWORD`) with a complete profile (2 yrs, React/Node/TypeScript/PostgreSQL/Docker/AWS, Bangalore, ₹8 LPA current, ₹12 LPA expected, 30-day notice, authorized in India, no sponsorship), a parsed default resume generated into `UPLOAD_DIR` (a real small PDF built with a minimal writer so download works), preferences (titles Software Engineer / Full Stack Developer / Backend Engineer; locations Bangalore, Hyderabad, Pune, Delhi NCR, Remote; min match 75; 20/day), company preferences (P1: Google, Microsoft, Amazon, Meta, Apple, Netflix; P3: a couple of startups; AVOID: one), skill taxonomy, then runs discovery over all mock adapters + demo ATS, analyzes, and fabricates ~3 weeks of history: ~40 applications across statuses with events, a few emails (simulated) linked, 2 interviews (one with prep), 1 offer, several rejections, notifications, audit logs, and one completed `AutomationRun`. The dashboard must look alive on first login.

---

## 15. Frontend contract (summary — full detail is the OpenAPI at `/openapi.json`)

* Base URL `import.meta.env.VITE_API_BASE_URL` (default `/api/v1`, dev proxy in Vite to `http://localhost:8000`).
* Access token kept in memory (Zustand store, persisted to `sessionStorage` only), refresh via cookie on 401 then retry once.
* Sidebar routes: `/dashboard /jobs /queue /applications /applications/:id /companies /resume /profile /automation /emails /interviews /analytics /settings` + `/login /register`.

---

## Deviations log

* auth+profiles (common): `Pagination` + `paginate()`/`paginate_sequence()` live in `app/modules/common/pagination.py` (PageResponse/OkResponse stay in `common/schemas.py` as specified); everything is re-exported from `app.modules.common`.
* auth+profiles (auth): request schemas enforce the password policy / blank-name rules in the **service** layer (`ValidationFailed` -> 422) instead of pydantic validators, because `core.exceptions`' RequestValidationError handler cannot JSON-serialise the `ValueError` pydantic stores in `ctx` (it returns 500).
* auth+profiles (auth): `auth.service` commits the session before raising on failed login / refresh-token reuse so the audit entry and the token revocations survive `get_db`'s rollback-on-error.
* auth+profiles (auth): `POST /auth/register` also sets the refresh cookie (contract only mentions it for `/auth/login`).
* auth+profiles (profiles): `CandidateContext.resume` is typed `Any | None` - a `resumes.schemas.ResumeRead` when that module is importable, otherwise a small dict - so profiles never hard-depends on the resumes module.
* auth+profiles (companies): added `POST /companies/{id}/blacklist` (the contract only defined the `blacklist_company` service function) so the UI can call it.
* auth+profiles (notifications/audit): `NotificationRead`/`AuditLogRead` expose the ORM attribute `meta` as `metadata` in JSON (matching the DB column name).
* ai+resumes (ai): `get_llm_provider()` / `reset_llm_provider()` / `provider_status()` live in `app/modules/ai/factory.py` and are re-exported lazily from `app/modules/ai/provider.py`, so both import paths work.
* ai+resumes (ai): `tasks.generate_answer()` accepts one extra optional keyword-only `question_key`, and `GeneratedAnswer` carries two additive fields (`question_key`, `is_sensitive`) for the review UI / field mapper.
* ai+resumes (ai): the deterministic answer+canonical-key rules live in `app/modules/ai/answer_rules.py` and the rule-based resume parser in `app/modules/ai/resume_parser.py` (mock internals; reusable by browser/applications).
* ai+resumes (ai): when a real provider errors or returns unusable JSON, the task falls back to the deterministic mock implementation (warning logged) so uploads/answer generation never 500.
* ai+resumes (resumes): `PATCH /resumes/{id}` with `is_default=false` returns 422 (promote another resume instead); `POST /resumes/{id}/reparse` refreshes `parsed_data` in place without bumping `current_version` (only `PUT /parsed-data` creates a version).
* jobs+adapters+matching (adapters): added a ninth mock adapter `COMPANY_CAREERS` (`adapters/mock/company_careers.py`) so the cross-platform duplicates §8/§9 describe ("the same role on LinkedIn + company careers + Naukri") actually exist; `list_adapters()` therefore returns 12 entries.
* jobs+adapters+matching (adapters): `AdapterInfo` carries two additive fields beyond §8 — `rate_limit_per_minute` and `uses_browser` — and `DemoAtsAdapter`/`GreenhouseAdapter`/`LeverAdapter` share the hosted-form flow via `adapters.demo_ats.GenericAtsFormAdapter`.
* jobs+adapters+matching (matching): the §10 "preferences/company 0.05" weight is implemented as a *preference-fit* component (work mode / employment type / preferred technologies / excluded keywords) in `scoring.score_preferences`; company priority stays a pure +5/+2/0 adjustment so §10's "never more than +5" cap holds. `scoring.combine(**parts)` is keyword-only and redistributes the weight of any part passed as `None`.
* jobs+adapters+matching (matching): `analyze_job`/`analyze_jobs` accept optional keyword-only `facts`/`priority`/`write_audit` so a batch computes the candidate context once; `ai.tasks.explain_match` is called with a flat scores dict (`match_score`, `skill_match`, `experience_match`, `location_match`, `salary_match`, `company_priority`, `weights`, `parts`).
* jobs+adapters+matching (jobs): `POST /jobs/{id}/queue|skip` return a minimal `QueuedApplicationRead` (id, job_id, status, priority, match_score, skipped_reason) instead of the applications module's `ApplicationRead`, which jobs must not import; `GET /jobs/sources` returns one `SourceInfoRead` per adapter with `job_count` + `connected` merged in rather than a separate counts map.
* jobs+adapters+matching (jobs): `JobDetail` exposes the detailed source rows as `job_sources` (`JobCard.sources` stays the list of `JobSourceType` values), and `jobs.service.get_company_priority(db, user_id, company)` is the shared lazy wrapper around `companies.service.get_priority` (default `P2`) that matching reuses.
* browser+demo_ats (browser): each `BrowserSessionHandle` starts its own `sync_playwright()` instance instead of one per process (§12 `BrowserManager`) - the Playwright sync API is bound to the thread that created it, so the runner must build the handle in the thread that drives the page; `BrowserManager.open_context(...)` stays as the documented factory.
* browser+demo_ats (browser): `DetectedField.options` is a list of `{value, label, selector}` objects (not bare strings) so radio groups can be one field per group and autofill can click the right input; a radio group's own selector is `input[type="radio"][name="..."]`.
* browser+demo_ats (browser): `autofill.fill_form(page, detected, answers)` keeps the contract signature and adds three optional keyword args (`session`, `application_id`, `screenshot_name`) - passing either `session` or `application_id` writes the post-fill screenshot required by §12 to `UPLOAD_DIR/screenshots/<application_id>/` and sets `FillResult.screenshot_path`; the `filled`/`skipped`/`needs_user` entries are plain JSON-safe dicts (TypedDict rows: `{selector,key,value_preview,field_type}` / `{selector,key,label,required,reason}`) so they can be copied straight into `Application.form_snapshot`.
* browser+demo_ats (browser): added `detector.detect_form_from_html(html, url)` (stdlib `html.parser`, same rules as the injected JS) and `session.is_browser_available()` so mapping/detection are unit-testable and callers degrade gracefully when Chromium is not installed; `GET /browser/status -> {available, headless}` exposes the probe.
* browser+demo_ats (demo ATS): `GET /demo-ats/jobs.json` returns a bare JSON array (one object per posting, with `slug`, `posted_hours_ago`, both `logo_url` and `company_logo_url`, `apply_url`, `application_type="ATS_FORM"`, `source="DEMO_ATS"`, `custom_questions`); `POST /demo-ats/jobs/{slug}/apply` re-renders the form with a 422 when a required field is missing.
* emails+integrations (integrations): `GET /integrations/gmail/callback` is the one authenticated-by-design exception to §0 - Google redirects the browser there without our bearer token, so the single-use `EmailIntegration.oauth_state` (cleared on use) is what identifies and authorises the user; every other integrations/emails endpoint requires `get_current_user`.
* emails+integrations (emails): `emails.service.ingest_message` takes two extra optional keyword-only arguments (`integration_id`, `application_id`) and `applications.service.transition/record_event` are imported lazily - when that module is unavailable (or its signature does not match) the status change is applied directly with an equivalent `ApplicationEvent`, so the pipeline works during parallel development.
* emails+integrations (emails): added `POST /emails/{id}/unlink` (detach a wrongly linked message) beyond §13, and the email-driven notification is skipped when `applications.service.transition` already raised one for the same type, so a status change never notifies twice.
* emails+integrations (integrations): `integrations.service.sync_gmail` commits before re-raising so `status=ERROR` + `last_error` survive `get_db`'s rollback-on-error (same pattern as `auth.service`); `sync_all_connected(db)` (worker entry point, re-exported from `app.modules.integrations`) commits per user and never raises.
* emails+integrations (integrations): additive read fields beyond §13 - `GmailStatus.sync_enabled`/`last_error`, `SyncResult.error`, and `AdapterInfoRead` mirrors `adapters.base.AdapterInfo` plus `connected: bool`; `DELETE /integrations/gmail` returns the resulting `GmailStatus` instead of an empty body.
* applications: `ApplicationRead` carries six denormalised non-column fields (`job_title`, `company_name`, `company_logo_url`, `location`, `application_type`, `ready`) so the list/queue screens need no second call; `form_snapshot` appears only on `ApplicationDetail`.
* applications: `ApplicationDetail.emails` is a list of plain JSON objects rather than `EmailMessageRead`, so the module never has to import the concurrently-written emails module.
* applications: `start_application`/`resume_automation` commit before spawning the background thread (which opens its own `session_scope()`), and `approve()` commits before raising on a failed submission so the `mark_failed` record survives `get_db`'s rollback-on-error.
* applications: `POST /{id}/approve` returns 200 with the paused application when the adapter answers `REQUIRES_USER` (only `FAILED` raises `AppError`); `POST /{id}/start` and `POST /{id}/resume-automation` accept an optional `{run_in_background: bool}` body so tests and the automation pipeline can run the runner synchronously.
* applications: added `GET /applications/{id}/review` (the `ReviewSummary` on its own) and a `?ready=` filter on `GET /applications/queue`; `transition()` defaults `actor`/`message`, and `mark_failed()` takes an extra keyword-only `final` flag for definite (non-retryable) failures.
* applications (interviews): `GET /interviews` returns the §0 `PageResponse` envelope and also accepts `status`; added `GET /interviews/{id}`; `InterviewRead` carries denormalised `company_name`/`job_title`.
* applications (browser/runner): `ApplicationRunner(application_id, db=None)` takes an optional session so a caller can run it synchronously inside its own transaction; the thread registry that makes a duplicate concurrent run (and therefore a duplicate submission) impossible lives in `app/modules/applications/executor.py`.
* automation+dashboard (automation): `pipeline.run_pipeline(user_id, trigger, run_id=None, dry_run=False, *, db=None, sleep_fn=None, acquire=True)` keeps the §14 positional signature and adds three keyword-only arguments — `db` (run inside the caller's session; the API's synchronous path and tests use it), `sleep_fn` (makes `delay_between_actions_seconds` patchable) and `acquire=False` (the scheduler already holds the user's lock).
* automation+dashboard (automation): `automation.service.start_manual_run(db, user_id, *, dry_run=False, background=True)` commits before spawning the daemon thread (the thread opens its own `session_scope()` and must see the RUNNING row) — same pattern as `auth.service`; `background=False` runs the pipeline synchronously.
* automation+dashboard (automation): config validation lives in `automation.service.validate_config_update` (raising `ValidationFailed` with stable codes `invalid_schedule_time` / `invalid_timezone` / `invalid_daily_limit` / `daily_limit_too_high` / `invalid_platform_limit` / `unknown_source` / `auto_submit_unsupported`) instead of pydantic validators, so the API returns a typed error body.
* automation+dashboard (automation): `AutomationRun.stats` carries four keys beyond the model's docstring — `filtered_out`, `ready_for_review`, `would_queue` (dry runs) and `filter_reasons` (`below_min_score`, `too_old`, `avoid_company`, `excluded_keyword`, `already_applied`, `already_skipped`, `limit_reached`) — and every run reports the full key set (zeros included).
* automation+dashboard (automation): `POST /automation/run` returns **202** (the run is still RUNNING in a background thread); `GET /automation/status.today` additionally returns `daily_limit`.
* automation+dashboard (automation): "needs your input" counts only **required** `NEEDS_USER_INPUT` answers (mirrors §11's approve rule), while auto-submit stays stricter and refuses when *any* answer is unanswered; auto-submit also requires `config.auto_submit_enabled`, the source on `auto_submit_sources` and `adapter.supports_auto_apply`.
* automation+dashboard (automation): the per-user Redis lock (`SET NX EX 3600`, key `automation:lock:<user_id>`) falls back to a process-local `dict` + `threading.Lock`, and the Redis backend is skipped entirely when `settings.ENV == "test"` so the suite never waits on a socket.
* automation+dashboard (dashboard): `GET /dashboard/activity` returns a flat `list[ActivityItem]` with a `kind` discriminator (`AUDIT` / `EVENT`) — the union of `AuditLogRead` and `ApplicationEventRead` fields plus a `link` — rather than two separately typed lists, so the frontend renders one timeline.
* automation+dashboard (dashboard): jobs are a global table, so the user-scoped reading of `jobs_found` is "jobs analyzed for this user" (`totals`) and "jobs created in the window that were analyzed for this user" (`today`/`week`/`month`); `GET /dashboard/charts` additionally returns `range`, `start_date` and `end_date`, and `funnel.interviews` counts applications that reached the interview stage while `totals.interviews` counts `Interview` rows.
* automation+dashboard (worker): the Gmail sync job runs every 30 minutes (§14 says hourly) and a fourth daily job `cleanup_expired_browser_sessions` runs at 03:00 UTC; `mark_no_response` runs at 02:00 UTC and falls back to a direct status update when `applications.service.transition` is unavailable.
* automation+dashboard (seed): `app.seed` exposes `seed_demo_data(db, *, force=False) -> SeedSummary` (the `db` argument lets tests seed inside the test session) and `python -m app.seed [--force]` wraps it in `session_scope()`; the demo PDF is written by `app.seed.build_resume_pdf()` and goes through `resumes.service.create_resume_from_bytes` so it is really parsed.
* automation+dashboard (alembic): the autogenerated initial migration was hand-reviewed to remove SQLite-only artefacts — `batch_alter_table` blocks became plain `op.create_index`/`op.drop_index`, and `sa.text('(CURRENT_TIMESTAMP)')` became `sa.func.now()` — so it runs unchanged on PostgreSQL; `tests/test_migrations.py` asserts `compare_metadata` reports **no** differences (only `compare_type`/`compare_server_default` are disabled, because SQLite has no real type affinity).
* integrator (jobs/companies): `GET /jobs` now resolves `company_priority` through `companies.service.get_priority_map` and filters `?priority=` through the new `companies.service.prioritized_company_ids(db, user_id)` — the list page used to match preferences on the exact normalised name only, so a job card showed P2 while `GET /jobs/{id}` showed P1 for the same company ("Google" vs "Google (Demo Careers)"). List, detail and the filter now share `resolve_priority`'s rules.
* integrator (applications): `approve()` commits the approval bookkeeping **before** `_submit_through_adapter` and commits + refreshes again afterwards — the submission drives a browser for several seconds and the held write transaction blocked the bundled demo ATS from writing its confirmation email (SQLite "database is locked"). Consequently `mark_submitted()` no longer transitions to APPLIED when the application is already further along (`emails.service.STATUS_ORDER`) or terminal, so `POST /applications/{id}/approve` may legitimately return `APPLICATION_RECEIVED` when the ATS confirmation email won the race; `applied_at`, `external_application_id` and the SUBMITTED event are recorded either way.
* integrator (adapters/browser): `GenericAtsFormAdapter.fill_application` fills every field it can **before** pausing for an unanswered required question (contract §12's documented order) instead of returning REQUIRES_USER straight after mapping — the review screen used to get an empty `form_snapshot` and no screenshot. The paused snapshot now carries `filled`/`skipped`/`needs_user`/`missing`, and `ApplicationRunner` records the `FORM_FILLED` event plus the `application.form_detected` / `application.field_filled` audit entries on the pause path as well as the success path.
* integrator (core): a **file-backed** SQLite `DATABASE_URL` is opened with `journal_mode=WAL`, `busy_timeout=10000` and `synchronous=NORMAL` so the API, the automation threads and the in-process demo ATS can write concurrently; `:memory:` (the test suite) is untouched.
* integrator (seed): `TODAY_APPLICATIONS = 3` of the APPLIED applications are dated a few hours ago **today** (in `DEMO_TIMEZONE`, via `automation.limits.day_bounds`) so `GET /dashboard/stats -> today.applications` is non-zero on first login; the rest of §14's three-week history is unchanged and the seed stays idempotent.
* integrator (scripts): added `backend/scripts/smoke_e2e.py --base-url [--with-browser]`, an HTTP-level end-to-end smoke test (login, every list screen, demo ATS, discovery, a full automation run, an email that advances an application, and optionally the queue -> autofill -> answer -> approve -> confirmation-email browser path) that prints PASS/FAIL per step and exits non-zero on any failure.
* reviewer R2 (core): every `DateTime(timezone=True)` column is now `app.models.base.UTCDateTime`, a
  `TypeDecorator` that normalises to UTC on bind and re-attaches `timezone.utc` on load. SQLite has no
  time-zone type, so §0's "timezone-aware UTC, ISO-8601 in JSON" only held on PostgreSQL — the demo/dev
  database returned offset-less timestamps that every client read as local time. Same DDL, no migration.
* reviewer R2 (applications): `POST /{id}/resume-automation` returns **409** `already_submitted` for an
  application already in/past `APPLIED` (it used to re-drive the adapter and submit twice), and both
  `approve()` and `resume_automation()` now run under `applications.executor`'s single-flight claim —
  `approve()` holds it for the whole submission, so two concurrent approvals submit exactly once
  (409 `already_running` for the loser). `executor.is_running()` no longer treats an unstarted claimed
  thread as finished.
* reviewer R2 (applications): `AutomationConfig.notify_on_input_required` is now actually read — the
  `INPUT_REQUIRED` notification on pause is skipped when the user turned it off.
* reviewer R2 (emails): `POST /emails/{id}/link` returns **409** `already_linked` when the message is
  linked to a *different* application (unlink first) — silently moving the link advanced two
  applications off one email. Re-sending the same link/classification is now a no-op. A sender domain is
  learned onto the **global** `companies.email_domains` only from a non-`OTHER` classification, and the
  job-title link strategy is skipped for bulk job-board senders.
* reviewer R2 (jobs): `GET /jobs?status=<unknown>` is **422** `invalid_status` instead of 500;
  `IngestResult` gained `skipped` (a listing whose company name normalises to "" is dropped instead of
  aborting the whole batch); `build_search_query` forwards the user's `work_modes`; `JobCard.sources`
  is de-duplicated. `jobs.service.get_job_details(db, user_id, job_ids)` is the batch form of
  `get_job_detail` (the queue page used to cost four statements per row).
* reviewer R2 (profiles/matching): a JSON `null` sent for a NOT NULL JSON column (`skills`,
  `work_authorization`, `desired_titles`, …) is stored as the empty list/dict instead of 500-ing the
  whole request; `min_match_score = 0` is honoured rather than silently replaced by the default.
* reviewer R2 (automation): a **dry run** no longer sets `AutomationConfig.last_run_at`, so previewing
  does not consume the day's scheduled slot; `POST /automation/run` takes the per-user lock before
  inserting the run row (the guard used to be check-then-act) and always closes the row out if the
  background thread fails; `POST /automation/runs/{id}/cancel` no longer force-releases that lock while
  the pipeline is still executing its current step.
* reviewer R2 (dashboard): `responses`/`response_rate` count only applications that were actually sent
  (a replied-then-skipped application used to push the rate past 100%), an interview folds into the
  response set so the funnel stays monotonic, and the week/month/chart windows start at **local
  midnight** rather than `now − N×24h` (which lost a day across a DST change).
* reviewer R2 (scalability): `GET /applications`, `/applications/queue` and `/companies` order and
  paginate in SQL instead of materialising every row and slicing in Python; composite indexes for the
  "(owner, sort column)" access pattern live in the models and in
  `alembic/versions/a1c4f7b28e10_composite_indexes.py`. Per-page query budgets are documented in
  `backend/README.md` and pinned by `tests/test_review_regressions.py`.
* db conventions (core): every table now carries `is_active` and `deleted_at`
  (`app.models.base.LifecycleMixin`) and **deletes are soft**. `DELETE /resumes/{id}`,
  `/companies/preferences/{id}`, `/integrations/accounts/{id}`, `/interviews/{id}` and
  `/browser/sessions/{id}` keep their status codes and bodies, but tombstone the row instead of
  removing it; a global `do_orm_execute` filter (`app/core/soft_delete.py`) hides tombstones from
  every ORM SELECT, `Session.get` included, unless the statement passes
  `execution_options(include_deleted=True)`. `DELETE /resumes/{id}` additionally **keeps the
  uploaded file on disk** (a soft delete that destroys the bytes is reversible in name only);
  `app/seed.py --force` is the one caller that still hard-deletes, and it reads with
  `include_deleted=True` so it also clears tombstones.
* db conventions (auth): `users.role` (the enum column) is **gone**. Roles are rows in
  `master.roles` and are granted through the `master.user_roles` junction;
  `User.role` is now a read-only property returning the most privileged role held, so
  `require_roles`, the JWT `role` claim and `UserRead.role` are byte-for-byte unchanged.
  `UserRead` gains an additive `roles: list[str]` (every role held, sorted).
  `auth.service` gains `assign_role(db, user, role_name)`, `revoke_role(db, user, role_name)`,
  `get_role(db, name)` and `ensure_default_roles(db)`; `create_user(..., role=UserRole.USER)` keeps
  its signature and now writes a `user_roles` row. `UserRole` stays the vocabulary of well-known
  role names; the junction's model class is `UserRoleAssignment` because that name was taken.
* db conventions (schema): the keys a user can delete and re-create became **partial unique
  indexes** (`... WHERE deleted_at IS NULL`) — `users.email`,
  `company_preferences (user_id, normalized_name)`, `connected_accounts (user_id, source)`,
  `browser_sessions (user_id, source)`, `roles.name`, `user_roles (user_id, role_id)` — so a
  tombstone no longer holds a unique key hostage. Keys nothing user-facing deletes stay plain
  UNIQUE constraints. One migration (`c5e81b60a4d7`) adds the columns, creates the two tables with
  their `USER`/`ADMIN` rows, backfills the grants from `users.role`, drops that column and swaps the
  constraints; it runs on PostgreSQL and SQLite and downgrades cleanly.

* database conventions (audit columns): every table gained `created_at`, `updated_at`, `created_by`
  and `updated_by` (migration `b9f41c7d2e58`), so all 27 now carry the same seven standard columns
  from one `StandardColumnsMixin`. The two timestamps are **database-owned** — no Python-side
  `default=`/`onupdate=`, a `DEFAULT now()` server default on both, and one
  `trg_<table>_updated_at` trigger per table calling `public.set_updated_at()` so a raw `UPDATE`
  moves `updated_at` too. The trigger's `WHEN (OLD::text IS DISTINCT FROM NEW::text)` guard leaves
  no-op updates alone; it compares row *text* because `OLD.* IS DISTINCT FROM NEW.*` raises on the
  20 tables with a `json` column. Consequence for callers: `obj.created_at` is `None` until the
  flush. `created_by`/`updated_by` are stamped by flush listeners from the actor published in
  `app/core/actor.py` and are **not** exposed by any API schema; `NULL` means a system write.
  Three deviations from the brief: the request actor is carried on the `Session` rather than only
  in a `ContextVar` (a `ContextVar` set in a sync FastAPI dependency is discarded, and resetting it
  in a `yield` dependency raises), `ActorMiddleware` publishes the `ContextVar` instead; the two
  scheduler housekeeping jobs (`mark_no_response`, `cleanup_expired_browser_sessions`) deliberately
  write with no actor because they act on nobody's behalf; and on SQLite the two audit columns are
  added without their foreign key, since adding a constraint there means rewriting the table.
