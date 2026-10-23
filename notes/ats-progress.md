# ats stream — progress

Owner: ats agent. Plan: `notes/resume-studio-plan.md`, scope: `notes/ats-optimizer-prompt.md`.
Test DB `jobpilot_test_ats`, ports API 8092 / web 5202, migration `b4d6f8a0c2e4`.

## Checklist

- ✅ Read plan, spec, prompt; inspected resumes (recommendations/apply/service/schemas), companies, adapters/boards, executor, ai, frontend resume feature
- ✅ Models `app/models/ats.py` + enums (appended) + migration `b4d6f8a0c2e4` (fresh-DB diff vs models: 0 for my 4 tables; downgrade clean)
- ✅ Backend `app/modules/ats/` (llm shims, jd, fetch, lookup, scoring, suggestions, service, targets, router) mounted at `/api/v1/ats` (main.py: 2 lines)
- ✅ Tests `tests/test_ats_scoring.py` (24), `tests/test_ats_fetch.py` (38), `tests/test_ats_api.py` (24) + helpers `tests/helpers/ats.py`; with resume/company suites: 215 passed
- 🔄 Frontend `src/features/ats/**`, pages AtsOptimizer / JobTargets / JobTargetDetail
- ⏳ Live DB migration + browser check + screenshots

## Decisions

- Uniqueness of job targets: a `fingerprint` column (sha256 of normalized company | normalized role |
  normalized URL) with a partial unique index `(user_id, fingerprint) WHERE deleted_at IS NULL`.
  Simpler and SQLite-safe compared with an expression index; a duplicate POST answers 409
  `target_exists` with the existing id.
- Snapshots carry `user_id` and a nullable `job_target_id`: an analysis of pasted text without a
  saved target still keeps its JD snapshot (ownership via `user_id`).
- Circular FKs (target -> latest snapshot / last analysis) use `use_alter=True` with explicit names.

- ai-providers shipped `ai.runtime` / `ai.safety` / `ai.context` during this work: `ats/llm.py` resolves them
  dynamically (task names forwarded) and falls back to local shims when absent.
- `score_title` is generous across role families; ATS title alignment is capped at 35 and a role does not count as
  "relevant experience" when `recommendations.different_role` proves the titles name different kinds of role.
- Background polish only rewrites bullets (the deterministic summary is already fact-only); every model rewrite must
  pass `resumes.apply.bullet_problem`; a failure leaves status DONE with `error` set (deterministic result kept).

## Blockers

- none yet
