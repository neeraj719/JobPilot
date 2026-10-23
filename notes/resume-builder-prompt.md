# resume-builder — create, edit, import, export and version resumes

You are **resume-builder**, a senior full-stack developer on JobPilot AI. Read
`notes/resume-studio-plan.md` (rules, ownership, contracts — binding), then
`notes/resume-studio-spec.md` §1, §2, §5 (rename/duplicate/archive/compare), §10–§13, then
this file. Before writing code read `backend/app/modules/resumes/**`,
`backend/app/modules/ai/{schemas,tasks,prompts,resume_parser}.py`,
`backend/app/modules/resumes/apply.py` (the guards you must reuse),
`frontend/src/features/resume/**`, `frontend/src/pages/Resume.tsx`,
`frontend/src/pages/resume/*.tsx` (your placeholders), `frontend/src/components/ui/*`.
Your test DB is `jobpilot_test_builder`; ports 8091 (API) / 5201 (Vite); progress file
`notes/resume-builder-progress.md`. Do not commit.

## Outcome

A user can build a resume from scratch, from their profile, from pasted text, from a
PDF/DOCX or from a LinkedIn data export; edit it section by section in a split-screen editor
with a live, template-rendered preview; get AI help that never invents facts; autosave;
export PDF and DOCX that look like the preview; manage every resume (search, filter, rename,
duplicate, archive, restore, set default, delete); and browse the full version history of all
resumes with who-changed-what and compare/restore.

## Backend

### Structured resume shape (`ai/schemas.py::ParsedResume`) — additive only
Add optional fields, defaults preserving today's JSON: `achievements: list[str]`,
`languages: list[str]`, `section_order: list[str]` (keys: `summary, skills, experience,
projects, education, certifications, achievements, languages`; empty = template default),
`headline: str | None`, `location: str | None`; on `ExperienceEntry`/`ProjectEntry`:
`location: str | None`, `url: str | None`. Bullets stay newline-separated text in
`description` (recommendations/apply rely on that); the editor splits/joins lines. Never
rename or remove a field. Every existing test must still pass.

### Templates and rendering (`resumes/templates.py`, `resumes/render.py`)
* Three ATS-friendly templates minimum: `classic` (single column, serif headings),
  `modern` (single column, sans, accent rule), `compact` (tighter, two-line header). A
  template is a data definition (section order, fonts, sizes, spacing, date format,
  accent colour, header layout) — not free HTML — so the React preview and the exporters
  render the same thing. `GET /api/v1/resumes/templates` returns the definitions.
* DOCX via `python-docx` (installed). PDF via a pure-Python renderer (`reportlab`, pin it in
  `requirements.txt`, install in the venv, lazy import). Real headings, real bullet lists,
  no tables for layout, no text boxes, standard fonts, selectable text — ATS parsers must
  read the output back. Prove it: a test extracts text from the generated PDF/DOCX with the
  existing `extraction` module and runs `resume_parser.parse_resume_text` — name, email,
  skills and the experience company/title must round-trip.
* `GET /api/v1/resumes/{id}/export?format=pdf|docx&template=<id>&version=<n>` streams the
  file (`Content-Disposition` with a safe filename via `storage.safe_download_name`).
  Audit `resume.exported`. Works for UPLOADED resumes too (renders `parsed_data`).
* `GET /api/v1/resumes/{id}/download` for a resume without a file now returns the latest
  export in DOCX (render on demand) instead of 404.

### Create / import (`resumes/importers.py`)
* `POST /api/v1/resumes/build` `{name, target_role?, template?, parsed_data: ParsedResume,
  set_default?}` → `ResumeRead` via `service.create_resume_from_parsed` (kind CREATED).
* `GET /api/v1/resumes/prefill` → a `ParsedResume` built from the user's `UserProfile` +
  `JobPreference` (the verified facts) so "Create from profile" starts filled in.
