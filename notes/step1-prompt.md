# Step 1 — Make the automation engine run on real sources

You are implementing Step 1 of the JobPilot AI roadmap. Work only inside this repository
(`C:\Users\Neera\projects\job application`). Read `docs/ARCHITECTURE.md` and `docs/CONTRACTS.md`
before changing anything. Another agent owns the database layer and may be committing in
parallel; keep your database change to one small additive migration and do not reorganise
tables, schemas or models beyond what is listed here.

## Why this step exists

The daily pipeline (`backend/app/modules/automation/pipeline.py`) can search, dedupe, score,
filter, queue, generate answers, autofill with Playwright, pause for approval and auto-submit.
But in the "generate answers" step it only lets the browser run for `DEMO_ATS`. Every other
browser-backed source (Greenhouse, Lever, and the real adapters we add next) is left QUEUED
"for manual start". That one rule blocks real auto-apply. Step 1 removes it and replaces it
with a per-source setting the user controls.

## Scope

### 1. Per-source apply mode on the automation config

Add a `source_modes` JSON column to `AutomationConfig`
(`backend/app/models/automation.py`, table `master.automation_configs`):

```
source_modes: dict[str, str]   # {"GREENHOUSE": "AUTO_APPLY", "LINKEDIN": "DISCOVER_ONLY"}
```

Add an enum `SourceApplyMode` in `backend/app/models/enums.py` with two values:

- `AUTO_APPLY`     — the pipeline may prepare answers, open the browser, fill the form, and
                      (only if `auto_submit_enabled` and the source is in `auto_submit_sources`)
                      submit.
- `DISCOVER_ONLY`  — the pipeline discovers and scores jobs from this source but never queues
                      an application for it. The job appears on the Jobs page with a manual
                      "apply" link.

Resolution rule, implemented once in `backend/app/modules/automation/service.py` as
`resolve_source_mode(config, source) -> SourceApplyMode` and used everywhere:

1. If `source_modes` has an entry for the source, use it.
2. Otherwise default to `AUTO_APPLY` when the adapter's `supports_auto_apply` is true,
   else `DISCOVER_ONLY`.
3. A source whose adapter has `supports_auto_apply == False` can never resolve to
   `AUTO_APPLY`, even if the stored value says so. Log at debug and return `DISCOVER_ONLY`.

Migration: one new Alembic revision under `backend/alembic/versions/` that adds the nullable
JSON column with server default `'{}'`. Follow the existing migration style. It must upgrade
and downgrade cleanly on PostgreSQL and be a no-op-safe on SQLite.

### 2. Pipeline changes (`pipeline.py`)

- **Queue step**: skip candidates whose source resolves to `DISCOVER_ONLY`. Count them in a
  new stat `discover_only` and list them in the step's `data` under `discover_only` with
  job id, title, company, source. They are still real jobs with real match scores; they just
  do not become applications.
- **Answers step**: delete the special case `uses_browser and source != JobSourceType.DEMO_ATS → deferred`.
  The new rule is: if the adapter `uses_browser` and the browser is not available, defer;
  otherwise prepare. Nothing else about the source matters here.
- **Autofill, approval and submit steps**: no change in logic, but make sure their counters
  still add up with the new flow. The submit step must keep refusing anything that still has
  a required `NEEDS_USER_INPUT` answer.
- Keep `_auto_submit_allowed` as the only gate for unattended submission.
- Record `source_modes` (resolved, per enabled source) in `run.config_snapshot` so a run log
  shows exactly which mode each source ran in.

### 3. API and schemas (`backend/app/modules/automation/schemas.py`, `router.py`, `service.py`)

- `AutomationConfigRead` returns `source_modes` as resolved values for every registered
  source, not just the stored ones, so the UI can render a complete table.
- `AutomationConfigUpdate` accepts `source_modes: dict[str, str] | None`. Validate keys
  against `JobSourceType` and values against `SourceApplyMode`. Reject `AUTO_APPLY` for a
  source whose adapter does not support it with a 422 and a clear message.
- `GET /jobs/sources` (already exists) should additionally expose `supports_auto_apply`
  and `uses_browser` if it does not already, so the UI can grey out the option.

### 4. Frontend

- `frontend/src/features/settings/components/AutomationSettingsForm.tsx` and
  `frontend/src/features/settings/schema.ts`: add a "Per-source apply mode" section. One row
  per source: display name, a two-option segmented control (Auto apply / Discover only),
  disabled with a tooltip when the adapter does not support auto apply.
- `frontend/src/features/automation/components/AutomationStatusHeader.tsx`: show a count of
  sources in auto-apply mode next to the existing auto-submit summary.
- Run log (`Automation.tsx` run detail): show the new `discover_only` count on the queue
  step.
- Keep the existing TypeScript types in `frontend/src/types` in sync.

### 5. Tests

- `backend/tests/test_automation.py`: add tests for
  - `resolve_source_mode` defaults and the "cannot force AUTO_APPLY on an unsupported
    adapter" rule;
  - a run where one source is `DISCOVER_ONLY`: jobs are ingested and scored, no application
    is created for them, `discover_only` stat is correct;
  - a browser-backed non-demo source is **prepared** (not deferred) when the browser is
    available (monkeypatch `_browser_available` to `True` and stub the adapter), and
    deferred when it is not;
  - the config update endpoint rejects `AUTO_APPLY` for a mock-only source.
- Update any existing test that relied on the old "defer everything except demo ATS" rule.
- Add one end-to-end test in `backend/tests/test_runner_demo_ats.py` or a new file that runs
  the full pipeline against the demo ATS with a real Chromium: manual trigger, `AUTO_APPLY`,
  `auto_submit_enabled=True` with `DEMO_ATS` in `auto_submit_sources`, and asserts the
  application ends `APPLIED` with an external application id. Mark it with the existing
  browser marker so it skips where Chromium is absent.

## Hard constraints

- Do not add or change anything that bypasses CAPTCHA, OTP, 2FA, login walls or bot
  detection. Blockers must still pause the application with `REQUIRES_USER`.
- Auto-submit stays off by default and per-source opt-in. Do not widen it.
- Do not touch the mock adapters' data, the Gmail integration, or the DB schema layout
  beyond the one column above.
- Follow the DB conventions already in the repo: uuid primary keys, `is_active` and
  `deleted_at` on tables, named schemas via the constants in `app/models/base.py`.
- Routers stay thin; logic lives in `service.py` and `pipeline.py`.
- Do not commit. Leave the working tree with your changes for review.

## Verification you must run and report

From `backend/` with the venv at `backend/.venv/Scripts/python.exe` (Postgres on
localhost:5432 and Redis on 6379 are running; Chromium is installed):

```
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic downgrade -1 && .venv/Scripts/python.exe -m alembic upgrade head
```

From `frontend/`:

```
npm run build
npm run lint   # if the script exists
```

Then start the API (`uvicorn app.main:app`) and, with the seeded demo user, do one manual
`POST /api/v1/automation/run` with `DEMO_ATS` set to `AUTO_APPLY` and confirm in the response
that the run reaches the submit step and the application is `APPLIED`.

## Report back in this format

1. Files changed, one line each with what changed.
2. Migration revision id.
3. Test results: paste the final pytest summary line and any failures in full.
4. The run log JSON from the manual demo ATS run (steps array only).
5. Anything you had to decide that was not in this prompt, and why.
6. Anything you did not finish, and why.
