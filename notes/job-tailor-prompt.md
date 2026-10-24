# job-tailor — "Job-Specific Resumes": paste the job description, pick a resume, get it optimised

You are **job-tailor**, a senior full-stack engineer / product designer (FastAPI + SQLAlchemy 2;
React 18 + TS + Tailwind + Radix + react-query) on JobPilot AI
(`C:/Users/Neera/projects/job application`, branch `develop`, Windows). Read, binding:
`notes/resume-studio-plan.md` §1, §5, §6, §7 (environment + verification protocol), `docs/DESIGN.md`
(theme v2 "Indigo Pulse"; skeletons, not spinners), `docs/CONTRACTS.md`, `notes/ats-optimizer-prompt.md`
(the rules of the ATS engine: honesty guards, "estimated" wording, no fabricated facts),
`notes/ai-model-choice-progress.md` (how the per-run model picker works and how the Playwright
proofs ran two models with the stub provider on :8102), and the code below. Do not commit.
Progress file: `notes/job-tailor-progress.md` (update after each milestone; if you are stopped, a
relaunch continues from it).

You are the **only agent** in the tree right now; the tree has ~220 uncommitted files from
finished streams (AI model picker, LinkedIn connect, resume upload). Do not revert or reformat
any of it. Alembic head is `f7a9b1c3d5e8` (merge). You should need **no migration**: the AI pass
state lives on `ats_analyses.status/progress` like the existing polish. If you truly need one,
branch off `f7a9b1c3d5e8` with revision id `a1c3e5b7d9f0` and say why in the report.

Ports: backend `8106` (`REDIS_URL=redis://localhost:6379/19`, `AUTH_RATE_LIMIT_PER_MINUTE=1000`),
Vite `5236`, stub AI provider `8103` (copy the stub approach from the ai-model-choice stream),
test DB `jobpilot_test_tailor` (own `TEST_DATABASE_URL`). The owner's dev servers on :8000/:5173
and Redis db 0 are not yours. Use `run_in_background: true` for servers, `</dev/null` on
non-interactive commands, write scripts with the Write tool (heredocs mangle backslashes and
quotes here). **Memory:** Claude Code kills background shells when the machine is low on memory.
Run the full backend suite once, alone, at the very end (no Playwright or servers running at the
same time); if it is killed, report that and do not restart it.

## What the owner said
"Job-Specific Resumes: in that I will just provide the job description and then select the resume
and you will optimize it according to that. Do that."

## What exists today (read it, then build on it, do not fork it)
- Page `/resume/targets` (`pages/resume/JobTargets.tsx`): a board/table of **job targets**. The
  only way in is "New target" (`features/ats/components/TargetFormDialog.tsx`): company + role
  are **required** (`targets.create_target` raises `target_incomplete`), dates, notes, optional
  JD, optional "Resume to tailor". Tailoring happens later, on `/resume/targets/:id`
  (`JobTargetDetail.tsx` → `TailorCard` → `POST /ats/targets/{id}/tailor`, `targets.tailor`).
  That is three screens before anything is optimised. The owner wants one.
- `targets.tailor()` = `ats.run_analysis` (rules: `scoring.py`, `suggestions.build_drafts`) →
  `ats.auto_optimize(mode="new_resume", polish_task=TASK_TAILOR)` which applies only the
  **rule-safe** suggestions to a new `TAILORED` resume, then re-analyses; the background
  `polish_analysis` thread asks the model to rewrite up to `POLISH_MAX_BULLETS` bullets and only
  **proposes** them (status stays PROPOSED until the user applies them in the ATS optimizer).
  So today "tailor" mostly adds evidenced skills, reorders sections and leaves the real rewriting
  as suggestions. The owner expects the resume to come out optimised.
- Honesty guards you must keep: `resumes/apply.py` (`bullet_problem`, `strip_filler`,
  `make_facts`: no new numbers, tools, employers, titles or claims; `_WEAK_FIRST` verb rule),
  `ADD_SKILL` only for skills evidenced in the resume text or profile, "estimated" score wording,
  `llm.wrap_untrusted` around all JD/resume text (prompt injection), `ai/safety.py`.
- JD intake already exists and is good: `features/ats/components/JdInputPanel.tsx` (paste /
  upload PDF-DOCX / URL / saved target / discovered job; parse preview; optional AI refine) and
  `POST /ats/jd/{parse,upload,fetch}`; `SnapshotCreate` (`PASTED|URL|BOARD`).