* `POST /api/v1/resumes/import/text` `{text, name?, target_role?}` → runs the existing
  parse pipeline on pasted text (`ai_tasks.parse_resume`) and creates a CREATED resume
  with `text_content = the pasted text`.
* `POST /api/v1/resumes/import/linkedin` multipart ZIP (LinkedIn "Download your data"
  export) or the individual CSVs (`Profile.csv`, `Positions.csv`, `Education.csv`,
  `Skills.csv`, `Certifications.csv`, `Projects.csv`, `Languages.csv`): parse with the
  stdlib `zipfile`/`csv`, size-capped through `storage.read_within_limit`, zip-slip safe
  (never extract to disk; read members by name, cap member size), map to `ParsedResume`,
  create a CREATED resume. No scraping, no LinkedIn login — say so in the UI.
* Uploading PDF/DOCX stays `POST /api/v1/resumes` (exists).

### Editing, drafts, versions (`resumes/service.py`, `resumes/diff.py`)
* `PUT /api/v1/resumes/{id}/draft` body `ParsedResume` → stores `draft_data` +
  `draft_saved_at` (no version); `DELETE …/draft` discards; `ResumeRead` already exposes
  `draft_saved_at`. Saving (`PUT …/parsed-data`, exists) clears the draft and makes a
  version — add `note` and `change_source` to that endpoint's body (optional, defaults
  `"Edited by user"` / `USER`).
* `PATCH /api/v1/resumes/{id}` gains `template` and `name`/`target_role` as today.
* `POST …/{id}/duplicate` `{name?}` → new resume (kind of the source, `source_resume_id`
  set, version 1 note "Duplicated from <name> v<n>", change_source SYSTEM).
* `POST …/{id}/archive` / `POST …/{id}/unarchive`; archived resumes are excluded from
  `GET /resumes` unless `?include_archived=true`, cannot be default, and matching /
  automation must not pick them (check `get_default_resume` and any
  `select(Resume)` in `matching/`, `applications/`, `automation/` — if one needs a filter,
  add `Resume.archived_at.is_(None)` **only** inside `resumes/service.py` helpers they call,
  or report it for integration if the query lives elsewhere).
* `GET …/{id}/versions/{n}` (one version), `GET …/{id}/versions/{n}/diff?against=<m>` and
  `GET …/{id}/diff?against=<resume_id>` → the diff shape in plan §4.2 (field-level, bullets
  compared line by line, skills as added/removed sets). `POST …/{id}/versions/{n}/restore`
  → new version with note "Restored from v<n>", change_source SYSTEM; keeps
  `resumes/apply.py` Undo semantics intact.
* `GET /api/v1/resumes/summary` → plan §4.6.
* `GET /api/v1/resumes/history?limit=&cursor=&resume_id=&change_source=` → versions across
  all of the user's resumes, newest first, with resume name/kind and a one-line change
  summary (computed with your diff: "+2 skills, 1 bullet changed").

### AI writing help (`ai/tasks.py` + `ai/prompts.py`, append-only; call through plan §4.3)
* `POST …/{id}/ai/rewrite-bullet` `{text, role?, company?}` → up to 3 candidates. Reuse
  `apply.strengthen_bullet` / `_llm_bullet` / `bullet_problem` / `strip_filler` — do not
  duplicate them; factor a shared function if needed (you own `apply.py`'s callers, keep its
  tests green). Each candidate carries `checks: {kept_details, no_new_numbers, no_new_claims}`.
* `POST …/{id}/ai/improve-text` `{text, field}` → grammar/clarity/tone only; reject output
  that adds numbers, skills, employers or dates not in the input (`invented_numbers` +
  a skills-diff against `ai/skills.py` aliases) and return `{text, changed: bool, reason?}`.
* `POST …/{id}/ai/draft-summary` → reuse `apply._summary_change`-style deterministic draft
  + optional model polish behind `summary_problem`.
* `POST …/{id}/ai/responsibility-to-achievement` `{text}` → rephrases into an
  achievement-oriented bullet **with a `[result]` placeholder** when no metric exists in the
  input; never fills a number itself. Explain this in the UI.
