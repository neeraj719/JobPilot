# ats — ATS analysis against a job description, safe apply, job targets and tailoring

You are **ats**, a senior full-stack developer on JobPilot AI. Read
`notes/resume-studio-plan.md` (rules, ownership, contracts — binding), then
`notes/resume-studio-spec.md` §3, §4, §5, §6, §9, §11–§13, then this file. Before writing
code read `backend/app/modules/resumes/{recommendations,apply,service,schemas}.py` (reuse
the scoring pieces and every guard), `backend/app/modules/matching/` (skill/title scoring —
read only), `backend/app/modules/companies/{service,board_detect}.py` and
`backend/app/modules/adapters/**` (board APIs), `backend/app/modules/applications/executor.py`
(background-thread pattern), `backend/app/modules/ai/{tasks,prompts,skills}.py`,
`frontend/src/features/resume/components/ApplySuggestionsDialog.tsx` (the apply UX to
mirror), `frontend/src/pages/resume/{AtsOptimizer,JobTargets,JobTargetDetail}.tsx`
(your placeholders). Test DB `jobpilot_test_ats`; ports 8092 / 5202; progress file
`notes/ats-progress.md`; migration id `b4d6f8a0c2e4` (down_revision `a9c3e5b7d1f0`). Do not
commit.

## Outcome

A user pastes/uploads a job description or gives a posting URL, picks a resume, and gets a
transparent **estimated** ATS compatibility report (overall + categories, matched/missing
keywords, weak content, concrete recommendations with before/after bullets). They apply
suggestions one by one or all safe ones (preview, edit, ignore, undo), the analysis reruns
and the new score shows. They save **job targets** (company + role + JD snapshot + status
+ notes + selected resume version), look a company up for its real open roles, tailor a
resume to a target (new TAILORED resume linked to its source, every change explained), compare
source vs tailored, refresh the JD later, and track the application status per target.

## Data model (`app/models/ats.py`, schema `media`, plan §5)

* `job_targets`: user_id, company_name, normalized_company, company_id (FK master.companies,
  SET NULL), role_title, job_url, location, work_mode (WorkMode), required_skills JSON,
  deadline, status (`JobTargetStatus`: SAVED, PREPARING, READY, APPLIED, INTERVIEW, OFFER,
  REJECTED, ARCHIVED — add the enum at the end of `enums.py`), notes, follow_up_at,
  source_resume_id (FK resumes, SET NULL), tailored_resume_id (FK resumes, SET NULL),
  tailored_resume_version int nullable, submitted_resume_version int nullable,
  application_id (FK transaction.applications, SET NULL), job_id (FK unified.jobs, SET
  NULL), latest_snapshot_id (FK job_description_snapshots, SET NULL), last_analysis_id (FK
  ats_analyses, SET NULL), last_analyzed_at. Partial unique
  (user_id, normalized_company, lower(role_title), coalesce(job_url,'')) WHERE deleted_at IS
  NULL — or a simpler fingerprint column; pick one and document it.
* `job_description_snapshots`: job_target_id, source (PASTED|UPLOADED|URL|BOARD), url,
  fetched_at, title, company, raw_text (capped 50 k chars), structured JSON (required
  skills, preferred skills, responsibilities, qualifications, keywords, seniority, years),
  text_sha256, changed_from_previous bool.
* `ats_analyses`: user_id, resume_id, resume_version, job_target_id nullable, snapshot_id
  nullable, status (PENDING|RUNNING|DONE|FAILED), progress 0–100, error, overall_score,
  category_scores JSON, matched_keywords JSON, missing_keywords JSON, weak_items JSON,
  parse_risks JSON, methodology_version, weights JSON, ai_provider/model nullable,
  duration_ms, completed_at.
* `optimization_suggestions`: analysis_id, ordinal, kind (ADD_SKILL|REPLACE_BULLET|
  REPLACE_SUMMARY|REORDER_SECTION|ADD_KEYWORD_CONTEXT|MANUAL), title, rationale,
  target_path, before, after, safe bool, requires_confirmation bool, confirmation_label,
  estimated_gain, status (PROPOSED|APPLIED|IGNORED|EDITED), applied_version nullable,
  checks JSON (the guard results).
Standard columns, FKs with ondelete, indexes on user_id/status/resume_id, triggers, soft
delete, SQLite-safe migration. Apply to the live DB with `alembic upgrade b4d6f8a0c2e4`.