- Per-run model choice: `AiRunButton task="…"` + `useAiChoice(task).runWithModel`, body `ai:
  WorkflowTarget`; task `tailor_resume` → workflow `generation` (`ai/routing.py`). Keep using it.
- Resume model: `kind` UPLOADED|CREATED|TAILORED, `source_resume_id`, versions
  (`update_parsed_data(..., change_source=AI)`), compare endpoints (`/ats/targets/{id}/compare`,
  `/resumes/{id}/compare?against=`), export `/resumes/{id}/export?format=pdf|docx`.

## Deliver

### 1. The one-screen flow (frontend)
New route **`/resume/targets/new`** (lazy, inside the resume module; the nav item
"Job-Specific Resumes" keeps pointing at `/resume/targets`), component
`features/ats/tailor/TailorComposer.tsx` (new folder `features/ats/tailor/**` is yours). Three
steps on one page, same stepper language as `AtsOptimizer.tsx`:
1. **Job description** — reuse `JdInputPanel` (add a prop to hide the "saved target" tab here;
   keep paste as the default tab, upload and URL available). When the parse returns a title /
   company, show them as two small editable inputs under the panel ("Role", "Company"), prefilled;
   neither is required to continue. If the JD has no company, the target is saved as
   "Unknown company" and the role falls back to the JD title or "Untitled role"; the user can
   rename on the result screen or in the target detail.
2. **Resume** — a compact picker of the user's non-archived resumes (cards or a radio list, not a
   bare select): name, kind badge (Uploaded / Built / Tailored), target role, version,
   last ATS estimate for this JD if one exists, default resume pre-selected; `?resume=<id>` in
   the URL pre-selects. Empty state: "Upload my resume" (opens the existing
   `UploadResumeSheet`) / "Build from my profile".
3. **Optimize** — one primary `AiRunButton task="tailor_resume"` labelled **"Optimize for this
   job"** (the model picker and the chevron keep working; with no model configured the button
   still works and the copy says the rewrite will be rules-only, with a link to Settings → AI
   models). A short honest note under it: "We create a tailored copy. Your original is never
   changed. Nothing is invented: every change keeps your facts."

**Progress** (no spinner): a stage list that follows the server — "Reading the job description",
"Scoring your resume", "Applying safe changes", "AI rewrite (n of m)", "Final score" — driven by
polling `GET /ats/analyses/{id}` (`status`, `progress`) exactly like the optimizer does.

**Result screen** (same route, replaces the composer; also reachable later as
`/resume/targets/:id` which already shows the tailored card): before → after estimated score
(`ScoreRing` ×2 with an arrow and the delta), the tailored resume name (editable inline, PATCH
`/resumes/{id}`), **what changed** grouped: skills added, summary rewritten, bullets rewritten,
sections reordered — each with before/after (`WordDiff` exists) and the one-line rationale;
**needs your confirmation** list for the suggestions the guards would not apply automatically,
with Apply / Skip per item (reuse `SuggestionList` or the apply endpoints); actions: **Open in
editor**, **Download PDF / DOCX**, **Compare with original** (`CompareView`), **View target**,
**Optimize another resume for this job** (back to step 2 with the JD kept). A toast on completion.

**Entry points** (edit minimally): `/resume/targets` header gets the primary gradient button
**"Optimize a resume for a job"** → `/resume/targets/new`; "New target" becomes the outline
secondary; the empty state of the board says the same. Dashboard quick action "Tailor for a
company" → "Optimize for a job · paste a JD, pick a resume" → `/resume/targets/new`.
`ResumeCard` menu and the uploaded-resume page button "Tailor for a company" → "Optimize for a
job" → `/resume/targets/new?resume=<id>`. The ATS optimizer's existing "Save as job target"
stays.

