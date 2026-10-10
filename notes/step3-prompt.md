# Step 3 — Company career board auto-detection and starter list

You are a senior backend and full-stack developer on JobPilot AI (repo
`C:\Users\Neera\projects\job application`). Step 2 (public ATS board adapters for
Greenhouse, Lever, Ashby and SmartRecruiters; `Company.ats_type`, `ats_board_token`,
`ats_board_url`; `PUT /companies/{id}/board`; `POST /companies`) is already in the tree.
Read `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `backend/app/modules/adapters/boards/`
and `backend/app/modules/companies/service.py` before writing code. Do not commit.

## Why

After Step 2 a user has to know and paste a board URL per company. Friends will not do
that. Step 3 lets them type a company name or website and the system finds the board, and
ships a starter list so a fresh account has real jobs on day one.

## Scope

### 1. Detection service — `backend/app/modules/companies/board_detect.py`

`detect_board(name: str | None, website: str | None) -> BoardDetection` tries, in order,
stopping at the first hit, all with `httpx`, 10-second timeouts, a descriptive User-Agent,
and never more than 8 requests per detection:

1. **Known mappings** — a bundled JSON file `backend/app/data/known_boards.json`
   mapping normalised company name and domain to `(ats_type, token)`. Ship at least 150
   entries covering well-known product companies, Indian unicorns and startups that use
   the four supported ATS vendors. Verify each entry returns ≥ 1 job at the time of writing
   (a script under `backend/scripts/verify_known_boards.py` does this and prints a table;
   run it and include the summary). Remove any that fail.
2. **Token guess** — derive candidate tokens from the domain and name (`stripe`,
   `stripe-inc`, lowercase no-spaces, hyphenated) and probe the four public board APIs
   directly. A 200 with ≥ 1 posting is a hit.
3. **Careers page scan** — fetch `website`, then the first link whose text or href
   contains "careers", "jobs", "join", "work with us", follow at most one redirect each, and
   scan the HTML for the vendors' hosted URL patterns (`boards.greenhouse.io/<token>`,
   `jobs.lever.co/<token>`, `jobs.ashbyhq.com/<token>`, `careers.smartrecruiters.com/<Token>`,
   `<token>.wd1.myworkdayjobs.com` for Workday as detect-only). Public pages only; respect
   `robots.txt` for the careers host (skip the scan if disallowed) and never follow a login.
4. **No result** — return `ats_type=None` with the list of what was tried so the UI can
   offer the manual board URL field.

`BoardDetection`: `ats_type`, `token`, `board_url`, `method` (KNOWN / GUESS / SCAN / NONE),
`open_jobs` (count from the verification fetch), `tried: list[str]`, `careers_url` if seen.

### 2. API and integration

- `POST /companies/detect-board` body `{"name": ..., "website": ...}` → `BoardDetection`.
  Does not persist.
- `POST /companies` (from Step 2) gains `auto_detect: bool = true`: on create, run
  detection and store the result when found. Response includes the detection.
- `POST /companies/{id}/detect-board` re-runs detection for an existing company and stores
  the result when found; 200 with `method=NONE` when not.
- Rate limit these endpoints with the existing limiter at 10 per minute per user; they hit
  third-party sites.

### 3. Starter list and onboarding

- Seed: on first start (`SEED_DEMO_DATA`), insert the known-board companies from the JSON
  **without** network calls; the tokens are already in the file.
- Onboarding nudge: when a user has fewer than 3 companies with a board configured, the
  Companies page shows a "Quick start" panel listing 20 popular companies from the known
  list with one-click "Add to my list" at priority P2. Backend endpoint
  `GET /companies/suggestions?limit=20` returns them, excluding companies already in the
  user's preferences, ordered by tag (FAANG, unicorn, product, startup) then name.

### 4. Frontend

- "Add company" dialog: name and optional website; after submit show the detection result
  (vendor badge, open job count, method) or the manual board URL field when nothing was
  found.
- Company row: a "Detect" action for companies with no board.
- "Quick start" panel per §3.
- Keep `frontend/src/types/api.ts` in sync.

### 5. Tests

- Detection unit tests with `httpx` mocked: known hit, guess hit for each vendor, scan hit
  for each pattern, robots disallow skips the scan, request cap of 8 respected, no result.
- API tests for the three endpoints including rate limiting.
- Seed test: known companies inserted without network (assert no `httpx` call).
- Opt-in live test, skipped unless `JOBPILOT_LIVE_BOARDS=1`, that detects one real
  Greenhouse company from its website.
- Run your tests plus `tests/test_companies.py`, `tests/test_adapters.py` and
  `tests/test_seed.py` with
  `TEST_DATABASE_URL=postgresql+psycopg://jobpilot:jobpilot@localhost:5432/jobpilot_test_step3`.
- `npm run build` must pass.

## Hard constraints

- Public pages and public APIs only; honour robots.txt; no login walls; no CAPTCHA or bot
  detection bypass.
- No schema changes beyond what Step 2 added. If you believe a column is needed, stop and
  say so in the report instead of adding it.
- Do not touch `resumes`, `ai`, `matching`, `backend/app/models`, `backend/alembic`,
  or `frontend/src/features/resume`. Routers stay thin. Do not commit.

## Report

1. Files added or changed. 2. Known-board verification table summary (count verified,
count removed). 3. Test summary and failures in full; frontend build result. 4. One real
detection result JSON for a company found by SCAN. 5. Decisions not covered; anything
unfinished with the reason.
