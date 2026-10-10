# Step 2 — Real job discovery from public ATS job boards

You are implementing Step 2 of the JobPilot AI roadmap. Work only inside this repository
(`C:\Users\Neera\projects\job application`). Read `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`
and `docs/DATABASE.md` first. Step 1 (per-source apply modes, `AutomationConfig.source_modes`,
`resolve_source_mode`) is already in the tree; build on it, do not redo it. Another agent owns
the database layer and may commit in parallel: keep your schema change to one small additive
migration and follow the repo's `StandardColumnsMixin` and named-schema conventions.

## Why this step exists

Today every job the engine finds is fake. The eight platform adapters (Naukri, LinkedIn,
Indeed, …) return a built-in mock catalogue and the Greenhouse and Lever adapters return an
empty list. Step 2 gives the engine real postings from real companies using the **free,
public, documented job board JSON APIs** of four ATS vendors. No login, no scraping behind
authentication, no CAPTCHA. The forms these jobs lead to are ordinary hosted HTML forms that
the existing `GenericAtsFormAdapter` browser flow already fills.

## Scope

### 1. Company board configuration

Add to `Company` (`backend/app/models/company.py`, table `master.companies`):

```
ats_board_token: str | None   # e.g. "stripe" for Greenhouse, "netflix" for Lever,
                              # "ramp" for Ashby, "Bosch" for SmartRecruiters
ats_board_url:   str | None   # the public board URL the token was derived from, for display
```

`ats_type` already exists; normalise its values to the `JobSourceType` names
(`GREENHOUSE`, `LEVER`, `ASHBY`, `SMARTRECRUITERS`, `WORKDAY`, `CUSTOM`, `DEMO_ATS`).
Add `ASHBY` and `SMARTRECRUITERS` to `JobSourceType` in `app/models/enums.py`.

Migration: one new Alembic revision adding the two nullable columns. Upgrade, downgrade,
upgrade must be clean on PostgreSQL.

### 2. Four real discovery adapters

Create `backend/app/modules/adapters/boards/` with one module per vendor, all subclassing
`GenericAtsFormAdapter` so the apply side is inherited:

| Adapter | Public endpoint |
|---|---|
| Greenhouse | `https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` |
| Lever | `https://api.lever.co/v0/postings/{token}?mode=json` |
| Ashby | `https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true` |
| SmartRecruiters | `https://api.smartrecruiters.com/v1/companies/{token}/postings` (paginated) and `/postings/{id}` for the description |

Replace the existing `greenhouse.py` and `lever.py` stubs with the real implementations
(keep the class names so `registry.py` imports still work).

Each adapter:

- Implements `search_jobs(query)` by fetching the board for **every company the user has
  configured with that `ats_type`**. The adapter is stateless and shared, so the list of
  companies to fetch is passed in through a new optional `SearchQuery.board_tokens:
  list[tuple[company_id, token]]` field filled by `jobs.service.build_search_query`. If the
  list is empty the adapter returns `[]` and logs at info.
- Maps the vendor payload into `DiscoveredJob`: title, location, description (strip HTML to
  text, keep the raw HTML in `raw`), `apply_url`, `posted_at`, `employment_type`,
  `work_mode` (remote detection from location text and vendor flags), `required_skills`
  extracted with the existing `app.modules.ai.skills` taxonomy from the description,
  `company_name` and `company_domain` from the configured company row. Salary where the
  vendor exposes it (Ashby compensation, Lever `salaryRange`), else `None`.
- Applies the `SearchQuery` title, location and `posted_within_hours` filters **client
  side** with the same semantics as `filter_catalogue` in `mock/base_mock.py`. Reuse that
  function if it fits; otherwise factor a shared helper.
- Uses `httpx` with a 15-second timeout, a descriptive `User-Agent`
  (`JobPilot/<version> (+https://github.com/...)`), and a per-process in-memory cache keyed
  by board URL with a 30-minute TTL, so repeated runs for several users do not re-fetch the
  same board. One failing board must not fail the others: catch, log at warning, and
  continue.
- Sets `is_mock = False`, `supports_auto_apply = True`, `uses_browser = True`,
  `requires_account = False`, a sensible `rate_limit_per_minute`, and a `terms_note` naming
  the public API.
- Overrides `submit_selectors` with the vendor's real submit button selectors
  (Greenhouse `#submit_app`, Lever `#btn-submit`, Ashby and SmartRecruiters as observed on
  their hosted forms). The blocker detector must still pause on CAPTCHA; Greenhouse and
  Lever hosted forms sometimes render a reCAPTCHA, and that must result in
  `REQUIRES_USER` with `PauseReason.CAPTCHA`, never an attempt to solve it.

### 3. Registry and discovery sources

- Register the two new sources in `adapters/registry.py`. `DISCOVERY_SOURCES` must include
  all four board sources.
- `jobs.service.resolve_discovery_sources` and `build_search_query`: a board source is
  only searched when the user has at least one company configured for it. Load the board
  list once per run, not per adapter call.