### 2. Backend: one call that does it
`POST /ats/targets/tailor` (router `ats/router.py`, service in `ats/targets.py`), body
`QuickTailorRequest { jd: SnapshotCreate, source_resume_id: UUID | None (None = default resume),
company_name?, role_title?, name?, ai?: WorkflowTarget }`, returns `TailorResult` (add
`target_id`, `tailored_resume_id`, `analysis_id` if not already present). It must, in one
transaction up to the background pass: resolve the snapshot (`ats.resolve_snapshot` /
`create_snapshot`), create the target with company/role from the request → structured JD →
fallbacks above (relax `target_incomplete` only for this path; keep the fingerprint uniqueness but
include the snapshot `text_sha256` in the key when company or role were derived, so two pasted JDs
never collide), then call the existing `tailor()`. `_ai_rate_limit` applies. Ownership checks as
everywhere; 404 for another user's resume.

### 3. Real tailoring, still honest (backend)
Extend the tailoring run (task `tailor_resume`, workflow `generation`) so the AI pass **applies**
its accepted rewrites to the tailored copy instead of only proposing them:
- In `polish_analysis` when `task == TASK_TAILOR` (or a sibling `tailor_pass` function): rewrite
  the **summary** toward the role (new `_model_summary`, same guard style: keep every fact, no new
  claims, at most 60 words, may mention only skills present in `facts`), rewrite the relevant
  **bullets** (raise the cap for tailoring to about 12, prioritise the entries whose technologies
  overlap the JD), and **order skills** so JD-matched ones come first (deterministic, no model).
  Every candidate goes through `bullet_problem` / an equivalent `summary_problem`; rejected ones
  are dropped (recorded in `checks.ai_rejected`), never applied.
- Accepted rewrites are applied in one go as a **new version of the tailored resume**
  (`update_parsed_data(..., change_source=AI, note="AI tailoring for <company · role>: n
  changes")`), the suggestions are marked APPLIED with `checks.applied_to_resume_id`, and a fresh
  analysis (no further polish) produces the final score. The source resume is never touched.
- The user can undo (existing version history / `undo`) and everything shows in Compare.
- No model configured → rules-only result, clearly labelled on the result screen. Model errors →
  the rules-only copy stands, the error is on the analysis (`_finish(error=…)`) and the result
  screen says "The AI rewrite did not run: <reason>. Retry" (reuse `/polish` retry with the task).
- Usage/cost events go through the existing runtime (`source="per_run"` when `ai` was given).

### 4. Quality bar
Theme v2 tokens only, light + dark, 1440 + 390 (the stepper stacks, the result's before/after
rings sit side by side on phones), skeletons, keyboard reachable, reduced motion respected,
`notes/theme-contrast.py` 0 failures, `npx tsc --noEmit` clean, `npm run build` green (main chunk
at most 352 kB; the composer in the resume/ATS chunk or its own lazy chunk).

### 5. Tests
- pytest (own test DB): quick-tailor with pasted JD + explicit resume; with no resume → default
  resume; no resume at all → `resume_required`; no company/role → derived, two different JDs
  without company/role both save; same JD twice → the existing-target error or a second target
  (choose, document); other user's resume → 404; tailoring pass with a stubbed model applies
  guard-passing rewrites as a new version, rejects a rewrite that adds a number, leaves the
  source resume's version unchanged; no model → rules-only, DONE; model error → copy exists,
  analysis error set. Keep `test_migrations.py` and `test_db_conventions.py` green.
- Playwright on your private servers, user `tailor.check@jobpilot.ai` (soft-delete at the end):
  (a) paste a 600-word JD → role/company prefilled → pick the second resume → Optimize →
  progress stages → result with before < after, change groups, Open in editor works; (b) stub
  model on :8103 shows the AI-rewritten bullets applied (version 2 of the tailored copy) and the
  compare view; (c) two models configured → the picker dialog appears on Optimize, Esc cancels
  with nothing created; (d) `?resume=<id>` preselects; (e) no company in the JD → "Unknown
  company" target renamed inline; (f) 390 px light and dark. Screenshots in
  `notes/screenshots/job-tailor/`, named `NN-what-theme-width.png`.
- Full backend suite once at the end, alone: `pytest --junitxml=notes/job-tailor-junit.xml`;
  report the exit code and counts from the XML.

## Report (final message)
1. The flow in five lines, with the route and the three entry points.
2. The new endpoint and the tailoring pass: what the model may change, what the guards reject,
   what happens without a model.
3. Files added/changed (new folder vs. minimal edits to existing pages).
4. Test counts (module + full suite with exit code), Playwright proof list with screenshot paths.
5. Anything unfinished or any limitation (e.g. caps, latency with a real model).
