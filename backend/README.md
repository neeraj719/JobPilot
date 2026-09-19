# JobPilot AI — backend

FastAPI + SQLAlchemy 2 + Pydantic v2. Runs entirely on SQLite and a deterministic mock LLM, so the
whole product — discovery, matching, AI answers, Playwright autofill, email classification,
automation, dashboard — works with **no Docker, no Postgres, no API keys**.

* API + Swagger: <http://localhost:8000/docs> · OpenAPI: `/openapi.json`
* Demo ATS career site: <http://localhost:8000/demo-ats/>
* Endpoint reference and the demo walkthrough: [`../docs/API.md`](../docs/API.md)
* Module contract (the binding spec): [`../docs/CONTRACTS.md`](../docs/CONTRACTS.md)

---

## Run it locally (no Docker)

```bash
cd backend
python -m venv .venv
. .venv/Scripts/activate          # Windows;  . .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
python -m playwright install chromium      # only needed for the autofill demo + browser tests

export DATABASE_URL="sqlite+pysqlite:///./dev.db"   # Windows cmd: set DATABASE_URL=...
export ENV=development

alembic upgrade head        # create the 25 tables
python -m app.seed          # demo account with three weeks of history (idempotent)
uvicorn app.main:app --reload --port 8000
```

Log in as **demo@jobpilot.ai / DemoPass123!**.

The scheduler (daily automation runs, Gmail sync, housekeeping) is a separate process:

```bash
python -m app.worker.main
# or, for a single-process dev setup:
RUN_SCHEDULER_IN_API=true uvicorn app.main:app --port 8000
```

On Postgres, point `DATABASE_URL` at `postgresql+psycopg://user:pass@host:5432/db` and run the same
`alembic upgrade head` — the migration is written to run unchanged on both engines. A file-backed
SQLite database is opened in WAL mode so the API, the automation threads and the bundled demo ATS
can write concurrently.

### Reseeding

