# Step 4 — Resume improvement recommendations

You are a senior full-stack developer on JobPilot AI (FastAPI + SQLAlchemy 2 + PostgreSQL
backend, React/Vite/Tailwind frontend, repo `C:\Users\Neera\projects\job application`).
Read `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md` (resumes, matching and AI sections),
`backend/app/modules/matching/scoring.py`, `backend/app/modules/ai/tasks.py`,
`backend/app/modules/ai/skills.py` and `backend/app/modules/resumes/service.py` before
writing code. Do not commit.

## Why

Users upload a resume and pick target jobs. Today they get a match score per job and a
list of missing skills, but no advice on the resume itself. Step 4 turns the data the
system already has into concrete, prioritised recommendations, and shows the user how much
their match scores would improve if they acted on them.

## Design rules

- **Deterministic first, LLM second.** Every recommendation must be derivable from data
  (parsed resume, skill taxonomy, target jobs, preferences) without an LLM, so the feature
  works with the `mock` provider and with a small local model. The LLM only rewrites the
  wording of suggestions and drafts example bullet text; it never invents facts about the
  candidate. If the LLM is unavailable, the deterministic output is shown as is.
- **No new tables, no migration.** Recommendations are computed on demand from the
  resume's current `parsed_data` and the user's jobs. Cache the result in process memory
  keyed by `(resume_id, resume.updated_at, jobs fingerprint)` with a 10-minute TTL. The
  "before and after" comparison uses `ResumeVersion` rows that already exist.
- The LLM provider abstraction is being extended by another developer right now (Ollama).
  Use `tasks._run_validated` exactly like the existing tasks do and do not touch
  `providers/ollama.py`, `factory.py`, `provider.py` or `app/core/config.py`. You **may**
  edit `providers/mock.py` to add the mock response for your new task, `tasks.py`,
  `prompts.py` and `ai/schemas.py`.

## Scope

### 1. Analysis engine — `backend/app/modules/resumes/recommendations.py`

Input: a `Resume` (parsed_data), the user's `JobPreference`, and the target job set:
the user's top-N jobs by match score (default 25, from `JobMatch`) plus any job the user
queued or applied to. Output: a `ResumeRecommendations` Pydantic model
(`resumes/schemas.py`) with:

- `overall_score: int` 0–100, the resume's health score (see below)
- `target_summary`: number of jobs analysed, the most common titles and top required
  skills across them
- `recommendations: list[Recommendation]`, each with `id` (stable slug), `category`,
  `priority` (HIGH / MEDIUM / LOW), `title`, `detail`, `evidence` (which jobs or fields
  triggered it), `suggested_text` (optional, LLM-polished), `estimated_score_gain`
  (points on the average match score across target jobs if fully addressed)
- `score_projection`: average match score now, and the projected average if all HIGH
  recommendations were addressed, computed by re-running `matching.scoring` with the
  candidate's skills augmented by the recommended skills (import `scoring`, do not edit it)
- `version_history`: for each `ResumeVersion`, the overall score and average match score
  it would have had, so the UI can draw "before and after" across versions

Recommendation categories and the deterministic rules behind them:

| Category | Rule |
|---|---|
| `MISSING_SKILL` | A skill required by ≥ 30 % of target jobs (via `ai/skills.py` normalisation and aliases) that does not appear in the resume's skills or experience text. One recommendation per skill, priority by frequency. Only suggest adding it when the candidate's experience text mentions a related family skill, otherwise label it "learn" not "add". |
| `KEYWORD_GAP` | Terms frequent in target job titles and descriptions (ATS keywords) missing from the resume text, after stop-word and taxonomy filtering. |
| `WEAK_SUMMARY` | Summary missing, under 30 words, or lacking the target title, years of experience, or top three skills. |
| `EXPERIENCE_BULLETS` | Experience entries with no bullets, bullets without a number or outcome (regex for digits, %, currency, "reduced", "increased", etc.), or more than 8 bullets. |
| `TITLE_ALIGNMENT` | The most recent title does not match any desired title or the common title in the target jobs, even loosely (reuse `scoring.score_title`). |
| `SECTION_MISSING` | No education, no skills section, no links (GitHub/LinkedIn) when target jobs are software roles, no projects for candidates with under 2 years of experience. |
| `LENGTH_AND_FORMAT` | Text content over ~900 words for under 5 years of experience, or under 200 words; contact details missing (email, phone); dates missing on experience entries. |
| `STALE_CONTENT` | Skills or entries older than 8 years that are not required by any target job. LOW priority. |

