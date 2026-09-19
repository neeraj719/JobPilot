# JobPilot AI

> Discover relevant software-engineering jobs across platforms, match them to your resume with AI,
> prepare and autofill applications with a human-in-the-loop approval step, and track every
> response — from one dashboard.

**Status:** MVP / prototype. The complete vertical slice works end to end:

```
Resume → Preferences → Job discovery → AI matching → Application queue → AI form answers
       → Browser autofill (Playwright) → Human review → Submission → Email response → Dashboard
```

Real job boards (LinkedIn, Naukri, Indeed, Hirist, Wellfound, Internshala, Glassdoor, Foundit) ship as
**mock adapters** behind a common `JobSourceAdapter` interface, plus a local **Demo ATS** career
site that the real Playwright autofill drives. Adding a production adapter is a single class.

---

## Quick start (Docker)

```bash
cp .env.example .env          # defaults work out of the box (mock LLM, no external keys needed)
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API + Swagger | http://localhost:8000/docs |
| Demo ATS career site | http://localhost:8000/demo-ats/ |
| Postgres | localhost:5432 (`jobpilot` / `jobpilot`) |

Demo login (seeded automatically): **demo@jobpilot.ai** / **DemoPass123!**

The seed creates a complete profile (2 yrs, React/Node/TypeScript/PostgreSQL/Docker/AWS), a parsed
resume, preferences (₹12 LPA+, Bangalore/Hyderabad/Pune/Delhi NCR/Remote, P1 = Google/Microsoft/Amazon),
~130 discovered jobs across all sources, a queue, three weeks of application history, emails,
interviews and audit logs — so the dashboard is alive on first login.

## Quick start (local, no Docker)

```bash
# backend
cd backend
python -m venv .venv && . .venv/Scripts/activate     # Windows; use .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
python -m playwright install chromium               # for the autofill demo
set DATABASE_URL=sqlite+pysqlite:///./dev.db         # or point at a local Postgres
alembic upgrade head && python -m app.seed
uvicorn app.main:app --reload --port 8000

# frontend (second terminal)
cd frontend && npm install && npm run dev            # http://localhost:5173, proxies /api → :8000
```

Run the tests: `cd backend && pytest` (SQLite + mock LLM, no services required) and
`cd frontend && npm run typecheck && npm run build`.

## The demo scenario (spec §31)

1. Log in as the demo user → **Dashboard** shows jobs found / matched / high-match / queued and what needs attention.
2. **Resume** → upload your own PDF/DOCX; AI extracts skills, experience, education into editable JSON.
3. **Profile / Settings** → salary, locations, titles, P1/P2/P3 companies, daily limit, minimum match.
4. **Jobs** → *Discover* pulls from every enabled source, merges duplicates, and shows match % with an explanation and missing skills.
5. **Application Queue** → pick a Demo ATS job → *Apply*. The engine generates answers from your profile (never inventing facts), Playwright opens the form, detects fields (name, email, phone, resume, experience, salary, LinkedIn, GitHub…), autofills them, and **pauses** on the question it cannot answer (`REQUIRES_USER`).
6. Answer it, review everything in the **Approval Center**, click **Approve & Submit** → status `APPLIED`.
7. The Demo ATS sends "Thank you for applying…" → the email classifier marks it `APPLICATION_RECEIVED` → the application and dashboard update. (With Gmail connected the same pipeline runs on your real inbox, read-only.)
8. **Automation** → enable the 09:00 daily run (limit 20/day, ≥75 % match) or press *Run now*.

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/DATABASE.md`](docs/DATABASE.md),
[`docs/SECURITY.md`](docs/SECURITY.md), [`docs/API.md`](docs/API.md) and the module contract in
[`docs/CONTRACTS.md`](docs/CONTRACTS.md).

```
frontend/   React 18 + TypeScript + Vite + Tailwind + shadcn/ui + React Router + Zustand + TanStack Query + RHF + Zod
backend/    FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic + PostgreSQL + Redis + APScheduler + Playwright
  app/core/        config, db, security (JWT / bcrypt / Fernet), rate limiting, audit
  app/models/      25 tables (see docs/DATABASE.md)
  app/modules/     auth · profiles · companies · resumes · ai · adapters · jobs · matching ·
                   applications · interviews · browser · emails · integrations · automation ·
                   dashboard · notifications · audit
  app/demo_ats/    local Greenhouse-style career site for the autofill demo
  app/worker/      scheduler process (daily runs, Gmail sync, housekeeping)
```

## Configuration

Everything is environment-driven — see [`.env.example`](.env.example). Highlights:

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | `mock` (default, deterministic, no key) · `openai` · `anthropic` |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | only needed for real providers |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | enable Gmail OAuth (read-only scope) |
| `SECRET_KEY`, `ENCRYPTION_KEY` | JWT signing / Fernet encryption — change in production |
| `DEFAULT_DAILY_APPLICATION_LIMIT`, `MAX_DAILY_APPLICATION_LIMIT` | automation safety rails |
| `PLAYWRIGHT_HEADLESS` | set `false` to watch the browser fill the demo form |

## Safety & compliance

* No CAPTCHA / OTP / 2FA / anti-bot bypass — the run pauses and asks you.
* Gmail: OAuth only, `gmail.readonly` scope, tokens encrypted at rest, never a password.
* Auto-submit is off by default and can only be enabled per supported source; every run respects
  daily/per-platform limits, delays and retry limits; every action is audit-logged.
* AI answers are grounded in your profile; missing facts become `NEEDS_USER_INPUT` rather than guesses.

## Adding a job platform

```python
# backend/app/modules/adapters/my_board.py
class MyBoardAdapter(JobSourceAdapter):
    source = JobSourceType.OTHER
    display_name = "My Board"
    def search_jobs(self, query: SearchQuery) -> list[DiscoveredJob]: ...
    def start_application(self, ctx): ...   # navigate
    def fill_application(self, ctx): ...    # reuse browser.detector / mapper / autofill
    def submit_application(self, ctx): ...
```
Register it in `adapters/registry.py`; it appears in Settings → Connected Accounts automatically.

## License

MIT (prototype).