`python -m app.seed` exits early when the demo user already exists. `python -m app.seed --force`
deletes that user's data and rebuilds it. The seed discovers real jobs through every mock adapter,
parses a genuinely generated PDF resume and fabricates ~40 applications (a few of them dated a few
hours ago **today**, so the dashboard's "Applications Today" tile is never zero on first login).

## Tests

```bash
cd backend
./.venv/Scripts/python.exe -m pytest              # ~630 tests, in-memory SQLite + mock LLM
./.venv/Scripts/python.exe -m pytest -m browser   # only the live-Chromium tests
./.venv/Scripts/python.exe -m pytest -m "not browser"
```

`tests/conftest.py` points the suite at `sqlite+pysqlite:///:memory:`, forces `LLM_PROVIDER=mock`,
truncates every table between tests and resets the in-memory rate limiter, so no external service
is ever required. Tests marked `browser` start a real uvicorn server in a thread and drive Chromium
against `/demo-ats`; they skip themselves when Chromium is not installed.

### End-to-end smoke test

`scripts/smoke_e2e.py` drives a **running** deployment over HTTP and prints PASS/FAIL per step
(login → every list screen → demo ATS → discovery → a full automation run → an email that moves an
application forward, and with `--with-browser` the queue → autofill → answer → approve → confirmation
email path):

```bash
./.venv/Scripts/python.exe scripts/smoke_e2e.py --base-url http://localhost:8000 --with-browser
```

It exits non-zero if any step fails, so it works as a deployment gate.

## Environment variables

Everything is read from the environment (`.env` at the repo root; see `../.env.example`). Real
environment variables win over `.env`.

| Variable | Default | Purpose |
|---|---|---|
| `ENV` | `development` | `development` / `test` / `production` |
| `API_PREFIX` | `/api/v1` | prefix for every application route |
| `DATABASE_URL` | Postgres DSN | `sqlite+pysqlite:///./dev.db` for local work |
| `REDIS_URL` | `redis://localhost:6379/0` | rate limiting + the automation lock; both fall back to in-process |
| `SECRET_KEY` | dev value | JWT signing — **change in production** |
| `ENCRYPTION_KEY` | dev value | Fernet key for OAuth tokens, credentials and browser state |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | `30` / `14` | token lifetimes |
| `RATE_LIMIT_PER_MINUTE` / `AUTH_RATE_LIMIT_PER_MINUTE` | `120` / `10` | per user (or IP) |
| `UPLOAD_DIR` / `MAX_UPLOAD_MB` | `./uploads` / `10` | resumes, screenshots, demo-ATS submissions |
| `LLM_PROVIDER` | `mock` | `mock` (deterministic, no key) · `openai` · `anthropic` |
| `LLM_MODEL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `LLM_TIMEOUT_SECONDS` | — | only for real providers |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` | — | Gmail OAuth; scope is `gmail.readonly` only |
| `PLAYWRIGHT_HEADLESS` | `true` | set `false` to watch the browser fill the form |
| `BROWSER_ACTION_DELAY_MS` / `BROWSER_TIMEOUT_MS` | `250` / `15000` | autofill pacing and page timeouts |
| `DEMO_ATS_BASE_URL` | `http://localhost:8000` | URL the **browser** uses to reach the demo ATS (the service name inside Docker) |
| `DEFAULT_DAILY_APPLICATION_LIMIT` / `MAX_DAILY_APPLICATION_LIMIT` | `20` / `100` | automation safety rails |
| `DEFAULT_MIN_MATCH_SCORE` / `AUTOMATION_RETRY_LIMIT` / `AUTOMATION_DELAY_SECONDS` | `75` / `3` / `1.0` | pipeline defaults |
| `SEED_DEMO_DATA`, `DEMO_USER_EMAIL`, `DEMO_USER_PASSWORD` | `true`, `demo@jobpilot.ai`, `DemoPass123!` | demo account |
| `RUN_SCHEDULER_IN_API` | `false` | run APScheduler inside the API process instead of the worker |

If you change the port, change `DEMO_ATS_BASE_URL` with it — the Playwright runner navigates to
that host, not to whatever the API thinks its own address is.

## Module map

```
app/
  main.py            FastAPI factory: middleware, exception handlers, router mounting
  seed.py            python -m app.seed — the whole demo dataset (idempotent, --force rebuilds)
  core/              config · database · security (JWT/bcrypt/Fernet) · deps · exceptions
                     · logging · rate_limit · audit
  models/            25 SQLAlchemy tables + every enum (models/enums.py is the vocabulary)
  demo_ats/          the bundled Greenhouse-style career site (Jinja2) the autofill demo drives
  worker/            APScheduler process: daily runs, Gmail sync, NO_RESPONSE sweep, cleanup
  modules/
    common/          Pagination, PageResponse, OkResponse — the shared envelope
    auth/            register / login / refresh-rotation / logout, password changes
    profiles/        candidate profile + job preferences + CandidateContext for the AI
    resumes/         upload, text extraction (pypdf / python-docx), parsing, versioning
    companies/       company registry, P1/P2/P3/AVOID priorities, blacklisting
    adapters/        JobSourceAdapter + 9 mock boards + demo ATS / Greenhouse / Lever
    jobs/            discovery orchestration, normalisation, cross-platform dedupe, the job list
    matching/        weighted scoring (skills, experience, location, salary, preferences) + AI reason
    applications/    queue, answer engine, review, approval, submission, events, executor registry
    browser/         Playwright session, form detector, field mapper, autofill, ApplicationRunner
    emails/          Gmail client, rule+LLM classifier, application linker, status pipeline
    integrations/    Gmail OAuth (read-only) and connected platform accounts
    automation/      config, per-user limits, locks, the pipeline, runs API
    dashboard/       stats, charts, activity timeline
    interviews/      interview rounds + AI prep sheets
    notifications/   in-app notifications
    audit/           the audit trail API
```

Layering is strict: **routers stay thin** (parse, call a service, return a schema), services hold
the logic, and cross-module calls go through the public service functions listed in
`docs/CONTRACTS.md` — often lazily imported so no module hard-depends on another's import time.

## Adding a `JobSourceAdapter`

1. Create `app/modules/adapters/my_board.py` and subclass `JobSourceAdapter` (or
   `GenericAtsFormAdapter` from `adapters/demo_ats.py` if the platform is a hosted ATS form, which
   gives you navigate → detect → map → fill → submit for free):

   ```python
   class MyBoardAdapter(JobSourceAdapter):
       source = JobSourceType.OTHER          # add a value to models/enums.py for a real platform
       display_name = "My Board"
       is_mock = False
       supports_auto_apply = False           # True only where submitting is actually permitted
       requires_account = True
       uses_browser = False
       rate_limit_per_minute = 20
       terms_note = "Why using this source is legitimate, and what we deliberately do not do."

       def search_jobs(self, query: SearchQuery) -> list[DiscoveredJob]: ...   # the only abstract one

       # optional — the base class returns a clean "not supported" for each
       def get_job_details(self, external_id: str) -> DiscoveredJob | None: ...
       def detect_application_type(self, job: DiscoveredJob) -> ApplicationType: ...
       def authenticate(self, session=None, credentials=None) -> AuthResult: ...
       def start_application(self, ctx: ApplyContext) -> ApplyStepResult: ...
       def fill_application(self, ctx: ApplyContext) -> ApplyStepResult: ...
       def submit_application(self, ctx: ApplyContext) -> ApplyStepResult: ...
   ```

2. Register it in `app/modules/adapters/registry.py`. It then shows up in `GET /jobs/sources`,
   `GET /integrations` and the automation's source filters automatically.
3. Give it a rank in `APPLY_SOURCE_RANK` (`app/modules/jobs/service.py`) so the engine knows whether
   it is a better place to apply from than an aggregator.
4. Add `tests/test_adapters.py` coverage. Adapters must never bypass a CAPTCHA, OTP, 2FA or bot
   check: detect it, return `AutomationState.REQUIRES_USER` with a `PauseReason`, and let the user
   finish. Only return `supports_auto_apply = True` where automated submission is genuinely allowed.

## Adding an LLM provider

1. Create `app/modules/ai/providers/my_provider.py` subclassing `LLMProvider` from
   `app/modules/ai/provider.py` — two abstract methods, the rest has sane defaults:

   ```python
   class MyProvider(LLMProvider):
       name = "my_provider"
       model = "my-model-v1"

       def complete(self, prompt: str, *, system: str | None = None,
                    max_tokens: int = 800, temperature: float = 0.2) -> str: ...

       def complete_json(self, prompt: str, *, schema: dict[str, Any] | type[BaseModel],
                         system: str | None = None, max_tokens: int = 1500) -> dict[str, Any]: ...

       @property
       def is_configured(self) -> bool:      # e.g. bool(settings.MY_PROVIDER_API_KEY)
           ...
   ```

   Override `supports_task()` / `run_task()` only for a provider that can answer a skill
   deterministically without a model call (that is how the mock provider works).

2. Wire it into `get_llm_provider()` in `app/modules/ai/factory.py` and add the literal to
   `Settings.LLM_PROVIDER` in `app/core/config.py` (plus its API-key setting).
3. Nothing else changes: every skill in `app/modules/ai/skills.py` and every task in
   `app/modules/ai/tasks.py` goes through the provider interface, and a provider error or
   unparseable JSON automatically falls back to the deterministic mock implementation so uploads
   and answer generation never 500.
4. The rule that outranks everything: the AI may only restate facts from the candidate's profile
   and resume. A missing fact becomes a `NEEDS_USER_INPUT` answer — never a guess.

## Database migrations

```bash
alembic revision --autogenerate -m "add x"   # review the result by hand
alembic upgrade head
alembic downgrade -1
```

`tests/test_migrations.py` asserts that `compare_metadata` reports **no** difference between the
migrations and the models, so a forgotten migration fails the suite.
