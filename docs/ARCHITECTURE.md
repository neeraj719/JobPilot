# JobPilot AI — Architecture

## 1. System overview

```
┌──────────────────────────────┐
│  Frontend (React + Vite)     │  Dashboard, Jobs, Queue, Applications, Approval Center, …
└──────────────┬───────────────┘
               │ REST (JSON, JWT bearer + HttpOnly refresh cookie)
┌──────────────▼───────────────┐
│  API (FastAPI)               │  app/main.py → module routers
│  ├─ auth / profiles          │
│  ├─ resumes  ──► AI service  │  LLMProvider abstraction (mock | ollama | openai | anthropic)
│  ├─ jobs ──► adapters        │  JobSourceAdapter per platform (mock + demo ATS + public ATS boards)
│  ├─ matching                 │  deterministic scoring + AI explanation
│  ├─ applications ──► browser │  answer engine, approval, Playwright runner
│  ├─ emails / integrations    │  Gmail read-only OAuth, classifier, linker
│  ├─ automation / dashboard   │  daily pipeline, stats
│  └─ demo_ats                 │  local Greenhouse-style career site for the demo
└──────────────┬───────────────┘
               │ SQLAlchemy 2 (sync)          ┌──────────────┐
┌──────────────▼───────────────┐              │ Worker       │ APScheduler: daily runs,
│  PostgreSQL                  │◄─────────────┤ (same image) │ Gmail sync, housekeeping
└──────────────────────────────┘              └──────┬───────┘
┌──────────────────────────────┐                     │
│  Redis                       │◄────────────────────┘ rate limiting, per-user automation locks
└──────────────────────────────┘
```

Layering rule (spec §21): **router → service → (AI | browser | adapters) → DB**. Routers are thin;
all business logic lives in `service.py` files; cross-module calls go through the functions listed
in `docs/CONTRACTS.md`.

Database rule: all 27 tables carry the same seven standard columns — a uuid `id`, `created_at`,
`updated_at`, `created_by`, `updated_by`, `is_active`, `deleted_at` — from one mixin; deletes are
soft and hidden by one global ORM filter in `app/core/soft_delete.py` (escape hatch:
`execution_options(include_deleted=True)`), and roles live in `master.roles` + `master.user_roles`
rather than in a column — see `docs/DATABASE.md` § Conventions.

The two timestamps belong to the database, not to the ORM: a server default fills them and one
`trg_<table>_updated_at` trigger per table bumps `updated_at` on any UPDATE that really changes the
row, so a write the ORM never sees moves it too. `created_by`/`updated_by` are stamped from the
acting user published by `app/core/actor.py` (the request's session, or `actor_context()` around a
background entry point); `NULL` means a system write.

## 2. Backend module map

| Module (`backend/app/modules/…`) | Responsibility |
|---|---|
| `common` | pagination, shared response schemas |
| `auth` | register / login / refresh rotation / logout, RBAC |
| `profiles` | candidate profile, job preferences, `CandidateContext` (flattened facts for the answer engine) |
| `companies` | company registry, P1/P2/P3/AVOID preferences, blacklisting |
| `resumes` | upload, versioning, text extraction, AI parsing to structured JSON |
| `ai` | `LLMProvider` abstraction, typed AI tasks (parse resume, explain match, answer question, cover letter, classify email, interview prep), skill taxonomy |
| `adapters` | `JobSourceAdapter` ABC, registry, mock adapters (Naukri, LinkedIn, Indeed, Hirist, Wellfound, Internshala, Glassdoor, Foundit), Demo ATS adapter, and the real public job board adapters in `adapters/boards/` (Greenhouse, Lever, Ashby, SmartRecruiters) |
| `jobs` | discovery orchestration, normalisation, duplicate detection (one job, many sources), job cards & filters |
| `matching` | weighted scoring (skills, title, experience, location, salary, company preference) + explanation |
| `applications` | queue, standard questions, answer engine (never invents facts), review summary, approval, submission, status tracking, events |
| `interviews` | interview records + AI preparation material |
| `browser` | Playwright session isolation, form detection, field mapping, autofill, application runner |
| `emails` | Gmail client, rule+AI classifier, application linker, status progression |
| `integrations` | Gmail OAuth (least privilege), connected job-platform accounts (encrypted) |
| `automation` | daily pipeline with safety rails, runs, locks, limits |
| `dashboard` | stats, charts, activity feed |
| `notifications`, `audit` | user notifications, audit log API |
| `demo_ats` (`app/demo_ats`) | local mock career site used by the Playwright demo |
| `worker` (`app/worker`) | APScheduler process |