## Backend (`app/modules/ats/`, mounted at `/api/v1/ats`)

### JD intake (`jd.py`)
* `POST /ats/jd/parse` `{text}` and `POST /ats/jd/upload` (PDF/DOCX/TXT via
  `resumes.extraction`) → structured JD: deterministic first (skills via `ai/skills.py`
  aliases, "required/preferred" by section cues and verbs like must/should/nice-to-have,
  years via regex, title via the first heading), then optional model polish through
  `analyze_job_description` (plan §4.3), validated: the model may only *classify* strings
  that occur in the text.
* `POST /ats/jd/fetch` `{url}` → the same, from a posting URL. Known vendors first via the
  public APIs the adapters already use (Greenhouse `boards-api`, Lever `api.lever.co`,
  Ashby posting API, SmartRecruiters posting API — detect from the URL); otherwise fetch the
  page under plan §6 (SSRF guard, caps), prefer JSON-LD `JobPosting` when present, else the
  main text with scripts/nav stripped. Return `source` and `confidence`; if nothing
  readable, 422 `jd_unreadable` telling the user to paste the text.
* Company lookup `GET /ats/companies/lookup?name=` → `{company, board, open_roles:[{title,
  location, url, external_id}]}` using `companies.service.detect_board` / `verify_board` and
  the boards adapters; if several roles match the target role, return them all — the UI
  asks the user to choose, never guesses. Rate-limit outbound lookups.

### Analysis (`scoring.py`, `service.py`) — transparent and configurable
* `GET /ats/methodology` → categories, weights, version, the "estimate, not an employer's
  ATS" disclaimer. Weights live in one dict (`ATS_WEIGHTS`, version string), overridable per
  request body `weights?` within bounds.
* Categories (0–100 each, deterministic): keyword_coverage (JD keywords found in the
  resume, exact + alias + lemma-light), title_alignment (reuse
  `recommendations.role_matches` / `matching` title logic), required_vs_preferred
  (required skills weighted more), technical_skills, experience_relevance (years vs JD
  range, recent titles vs role), achievement_quality (reuse bullet checks: verbs, metrics,
  length), readability_format (bullet length, passive voice-ish cues, section lengths),
  section_completeness, parse_risk (missing contact, odd characters, empty sections,
  tables unknown). Overall = weighted sum. Keep every signal explainable: each category
  returns `evidence[]` strings the UI shows.
* Suggestions: reuse `recommendations` + `apply.build_apply_plan`-style change building
  **against the JD** (missing required skill → ADD_SKILL only when evidenced in the
  profile/resume, else `requires_confirmation` "I have used X"; weak bullet → REPLACE_BULLET
  candidates through `apply.strengthen_bullet` guards; summary → REPLACE_SUMMARY through
  `summary_problem`; missing JD keyword with evidence → ADD_KEYWORD_CONTEXT suggesting where
  it fits; otherwise MANUAL advice). Mark `safe` only for provably safe changes.
* `POST /ats/analyses` `{resume_id, jd: {text} | {snapshot_id} | {job_target_id},
  weights?}` → runs the deterministic analysis synchronously (target < 2 s), persists, then
  if a model is configured polishes suggestions in a background thread (executor pattern,
  `ai_user` context per plan §4.4, idempotent, status/progress on the row). `GET
  /ats/analyses/{id}` polls; `GET /ats/analyses?resume_id=&job_target_id=` lists.
* `POST /ats/analyses/{id}/apply` `{suggestion_ids:[...], edits:{id: after}}` → validate
  against the stored suggestions (server-side, never trust client kind/target), apply to a
  deep copy of `parsed_data`, save via `service.update_parsed_data(change_source=AI,
  note="ATS: applied N suggestions for <company/role>")` (an edited text → USER), mark
  suggestion statuses, **rerun the analysis** on the new version and return
  `{resume, analysis, applied, skipped}`. 409 `stale_resume` if the resume version moved.
  `POST /ats/analyses/{id}/ignore` `{suggestion_ids}`. Undo = the builder's restore or the
  existing Undo pattern (previous version → new version).
* `POST /ats/analyses/{id}/auto-optimize` `{mode: "new_resume" | "new_version", name?}` →
  applies every `safe` suggestion (never the confirmation ones) and reorders skills/sections
  to the JD; `new_resume` creates a TAILORED resume via `create_resume_from_parsed`
  (source_resume_id, change_source AI); returns the explanation list (`what`, `why`, `evidence`).

