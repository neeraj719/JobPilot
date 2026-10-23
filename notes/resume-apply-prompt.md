# Resume — "Apply suggestions" button (review, apply, save as a new version)

You are "resume-apply", a senior full-stack developer on JobPilot AI (FastAPI + SQLAlchemy 2 +
PostgreSQL backend, React/Vite/Tailwind frontend, repo `C:\Users\Neera\projects\job application`).
Read `backend/app/modules/resumes/{recommendations,service,schemas,router}.py`,
`backend/app/modules/ai/{tasks,prompts}.py` (the `polish_resume_recommendations` task and its
"no numbers that are not in the resume" check), `frontend/src/pages/Resume.tsx` and
`frontend/src/features/resume/**` before writing code. Do not commit.

## What the owner asked for

On the Resume page, after a resume is uploaded, the app shows recommendations. The owner wants a
button that applies the changes and saves the resume.

## The rule that shapes the design

The product never puts a fact on a resume that the candidate has not confirmed. So "apply all"
means: apply every change that is **provably safe** automatically, and let the user confirm or
complete the rest in the same dialog, then save once. Concretely:

| Recommendation | Change kind | Default |
|---|---|---|
| `MISSING_SKILL`, `action="list"` (skill already evidenced in the resume or profile) | `ADD_SKILL` to `parsed_data.skills` | **selected**, safe |
| `MISSING_SKILL`, `action="add"` ("add if you have used it") | `ADD_SKILL` | **not selected**; checkbox labelled "I have used {skill}" |
| `MISSING_SKILL`, `action="learn"` | none | listed under "Needs your work", not applicable |
| `WEAK_SUMMARY` with `suggested_text` that has no `[placeholder]` and passes the fact check | `REPLACE_SUMMARY` | **selected**; text shown and editable |
| `EXPERIENCE_BULLETS` with `suggested_text` | `REPLACE_BULLET` (the weak bullet in `evidence`, inside that experience entry's `description`) | **not selected**; editable field; can only be selected once every `[...]` placeholder is replaced |
| `KEYWORD_GAP`, `TITLE_ALIGNMENT`, `SECTION_MISSING`, `LENGTH_AND_FORMAT`, `STALE_CONTENT` | none | listed under "Needs your work" with their detail |

If a `WEAK_SUMMARY` has no usable `suggested_text`, build a factual one deterministically from
the resume: target title (from preferences or the most recent title), years of experience if
known, and the top three skills that are already in the resume. Never add numbers, employers,
degrees or skills that are not in `parsed_data` or the profile.

## Scope

### 1. Backend — `backend/app/modules/resumes/apply.py` (new) + service/router/schemas

- `build_apply_plan(db, user_id, resume_id) -> ApplyPlan`: uses
  `service.get_recommendations` (cached result is fine) and returns
  `ApplyPlan { resume_id, resume_version, changes: list[ApplicableChange], manual: list[ManualItem] }`.
  - `ApplicableChange { id (the recommendation id; bullets may need a suffix per bullet),
    recommendation_id, kind: ADD_SKILL|REPLACE_SUMMARY|REPLACE_BULLET, title, before: str|None,
    after: str, target: {field path, e.g. "skills", "summary", "experience[1].description"},
    selected_by_default: bool, requires_confirmation: bool, confirmation_label: str|None,
    has_placeholders: bool, estimated_score_gain: float }`
  - `ManualItem { recommendation_id, title, detail, category, priority }`
- `apply_changes(db, user_id, resume_id, request: ApplyRequest) -> ApplyResult`:
  - `ApplyRequest { resume_version: int, changes: list[{ id, after?: str }] }`. Only the ids the
    client sends are applied. `after` overrides the text for REPLACE_SUMMARY and REPLACE_BULLET.
  - Rebuild the plan server-side and validate every requested id against it (unknown id → 422
    `unknown_change`). Never trust client-sent `kind`, `target` or skill names.
  - Reject any `after` that still contains a `[...]` placeholder (422 `placeholder_left`).
  - For REPLACE_SUMMARY, reject text containing numbers that do not appear in the resume text or
    parsed data (reuse or factor out the existing check from `ai/tasks.py`; do not duplicate the
    regex). User-typed bullet text is the user's own claim and is allowed numbers.
  - If `resume_version` is not the resume's `current_version`, 409 `stale_plan` so a second tab
    cannot overwrite newer edits.
  - Apply to a deep copy of `parsed_data`: append skills (de-duplicated case-insensitively,
    canonical spelling from the skill taxonomy), replace the summary, replace the exact bullet
    text inside the experience description (if the bullet text is no longer found, skip it and
    report it in `skipped`).
  - Save through the existing `service.update_parsed_data` path so a new `ResumeVersion` is
    created, with the version note "Applied N suggestions". Invalidate the recommendations cache
    for this resume.
  - Return `ApplyResult { resume: ResumeRead, applied: list[{id, kind, title}],
    skipped: list[{id, reason}], recommendations: ResumeRecommendations }` (fresh, `refresh=True`).
  - Audit `resume.suggestions_applied` with the ids.
- Endpoints (router stays thin):
  - `GET /resumes/{resume_id}/recommendations/apply-plan` → `ApplyPlan`
  - `POST /resumes/{resume_id}/recommendations/apply` → `ApplyResult`
- The uploaded original file (PDF/DOCX) is **not** modified; this edits the structured resume
  data that matching, autofill and the recommendations use. Say so in the API docs.

### 2. Frontend — Resume page

- In the "Resume health" card (`ResumeHealthCard.tsx`) and at the top of the recommendations
  list, a primary button **"Apply suggestions"** with a count badge of applicable changes. Hidden
  when the plan has no applicable changes.
- Clicking opens a dialog (`features/resume/components/ApplySuggestionsDialog.tsx`, use the
  existing `Dialog` UI component and project styling, light and dark):
  - Section "Ready to apply": safe changes, pre-ticked. Each row: checkbox, title, a compact
    before → after diff (strikethrough for removed text, highlight for added), estimated score
    gain chip. Summary and bullet rows have an inline editable textarea.
  - Section "Confirm first": `requires_confirmation` rows, unticked, with the confirmation label.
  - Bullet rows with placeholders: the placeholder is highlighted, the checkbox stays disabled
    with the hint "Replace the bracketed part with your real result" until no `[...]` remains.
  - Section "Needs your work" (collapsed by default): the manual items, read-only.
  - Footer: "Select all ready" / "Clear", the selected count, projected score gain of the
    selection, and the primary **"Apply N changes and save"** button. Disabled when nothing is
    selected; shows a spinner while saving.
- On success: toast "Applied N suggestions — saved as version V", close the dialog, update the
  resume and recommendations queries from the response (no extra round trip), so the health
  score, the projection and the before/after chart update immediately. On 409 `stale_plan`,
  refetch the plan and tell the user the resume changed. On 422, show the server message inline
  on the offending row.
- Hooks in `features/resume/api.ts`: `useApplyPlan(resumeId)`, `useApplySuggestions(resumeId)`.
  Query keys in `lib/queryClient.ts`. Types appended to `frontend/src/types/api.ts` in one
  delimited block (re-read the file right before editing).

### 3. Tests

- Backend unit tests: plan building per recommendation kind and default selection; skills
  de-duplicated and canonicalised; summary fact check rejects invented numbers; placeholder
  rejection; unknown id; stale version 409; bullet replaced exactly once and skipped when not
  found; a new `ResumeVersion` is created with the note; cache invalidated; another user's resume
  404; client cannot smuggle a skill not in the plan.
- API tests for both endpoints.
- Run with `TEST_DATABASE_URL=postgresql+psycopg://jobpilot:jobpilot@localhost:5432/jobpilot_test_resume_apply LLM_PROVIDER=mock`:
  your new tests plus `tests/test_resume_recommendations.py`, `tests/test_resumes.py`,
  `tests/test_ai.py`. Not the full suite.
- `npm run build` in `frontend/` must pass.
- Browser check: start a venv uvicorn on port 8090 and a Vite dev server on port 5198 pointed at
  it (`VITE_DEV_BACKEND_URL=http://localhost:8090 npx vite --port 5198`), register a throwaway
  user `resume.apply.check@jobpilot.ai`, upload `backend/tests` sample resume content or a small
  generated DOCX, run discovery so there are target jobs, open the Resume page with Playwright,
  open the dialog, apply, and screenshot before and after (light and dark). Soft-delete the
  throwaway user afterwards. Stop both servers.

## Hard constraints

- Never add a skill, number, employer, date or degree the candidate has not confirmed.
- No schema changes and no migration; `ResumeVersion` already exists.
- Do not edit `matching/scoring.py`, `ai/skills.py`, `ai/provider*`, `ai/factory.py`,
  `app/core/config.py`, auth, adapters, companies, jobs, the sidebar or top bar components.
- Routers stay thin. Do not commit, stash, reset or checkout.

## Report

1. Files added or changed. 2. Test summary line and failures in full; build result.
3. Screenshot paths from the browser check and what they show. 4. The apply-plan JSON for the
throwaway user (trimmed). 5. Decisions not covered here; anything unfinished with the reason.
