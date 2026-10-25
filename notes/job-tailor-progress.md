# job-tailor — progress

Brief: `notes/job-tailor-prompt.md`. Owner: job-tailor agent. Do not commit.
Ports: backend 8106 (Redis db 19), Vite 5236, stub AI 8103, test DB `jobpilot_test_tailor`.

## Checklist
- ✅ Read brief + plan §1/5/6/7, DESIGN, CONTRACTS §16-18, ats prompt, ai-model-choice progress, ats backend code
- ✅ 2. Backend `POST /ats/targets/tailor` (`QuickTailorRequest` → `TailorResult` + `target_id/tailored_resume_id/analysis_id/ai_pass`)
  - `targets.quick_tailor`, `_quick_snapshot`, `fingerprint(..., extra=)`, `create_target(..., fingerprint_extra, link_company)`
  - router `quick_tailor` (before `/targets` POST), `apply_choice` + `_ai_rate_limit(user, True)`
- ✅ 3. Backend tailoring pass `app/modules/ats/tailoring.py` (`tailor_pass`, `plan_bullets`, `summary_problem`,
  `bullet_problem`, `model_summary`, `model_bullet`); `service.polish_analysis` delegates for `tailor_resume`;
  `run_analysis` always schedules the pass for tailor runs when a model answers; `retry_polish(task=)` +
  `AiRunRequest.task` (inferred via `is_tailoring_analysis`); compare gains `changes[]` (`TailorChange`) + `ai_rejected`
- ✅ 5a. pytest `tests/test_ats_tailor.py` (24 pass); with ats_api, ats_scoring, ai_choice, db_conventions,
  migrations, resume_apply: 168 pass (one run hit a teardown deadlock in test_ai_choice from its polish thread —
  flaky race, passes alone and in the rerun)
- ✅ 1. Frontend `/resume/targets/new` → `features/ats/tailor/{TailorComposer,ResumePicker,TailorProgress,TailorResultView,TailorSteps,InlineEdit}.tsx`
  (lazy, exported from `modules/resume/pages.ts`); `JdInputPanel` props `tabs/showMetaFields/autoPreview/onParsed/initialText`;
  api `useQuickTailor`, `useTailorTarget`, `useRetryPolish(id, task)`; types `QuickTailorRequest`, `TailorChange`, TailorResult ids.
  Entry points: JobTargets header (gradient "Optimize a resume for a job" + outline "New target") and empty state;
  dashboard quick action "Optimize for a job"; MyResumes buttons + StudioResumeCard menu → `/resume/targets/new?resume=<id>`.
  JobTargetDetail: inline rename of role/company; TailorCard toast links to the progress/result view.
- ✅ 4. Quality: tsc clean, build green, main chunk 350.45 kB (composer in the lazy resume pages chunk), contrast 0 failures, 1440/390 light+dark
- ✅ 5b. Playwright proofs (a)-(f) all PASS (a on real Ollama qwen2.5:3b, b/c/e on stub :8103); 18 screenshots in `notes/screenshots/job-tailor/`
- ✅ 5c. Full backend suite once, alone → `notes/job-tailor-junit.xml`: exit 0, tests=1447, failures=0, errors=0, skipped=3 (571 s)
- ✅ Docs: CONTRACTS §18 notes (one-screen tailoring + AI tailoring pass)
- ✅ Cleanup: tailor.check@jobpilot.ai soft-deleted (4 targets, 8 resumes, credential), servers + stub stopped

## Decisions
- No migration: pass state lives on `ats_analyses.status/progress` + suggestion rows (`checks.tailor_pass`,
  `checks.tailor_state` pending|accepted|rejected|unchanged|not_run|applied) → UI "AI rewrite (n of m)".
- Same JD twice → 409 `target_exists` (details.id); the UI offers "Optimize for the saved target" which calls
  `POST /targets/{id}/tailor`. "Optimize another resume for this job" also uses `/targets/{id}/tailor`.
- "Derived" company/role = not typed or typed equal to the parse → JD sha joins the fingerprint.
- Renaming a target uses the plain key (a rename to an existing company+role is `target_exists`).
- Model error mid-pass → nothing applied (rules-only copy stands), rows `not_run`, error on the analysis.
- Bullet guard for tailoring is stricter than the shared one: a rewrite may only name tools its own entry names.
- Uploaded / URL JDs are sent as PASTED text (+ url) so the server does not refetch.

- JD rules parser reads a plainly named company (jd._company_from_text) so the Company field can prefill.
- Summary prompt asks for 35-55 words: a shorter AI summary made the final analysis propose a rule summary over it.
- Picker lists originals (default first) before tailored copies.

## Blockers
- none
