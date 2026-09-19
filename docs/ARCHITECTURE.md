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
│  ├─ resumes  ──► AI service  │  LLMProvider abstraction (mock | openai | anthropic)
│  ├─ jobs ──► adapters        │  JobSourceAdapter per platform (mock + demo ATS + ATS stubs)
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

## 2. Backend module map

| Module (`backend/app/modules/…`) | Responsibility |
|---|---|
| `common` | pagination, shared response schemas |
| `auth` | register / login / refresh rotation / logout, RBAC |
| `profiles` | candidate profile, job preferences, `CandidateContext` (flattened facts for the answer engine) |
| `companies` | company registry, P1/P2/P3/AVOID preferences, blacklisting |
| `resumes` | upload, versioning, text extraction, AI parsing to structured JSON |
| `ai` | `LLMProvider` abstraction, typed AI tasks (parse resume, explain match, answer question, cover letter, classify email, interview prep), skill taxonomy |
| `adapters` | `JobSourceAdapter` ABC, registry, mock adapters (Naukri, LinkedIn, Indeed, Hirist, Wellfound, Internshala, Glassdoor, Foundit), Demo ATS adapter, Greenhouse/Lever stubs |
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

### 3.2 Application workflow (spec §9)
```
DISCOVERED → QUEUED → IN_PROGRESS ─► form detected ─► profile mapped ─► AI answers ─► form filled
        ─► validation ─► PAUSED (USER_REVIEW)  ─► Approve & Submit ─► APPLIED ─► tracked
                       └► REQUIRES_USER (CAPTCHA / OTP / unknown question / sensitive question)
```
* `applications.answers.generate_answers` answers each question from `CandidateContext.flat` first;
  only free-text questions are synthesised by the LLM; factual gaps become `NEEDS_USER_INPUT`.
* `browser.runner.ApplicationRunner` drives the adapter: for browser-based adapters it opens an
  isolated Playwright context, `detect_form` → `FieldMapper` → `fill_form`, stores a `form_snapshot`
  and pauses for review. Blockers (CAPTCHA, OTP, login, registration) pause the run — never bypassed.
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
* **New question type**: add a mapping rule in `browser/mapper.py` and, if needed, an answer rule in
  `ai/tasks.py` / `applications/answers.py`.

## 5. Runtime & deployment

* `docker compose up` starts Postgres, Redis, API (runs migrations + seed), worker, and the Nginx-served
  frontend (proxying `/api` and `/demo-ats` to the API).
* The API and worker share the Playwright Python base image so Chromium is available for autofill.
* Configuration is environment-only (`.env.example`).