## 3. Key flows

### 3.1 Discovery → matching
1. `POST /jobs/discover` (or the daily pipeline) builds a `SearchQuery` from the user's `JobPreference`.
2. Each enabled `JobSourceAdapter.search_jobs()` returns `DiscoveredJob`s.
3. `jobs.service.ingest_discovered` normalises company/title/location and runs the dedupe cascade:
   `(source, external_id)` → canonical URL → dedupe hash → fuzzy title/description. Duplicates become
   additional `JobSource` rows on the same `Job`.
4. `matching.service.analyze_job` scores every new job against the profile, default resume and
   preferences, stores a `JobMatch` (score parts, missing skills, explanation).

### 3.1a Job sources

| Source | Adapter | Discovery | Apply |
|---|---|---|---|
| Naukri, LinkedIn, Indeed, Hirist, Wellfound, Internshala, Glassdoor, Foundit, Company careers | `adapters/mock/*` (`is_mock=true`) | deterministic built-in catalogue, no network | simulated easy-apply (Glassdoor and Company careers: discover only) |
| Demo ATS | `adapters/demo_ats.py` | `/demo-ats/jobs.json` served by this backend | real Playwright form fill against the local demo site |
| Greenhouse | `adapters/boards/greenhouse.py` | `GET boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` | hosted form `job-boards.greenhouse.io/embed/job_app?for={token}&token={id}` |
| Lever | `adapters/boards/lever.py` | `GET api.lever.co/v0/postings/{token}?mode=json` | hosted form `jobs.lever.co/{token}/{id}/apply` |
| Ashby | `adapters/boards/ashby.py` | `GET api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true` | hosted form `jobs.ashbyhq.com/{token}/{id}/application` |
| SmartRecruiters | `adapters/boards/smartrecruiters.py` | `GET api.smartrecruiters.com/v1/companies/{token}/postings` (paginated) + `/postings/{id}` for the description | the posting's `applyUrl` on jobs.smartrecruiters.com |

The four board adapters are real (`is_mock=false`, `supports_auto_apply=true`, `uses_browser=true`,
no account). They read only public, documented, unauthenticated JSON APIs, with a descriptive
`User-Agent`, a 15 s timeout and a 30-minute per-process cache keyed by URL
(`adapters/boards/http.py`). Which boards to read comes from the company registry: every
company with `ats_type` + `ats_board_token`, minus the user's AVOID companies, is loaded once
per run by `jobs.service.load_board_tokens` and handed to the adapters in
`SearchQuery.board_tokens`; past `MAX_BOARDS_PER_RUN` (40) boards the user's own list goes first
(P1, P2, P3), then the rest by tag and name. Boards get there three ways: `PUT /companies/{id}/board`
(a pasted URL), the seed, which stores every entry of the bundled known-board list
`app/data/known_boards.json` (~190 verified companies, no network at seed time; re-check with
`scripts/verify_known_boards.py`), and board auto-detection (`companies/board_detect.py`, used by
`POST /companies`, `POST /companies/detect-board` and `POST /companies/{id}/detect-board`): the known
list by domain or name, then token guesses from the domain and name probed against the four APIs,
then a scan of the website and its first careers link for the vendors' hosted board URLs (Workday is
recognised but not readable). Detection makes at most 8 requests with a 10 s timeout, honours
robots.txt, fetches only public addresses on default ports, follows at most one redirect per page and
never a login; every hit is verified with one board fetch. A board source is searched only when at least one company is
configured on it. Postings are filtered client side with the same `filter_catalogue` the mock
adapters use. Applying reuses `GenericAtsFormAdapter`; the vendors' hosted forms carry a
CAPTCHA (reCAPTCHA on Greenhouse and Ashby, hCaptcha on Lever, a bot-check interstitial on
SmartRecruiters), which the detector reports and which pauses the application as
`REQUIRES_USER` / `CAPTCHA` — it is never solved.

### 3.2 Application workflow (spec §9)
```
DISCOVERED → QUEUED → IN_PROGRESS ─► form detected ─► profile mapped ─► AI answers ─► form filled
        ─► validation ─► PAUSED (USER_REVIEW)  ─► Approve & Submit ─► APPLIED ─► tracked
                       └► REQUIRES_USER (CAPTCHA / OTP / unknown question / sensitive question)
```
* `applications.answers.generate_answers` answers each question from what the user typed on the
  application, then the user's **standing answers** (answers given once and reused — consent and legal
  declarations only when the wording matches, never demographics), then `CandidateContext.flat`;
  only free-text questions are synthesised by the LLM; factual gaps become `NEEDS_USER_INPUT`.
