# ai-providers — bring-your-own AI provider, per-task models, secure keys, usage

You are **ai-providers**, a senior backend-leaning full-stack developer on JobPilot AI. Read
`notes/resume-studio-plan.md` (rules, ownership, contracts — binding), then
`notes/resume-studio-spec.md` §7, §8, §11–§13, then this file. Before writing code read
`backend/app/modules/ai/**` (all of it), `backend/app/core/{security,deps,config,
rate_limit,exceptions,audit}.py`, `backend/app/modules/integrations/gmail_oauth.py` (how
tokens are encrypted today), `backend/app/models/{automation,email}.py` (encrypted
columns), `frontend/src/pages/Settings.tsx`, `frontend/src/features/settings/**`,
`frontend/src/pages/resume/AiModelSettings.tsx` (your placeholder), `docs/SECURITY.md`.
Test DB `jobpilot_test_aiprov`; ports 8093 / 5203; progress file
`notes/ai-providers-progress.md`; migration id `c7e9b1d3f5a7` (down_revision
`a9c3e5b7d1f0`). Do not commit.

## Outcome

Each user can pick an AI provider — the free local Ollama (default, nothing leaves the
machine), OpenAI, Google Gemini, Anthropic Claude, or an OpenAI-compatible self-hosted
endpoint — paste their own API key (stored encrypted, never shown again, masked, rotatable,
deletable), test the connection, see the models that key can use, choose a default model and
a different model per workflow (resume generation, ATS analysis, bullet rewriting, JD
analysis, final review), set an optional fallback, see usage and estimated cost, and
understand that a ChatGPT/Gemini/Claude *subscription* is not API billing. Every AI call in
the app routes through this configuration via one runtime interface.

## Backend