* All four run the mock provider deterministically in tests.

## Frontend

* `src/features/resume-studio/` (api.ts hooks under `qk.resumeStudio` and existing
  `qk.resumes`, `types.ts`, `schema.ts` zod for the editor, components). Keep existing
  `features/resume` components working and reuse them (insights, apply dialog, version
  history widget, target role select).
* **My Resumes** (`/resume/my`, `/resume/my/:id`): grid/list of resume cards with search,
  filters (kind, target role, archived), sort; card actions: open, edit, export (PDF/DOCX),
  duplicate, rename, set default, archive/restore, delete (ConfirmDialog). `/resume/my/:id`
  = today's detail (insights, parsed data, versions) with an "Edit in editor" button and a
  "Tailor for a job" link to `/resume/targets?resume=<id>` (ats owns that page). Kind
  badges (Uploaded / Built / Tailored from <name>), draft indicator ("Unsaved draft from
  <time> — Resume editing / Discard").
* **Create Resume** (`/resume/new`): a chooser — Start from profile · Upload PDF/DOCX ·
  Paste text · Import LinkedIn export (with the "how to download your data" steps) · Blank.
  Then name, target role (`TargetRoleSelect`), template picker (mini previews), and it
  lands in the editor.
* **Editor** (`/resume/my/:id/edit`): split screen — left: section list (add/remove/reorder
  with keyboard-accessible drag — `@dnd-kit/core` + `@dnd-kit/sortable` may be added, pin
  versions), forms per section (react-hook-form + zod), bullets as a list with per-bullet
  AI actions (Rewrite / Make achievement-oriented / Improve wording) showing candidates
  side by side with the checks and an "Apply" that only edits the local draft; right: live
  preview rendered from the template definition (print-like page, zoom, template switch).
  Autosave the draft (debounced ~1.5 s, non-blocking "Saved draft · 12:03" status, retry on
  failure). "Save version" with an optional note; "Export" menu; "Compare with v<n>".
  Mobile: tabs Edit / Preview. Unsaved-changes guard on navigation.
* **Version History** (`/resume/history`): timeline across resumes with filters (resume,
  USER/AI/SYSTEM), each row: resume, version, change summary, note, source badge (AI edits
  visibly distinct), actions Compare (side-by-side field diff, added/removed highlighted)
  and Restore (ConfirmDialog). Deep link `?resume=<id>&v=<n>`.
* Every list has loading/empty/error states; destructive actions confirm; toasts on
  success with Undo where a version was created (restore the previous version).

## Tests
Backend: templates/render round-trip (PDF+DOCX → extraction → parser), build/prefill/
import-text/import-linkedin (ZIP with the real LinkedIn CSV headers, zip-slip and size
guards), draft save/discard/clear-on-save, duplicate, archive excluded from default and
listing, diff shapes, restore makes a version, history endpoint, AI helpers' guards
(invented numbers/skills rejected, placeholder kept), ownership 404s, summary. Run with your
DB: your new tests + `tests/test_resumes.py tests/test_resume_apply.py
tests/test_resume_recommendations.py tests/test_ai.py tests/test_matching.py`.
Frontend: `npm run build`. Browser: create `builder.check@jobpilot.ai`, create from profile,
import text, edit with AI rewrite, autosave, export both formats (open the DOCX text, check
the PDF has text), duplicate, archive, restore a version; screenshots light+dark into
`notes/screenshots/builder/`.

## Constraints recap
Never fabricate facts (plan §6). Additive schema changes only (if a migration is truly
unavoidable: id `d1f3a5c7e9b2`, down_revision `a9c3e5b7d1f0`). Do not edit `Sidebar.tsx`,
`navigation.ts`, `recommendations.py` scoring (you may import), other streams' files.
Routers thin. Keep the app importable at every step. Update
`notes/resume-builder-progress.md` as you go. Report per plan §8.