- `GET /jobs/sources` must show the four board adapters as real (`is_mock=false`).

### 4. Companies API and UI

- `CompanyRead` exposes `ats_type`, `ats_board_token`, `ats_board_url`.
- New endpoint `PUT /companies/{company_id}/board` with body
  `{"ats_type": "GREENHOUSE", "board_url": "https://boards.greenhouse.io/stripe"}`.
  The service parses the token out of the URL for all four vendors (also accept a bare
  token), validates it by fetching the board once (reject with 422 `board_not_found` on a
  404 or an empty, malformed payload), and stores type, token and URL.
- New endpoint `POST /companies` to create a company by name (plus optional website and
  board URL) so a user can add a company that is not in the registry yet. Reuse
  `get_or_create_company`.
- Frontend `Companies.tsx` and its feature components: add a "Career board" column and an
  edit dialog with vendor select plus board URL field and a "Verify" action that calls the
  endpoint and shows the open job count returned. Add an "Add company" button.
- Keep `frontend/src/types/api.ts` in sync.

### 5. Seed data

In `app/seed.py`, configure real boards for a handful of well-known companies that are
already in the registry or add them, so a fresh install finds real jobs on the first run.
Use boards you have verified return jobs at the time of writing, for example Greenhouse:
`stripe`, `gitlab`, `cloudflare`; Lever: `netflix`, `spotify`; Ashby: `ramp`, `notion`;
SmartRecruiters: `Bosch`, `Visa`. If a board is empty or gone when you check, pick another
and say so in your report. Seeding must not call the network: store the tokens only.

### 6. Tests

- Unit tests per adapter with recorded JSON fixtures under `backend/tests/fixtures/boards/`
  (one real response per vendor, trimmed to two or three postings). Assert the mapping to
  `DiscoveredJob` field by field, the HTML-to-text description, remote detection, salary
  extraction, and that a 404 on one board does not drop the results of another.
- Test the board URL parser for every vendor and for a bare token.
- Test `resolve_discovery_sources` only includes a board source when a company is
  configured for it.
- Test `PUT /companies/{id}/board` with the HTTP client mocked: success, 404 → 422,
  malformed payload → 422.
- One opt-in live test, skipped unless `JOBPILOT_LIVE_BOARDS=1`, that fetches one real
  Greenhouse board and asserts at least one `DiscoveredJob` comes back. Do not make the
  default suite depend on the network.
- Run the full suite. Do not hand back tests that were only collected.

### 7. Docs

Update `docs/CONTRACTS.md` (adapter section and `SearchQuery`), `docs/API.md` (new
endpoints), `docs/DATABASE.md` (new columns), and `docs/ARCHITECTURE.md` (adapter table).

## Hard constraints

- Public, documented, unauthenticated endpoints only. No scraping of pages that require
  login, no bypass of CAPTCHA, OTP, 2FA or bot detection. If a vendor's hosted form shows a
  CAPTCHA the application pauses for the human.
- Do not touch the mock platform adapters or the Gmail integration.
- Auto-submit stays off by default and per-source opt-in. Board sources default to
  `AUTO_APPLY` only because `supports_auto_apply` is true; do not change
  `resolve_source_mode`.
- Routers stay thin; logic lives in services and adapters. No Playwright import at module
  top level in the adapters package.
- Follow the DB conventions in `docs/DATABASE.md`: `StandardColumnsMixin`, named schemas,
  soft delete.
- Do not commit. Leave the working tree with your changes for review.

## Verification you must run and report

From `backend/` with `.venv/Scripts/python.exe` (Postgres on localhost:5432 and Redis on 6379
are running; Chromium is installed):

```
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic downgrade -1 && .venv/Scripts/python.exe -m alembic upgrade head
JOBPILOT_LIVE_BOARDS=1 .venv/Scripts/python.exe -m pytest -q -k live_board
```

From `frontend/`:

```
npm run build
```

Then start the API with the venv Python (not the system Python; the system one has no
Playwright), log in as the seeded demo user, call `PUT /companies/{id}/board` for one
Greenhouse company, then `POST /jobs/discover` with `sources: ["GREENHOUSE"]`, and confirm
real postings appear in `GET /jobs`. Finally run `POST /automation/run` with
`GREENHOUSE` in `enabled_sources` and `AUTO_APPLY`, auto-submit **off**, and confirm the run
reaches the autofill step and at least one application lands in `PAUSED` (ready for review)
or `REQUIRES_USER` (CAPTCHA) with a form snapshot and screenshot. Do not approve or submit
anything to a real company during verification.

## Report back in this format

1. Files changed, one line each.
2. Migration revision id.
3. Final pytest summary line, any failures in full, and the live board test result.
4. Which seed boards you verified and the job counts they returned.
5. The run log steps JSON from the Greenhouse automation run, plus the final
   `automation_state` and `pause_reason` of each application it touched.
6. Decisions you made that were not in this prompt, and why.
7. Anything not finished, and why.