Overall score: start at 100, subtract weighted penalties per rule (HIGH 12, MEDIUM 6,
LOW 2, capped per category), clamp 0–100. Document the weights at the top of the module.

### 2. AI polish — one new task

`tasks.polish_resume_recommendations(resume_payload, recommendations) -> PolishedRecommendations`
in `ai/tasks.py`, with a prompt in `ai/prompts.py` and schemas in `ai/schemas.py`. It
receives the deterministic recommendations and returns, for each `id`, an improved
`detail` and an optional `suggested_text` (for example a rewritten summary or one example
bullet). The prompt must say explicitly: use only facts present in the resume payload, do
not add employers, dates, degrees or metrics that are not there, keep each suggestion under
60 words. Validate that the response only references recommendation ids you sent and drop
anything else. Add the mock provider's canned response. Wrap the call so any provider error
falls back to the deterministic text and sets `ai_polished: false` on the result.

### 3. API

- `GET /resumes/{resume_id}/recommendations?refresh=false` → `ResumeRecommendations`.
  `refresh=true` bypasses the cache.
- `GET /resumes/{resume_id}/recommendations/history` → the `version_history` only, for
  the chart.
- Router thin, logic in `recommendations.py` and `resumes/service.py`. Update `docs/API.md`
  and `docs/CONTRACTS.md`.

### 4. Frontend — Resume page (`frontend/src/pages/Resume.tsx`, `features/resume/`)

- A "Resume health" card: overall score gauge, average match score now vs projected, and a
  one-line target summary ("Analysed 25 jobs: mostly Backend Engineer roles asking for
  Python, PostgreSQL, Docker").
- A recommendations list grouped by priority with category chips, evidence on expand,
  suggested text with a copy button, and a "Mark as done" local toggle (client-side only,
  persisted in localStorage per resume id).
- A "Before and after" line chart across resume versions (use the chart library already
  in the bundle) with overall score and average match score series.
- A "Refresh analysis" button that calls with `refresh=true`.
- Loading, empty (no target jobs yet: tell the user to run discovery or set preferences)
  and error states. Keep `frontend/src/types/api.ts` in sync.

### 5. Tests

- Unit tests for every rule in the table with small hand-built `parsed_data` and job
  fixtures; the score math; cache key behaviour; the projection using `scoring`.
- Task test with the mock provider, including the "unknown id is dropped" rule and the
  fallback when the provider raises.
- API tests for both endpoints including a resume that belongs to another user (404).
- Run your new tests plus `tests/test_resumes.py`, `tests/test_matching.py` and
  `tests/test_ai.py` with
  `TEST_DATABASE_URL=postgresql+psycopg://jobpilot:jobpilot@localhost:5432/jobpilot_test_step4`.
  Do not run the full suite; other agents are running theirs.
- `npm run build` in `frontend/` must pass.

## Hard constraints

- Never fabricate candidate facts, in code or prompts.
- No database schema changes and no migration.
- Do not edit `matching/scoring.py`, `ai/skills.py`, `ai/provider.py`, `ai/factory.py`,
  `providers/openai.py`, `providers/anthropic.py`, `app/core/config.py`, anything under
  `adapters`, `companies`, `jobs`, `backend/app/models`, `backend/alembic`, or
  `frontend/src/features/companies`. Other developers are working there.
- Routers stay thin. Do not commit, stash, reset or checkout.

## Report

1. Files added or changed, one line each.
2. Test summary line and failures in full; frontend build result.
3. A real example: the seeded demo user's recommendations JSON (trimmed to the first five)
   and the score projection numbers.
4. Decisions not covered here, and anything unfinished with the reason.