* `browser.runner.ApplicationRunner` drives the adapter: for browser-based adapters it opens an
  isolated Playwright context, then `detect_form` → `FieldMapper` → records every question and answers
  it **before** `fill_form`, so only a required question nobody could answer pauses (an optional one
  never does); it stores a `form_snapshot` and pauses for review, or submits when auto-submit is on for
  the source. Blockers (CAPTCHA, OTP, login, registration) pause the run with the mapped fields in the
  snapshot and nothing typed — never bypassed.
* `applications.service.approve` is the only path that submits (unless the user explicitly enabled
  auto-submit for a supported source).

### 3.3 Email → status
Gmail (read-only) or simulated emails → `emails.classifier` (rules, LLM fallback) → `emails.linker`
(domain, company name, job title, application id) → `applications.service.transition` (never
downgrades) → notification.

### 3.4 Daily automation (spec §14)
`automation.pipeline.run_pipeline` executes the recorded steps
`search → collect → dedupe → analyze → filter → prioritize → enforce limits → queue → generate answers → autofill → approval queue → auto-submit (if allowed) → finish`
under a per-user lock, honouring daily / per-platform limits, delays and retry limits. The worker
process triggers it at the configured local time.

## 4. Extensibility

* **New job platform**: subclass `JobSourceAdapter` in `adapters/`, register it in `adapters/registry.py`.
  Implement `search_jobs` (official API preferred), `detect_application_type`, and the three apply
  steps. Browser-based adapters reuse `browser.detector/mapper/autofill` unchanged.
* **New LLM**: implement `LLMProvider` in `ai/providers/`, add it to the factory, set `LLM_PROVIDER`.
  Shipped providers: `mock` (deterministic rules, the default), `ollama` (free local model, the
  recommended real model for local use), `openai`, `anthropic`.
* **Local LLM (Ollama)**: `ai/providers/ollama.py` calls Ollama's native API (`POST /api/chat`,
  `stream: false`) with `httpx`; no SDK, no key, nothing leaves the machine.
  * Setup: install Ollama (`winget install --id Ollama.Ollama -e` on Windows; it runs as a
    background service on port 11434), `ollama pull qwen2.5:3b-instruct`, then set
    `LLM_PROVIDER=ollama` and `LLM_MODEL=qwen2.5:3b-instruct` in `.env` and restart the API.
  * Model choice: `qwen2.5:3b-instruct` (~1.9 GB) runs fully on a 4 GB GPU with an 8k context and is
    the default. `qwen2.5:7b-instruct` (~4.7 GB) gives better prose but splits between GPU and CPU
    on such a GPU and is roughly 5-10x slower; pick it only with more VRAM or patience.
  * `complete_json` sends the task's pydantic schema as Ollama's `format` (structured outputs), with
    every property marked required so a small model cannot skip keys; without a schema it uses
    `format: "json"`. The reply still goes through `extract_json`, and one retry with a "return only
    JSON" nudge covers unparseable or off-schema output before `ExternalServiceError(llm_bad_json)`.
    Temperature is 0.1 for structured tasks unless the caller passes one.
  * Failures map to `ExternalServiceError` codes: `llm_unavailable` (server down),
    `llm_model_missing` (404, model not pulled), `llm_timeout`, `llm_bad_json`. `ai.tasks` still
    falls back to the deterministic implementation on any of them.
  * Settings: `OLLAMA_BASE_URL` (default `http://localhost:11434`; containers use
    `host.docker.internal:11434`), `OLLAMA_KEEP_ALIVE` (`10m`), `OLLAMA_NUM_CTX` (`8192`). The request
    timeout is `LLM_TIMEOUT_SECONDS` when set explicitly, otherwise at least 120 s.
  * `GET /ai/status` reports `configured: true` only when the server answers `/api/tags` and the
    configured model is pulled; `OllamaProvider.describe()` adds base URL, Ollama version and the
    reason when it is not ready.
* **New question type**: add a mapping rule in `browser/mapper.py` and, if needed, an answer rule in
  `ai/tasks.py` / `applications/answers.py`.

## 5. Runtime & deployment

* `docker compose up` starts Postgres, Redis, API (runs migrations + seed), worker, and the Nginx-served
  frontend (proxying `/api` and `/demo-ats` to the API).
* The API and worker share the Playwright Python base image so Chromium is available for autofill.
* Configuration is environment-only (`.env.example`).