### Job targets (`targets.py`)
CRUD `GET/POST /ats/targets`, `GET/PATCH/DELETE /ats/targets/{id}` (soft delete), filters
status/company/search, pagination like `jobs`. `POST /ats/targets/{id}/snapshot` (paste/
upload/url/board) → new snapshot, `changed_from_previous` by text hash, diff of required
skills vs previous; `POST …/refresh` re-fetches from the stored URL. `POST …/tailor`
`{source_resume_id}` → snapshot required → analysis → auto-optimize `new_resume` named
"<resume> — <Company> <Role>" → links `tailored_resume_id`, status PREPARING→READY. `GET
…/compare` → source vs tailored (builder diff endpoint when present, else your field diff,
plan §4.2). `PATCH` status transitions audited; setting APPLIED records
`submitted_resume_version` and optional `application_id` (if the user applied through
JobPilot: look up `Application` by job_id/user — read only). `GET /ats/summary` (plan §4.6).
When a target has `job_id` (created from a discovered job: accept `job_id` in POST and copy
title/company/description into the first snapshot), link back to `/jobs`.

## Frontend (`src/features/ats/**`, `qk.ats`)

* **ATS Optimizer** (`/resume/ats`, accepts `?resume=&target=`): step strip — 1 Resume
  (select, shows version) · 2 Job description (tabs Paste / Upload / URL / From a saved
  target / From a discovered job) · 3 Results. Results: score ring with the "estimated"
  label and methodology popover (weights, version, disclaimer), category bars with evidence
  on expand, matched/missing keyword chips (missing ones with "where it could fit"),
  weak/irrelevant content list, recommendations list with per-item Apply / Edit / Ignore,
  before→after diff for bullets, "Apply all safe" (pre-ticked safe items, confirmation rows
  unticked with their label, like `ApplySuggestionsDialog`), progress while the model
  polishes (non-blocking; deterministic results show immediately), after apply: new score +
  delta, Undo toast. "Save as job target" and "Auto-optimize → new resume" buttons.
* **Job-Specific Resumes** (`/resume/targets`): board/table by status (Saved · Preparing ·
  Ready · Applied · Interview · Offer · Rejected · Archived) with search, company filter,
  deadline/follow-up badges; "New target" dialog: company (lookup → shows the board's open
  roles to pick from; if none, paste JD), role, URL, deadline, notes, source resume.
* **Target detail** (`/resume/targets/:id`): header (company, role, status select, links),
  JD snapshot (structured view + raw text, "Refresh" with change highlights), analysis card
  (score, missing requirements), tailored resume card (version, Open in editor → builder
  route, Export PDF/DOCX → builder endpoint, Compare source vs tailored side-by-side with
  changes explained), activity (snapshots, analyses, status changes), notes/follow-up.
  Empty/loading/error states; ConfirmDialog for delete/archive; toasts.

## Tests
`tests/test_ats_*`: scoring determinism and weights (fixtures with 3 JD/resume pairs and
expected ordering), JD structuring (required vs preferred, years), URL fetch guards (private
IP refused, redirect re-check, size cap — mock httpx), vendor URL detection, company lookup
with several roles returned unguessed, analysis create/poll/list, apply with server-side
validation (unknown id 422, stale 409, invented number rejected, confirmation items not in
"safe"), rerun after apply, auto-optimize creates a TAILORED resume with source link and
AI change_source, targets CRUD + status audit + snapshot change detection + refresh,
compare, ownership 404s, summary. Run with your DB: your tests + `tests/test_resumes.py
tests/test_resume_apply.py tests/test_resume_recommendations.py tests/test_companies*.py`.
`npm run build`. Browser: user `ats.check@jobpilot.ai` with an uploaded sample resume,
paste a real-looking JD, analyse, apply safe suggestions, see the rerun, save as target,
tailor, compare; screenshots light+dark into `notes/screenshots/ats/`.

## Constraints recap
Estimates, never guarantees (label every score). Never add unconfirmed facts; the model
only classifies/rephrases text that exists. SSRF and size guards on every fetch. Outbound
calls rate-limited and mocked in tests (`conftest` already blocks job-board network — read
`_no_job_board_network`). No edits to `resumes/`, `matching/`, `applications/`, `companies/`,
`adapters/`, `Sidebar.tsx`; write shims per plan §3 if you must. Keep the app importable.
Update `notes/ats-progress.md` as you go. Report per plan §8.