### Runtime interface — **ship this first** (plan §4.3–§4.5), other streams depend on it
* `app/modules/ai/context.py`: `contextvars` holder for the current user id;
  `ai_user(user_id)` context manager; `current_ai_user()`. Set it in
  `app/core/deps.py::get_current_user` (one line, keep the dependency's behaviour) and
  clear it at request end (the contextvar is per task/thread — verify with a test that two
  requests in the TestClient do not leak).
* `app/modules/ai/safety.py`: `wrap_untrusted(label, text, *, max_chars)` and
  `UNTRUSTED_RULES` (plan §4.5); also `redact_for_logs(text)`.
* `app/modules/ai/routing.py`: `AiWorkflow` (`generation, analysis, rewriting,
  jd_analysis, review, general`), `TASK_WORKFLOWS` mapping the task names in plan §4.3 and
  every existing task name in `tasks.py` (parse_resume, polish_resume_recommendations,
  explain_match, generate_answer, generate_cover_letter, classify_email,
  generate_interview_prep → `general`); `resolve(db, user_id, task) -> Resolved(provider,
  model, source: "task_override" | "user_default" | "server_default", fallback)`.
* `app/modules/ai/runtime.py`: `complete_json(task, prompt, *, schema, system=None,
  max_tokens=1500)`, `complete(task, prompt, *, system=None, max_tokens=800,
  temperature=0.2)`. Builds the provider for the resolved (provider, model, credential)
  through `factory` (cache per (user, provider, model, credential_version) — never leak a
  key into a global), prepends `UNTRUSTED_RULES` to `system`, times the call, records a
  usage event (tokens when the SDK returns them, else an estimate flagged `estimated`),
  maps SDK errors to `ExternalServiceError` codes `provider_not_configured |
  invalid_credentials | quota_exceeded | model_unavailable | provider_timeout |
  budget_exceeded | provider_error` with user-actionable messages (no secrets, no raw
  bodies). **Fallback only when the user turned it on** and only to the configured fallback;
  record that it happened in the usage event and the response metadata; never fall back
  silently to a paid provider. The mock provider stays the test default and the
  deterministic fallback used by `tasks.py` today.
* Keep `get_llm_provider()` (no args) working as the server default. Make `tasks._run` go
  through `runtime` so **existing** features (parsing, recommendations polish, answers,
  cover letters, email classification) honour the user's choice too — with the mock still
  short-circuiting in tests. Run `tests/test_ai.py`, `tests/test_resume_*`,
  `tests/test_applications*.py`, `tests/test_emails*.py` to prove nothing regressed.

### Providers (`providers/`)
* `gemini.py` via the official `google-genai` SDK (pin in `requirements.txt`, lazy import):
  `complete`, `complete_json` (response_mime_type JSON + schema), timeouts, model listing.
* `openai_compatible.py` (or a `base_url` option on the OpenAI adapter) for self-hosted
  OpenAI-compatible servers (vLLM, LM Studio, llama.cpp, OpenRouter): base URL + optional
  key; URL validated (https, or http only for localhost/private ranges that the *user*
  typed — document the trade-off); never used as a fallback automatically.
* Existing `openai.py` / `anthropic.py` / `ollama.py`: accept an explicit `api_key`,
  `model`, `base_url` (already partly there), add `list_models()` (OpenAI `GET /v1/models`,
  Anthropic `GET /v1/models`, Gemini `models.list`, Ollama `/api/tags`) and
  `test_connection()` (one cheap call, returns latency, model, and the error class).
* `registry.py`: maintained model registry per provider — id, display name, context
  window, input/output price per 1M tokens (USD, with `prices_as_of` date and
  `estimated: true`), capabilities (json_mode, vision), `recommended_for` workflows, and
  for Ollama the local models probed live. Live listing merges into the registry; unknown
  models are allowed but flagged "not in registry — pricing unknown". Validate a chosen model
  exists before saving (live list if reachable, registry otherwise).

### Settings and credentials (`app/models/ai_settings.py`, `settings_service.py`)
* `master.ai_provider_settings`: user_id (partial unique, active), default_provider,
  default_model, workflow_models JSON `{workflow: {provider, model}}`, fallback_provider,
  fallback_model, fallback_enabled bool default false, daily_call_limit int nullable,
  monthly_budget_usd numeric nullable, data_residency_ack bool (user acknowledged that
  hosted providers receive resume text).
* `master.ai_provider_credentials`: user_id, provider, encrypted_api_key (Fernet via
  `encrypt_str`), key_hint (last 4), base_url nullable, credential_version int, status
  (UNTESTED|OK|ERROR), last_tested_at, last_error (sanitised), rotated_at; partial unique
  (user_id, provider). Deleting = soft delete + wipe the ciphertext.
* `transaction.ai_usage_events` (append-only): user_id, provider, model, task, workflow,
  input_tokens, output_tokens, tokens_estimated bool, estimated_cost_usd, duration_ms,
  status (OK|ERROR|FALLBACK), error_code, created_at. Index (user_id, created_at).
* Enforcement in `runtime`: daily call limit and monthly budget (sum of events this
  month) → `budget_exceeded` before the call; per-user rate limit on the test-connection
  and model-list endpoints via `app.core.rate_limit`.
* Endpoints (`/api/v1/ai`, extend `ai/router.py`): `GET /ai/providers` (catalog with
  capabilities, docs URL, billing note "API access is billed separately from chat
  subscriptions", local-vs-hosted privacy note), `GET /ai/settings`, `PUT /ai/settings`,
  `PUT /ai/credentials/{provider}` `{api_key, base_url?}` (requires recent auth —
  `app.core.deps.require_recent_auth` — returns masked hint only), `DELETE
  /ai/credentials/{provider}`, `POST /ai/credentials/{provider}/test`, `GET
  /ai/providers/{provider}/models`, `GET /ai/usage?range=7d|30d|month` (totals, per
  workflow, per day series, cost estimate, `estimated` flags), `GET /ai/status` (exists —
  extend with the user's effective configuration). Audit `ai.credential_saved/rotated/
  deleted/tested`, `ai.settings_updated` without secrets. Logging: never log prompts with
  resume text at INFO; DEBUG only through `redact_for_logs`.
* Config (`app/core/config.py`, additive): `AI_ALLOW_HOSTED_PROVIDERS` (default true),
  `AI_DEFAULT_DAILY_CALL_LIMIT`, `AI_USAGE_RETENTION_DAYS` (prune job in the worker
  scheduler if trivial, else document), `GOOGLE_API_KEY` server-level optional like the
  others. `.env.example` updated.

## Frontend (`src/features/ai-providers/**`, `qk.aiProviders`)

**AI Model Settings** (`/resume/ai-settings`), also linked from a card on `/settings`:
* Header with the effective setup ("Local Ollama · qwen2.5:3b-instruct — private, free") and
  a privacy/billing explainer (hosted providers receive resume text; API billing ≠ chat
  subscription; links to each provider's key page).
* Provider cards (Ollama, OpenAI, Gemini, Anthropic, OpenAI-compatible): status pill
  (Not configured / Untested / Connected · 420 ms / Error: invalid key), key input
  (password field, paste-friendly, never prefilled; after save shows `••••1234` with
  Rotate and Remove), base URL for compatible/Ollama, **Test connection** with the result
  and an actionable error, model select populated from `/models` (grouped: recommended,
  other, unknown-pricing), refresh models.
* Workflow routing table: rows Resume generation · ATS analysis · Bullet rewriting · JD
  analysis · Final review; each a provider+model select defaulting to "Use default"; a
  default row; fallback section (toggle + provider/model, explained: "only used when the
  primary fails; never silently"); limits (daily calls, monthly budget) with helper text.
* Usage: totals for the range, cost estimate with the `estimated` caveat and prices-as-of
  date, small recharts series per day, table per workflow/provider.
* Validation with zod, optimistic-free (wait for server), toasts, inline errors from the
  server codes; loading/empty/error states; keyboard accessible; light/dark. The page must
  not call any provider on load except the local Ollama probe (cheap) — tests of hosted
  providers only on user action.

## Tests
`tests/test_ai_providers_*`: encryption round trip and that no endpoint ever returns the
key (grep every response body), masking, recent-auth required for credential writes,
rotate bumps `credential_version` and evicts the cached client, delete wipes ciphertext,
routing resolution precedence (task override > user default > server default), fallback
only when enabled and recorded, budget/daily limits → `budget_exceeded`, error mapping for
each code (mock SDK exceptions), usage event recorded with duration, contextvar isolation
across requests and in `ai_user` for threads, Gemini adapter JSON mode (mocked SDK),
model listing merge with the registry, OpenAI-compatible base URL validation, settings
PUT validation (unknown model rejected), ownership (user A never sees user B's settings),
`tasks._run` goes through runtime and the mock still short-circuits. Run with your DB: your
tests + `tests/test_ai.py tests/test_resumes.py tests/test_resume_apply.py
tests/test_resume_recommendations.py tests/test_applications*.py tests/test_emails*.py
tests/test_auth*.py`. `npm run build`. Browser: user `aiprov.check@jobpilot.ai`, open the
page, test Ollama (real, running), save a fake OpenAI key and see the actionable
"invalid credentials" result, set a workflow override, view usage after running one
resume parse through the API; screenshots light+dark in `notes/screenshots/aiprov/`.

## Constraints recap
Secrets never leave the server, never logged, never in errors/audit. No silent fallback to
paid providers. Local Ollama remains the default and keeps working with zero configuration.
Keep `get_llm_provider()` and `tasks.py` public functions backward compatible. New SDKs
lazy-imported and pinned. Do not edit resumes/ats/matching modules, `Sidebar.tsx`,
`navigation.ts`. Keep the app importable at every step (the owner's :8000 reloads your
edits). Update `notes/ai-providers-progress.md` as you go. Report per plan §8.
