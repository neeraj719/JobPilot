# ai-providers — progress

Stream: ai-providers (plan `notes/resume-studio-plan.md`, scope `notes/ai-providers-prompt.md`).
Test DB `jobpilot_test_aiprov`, ports 8093 / 5203, migration `c7e9b1d3f5a7`.

## Checklist

- ✅ Runtime interface (contracts §4.3–§4.5) — **available now** for builder/ats:
  - `app.modules.ai.runtime.complete_json(task, prompt, *, schema, system=None, max_tokens=1500)`
  - `app.modules.ai.runtime.complete(task, prompt, *, system=None, max_tokens=800, temperature=0.2)`
  - also `runtime.model_available(task=None)`, `runtime.model_info(task=None)`,
    `runtime.provider_is_mock(task=None)`, `runtime.last_call()` (fallback metadata)
  - `app.modules.ai.context.ai_user(user_id)` / `current_ai_user()`; `get_current_user` binds the request user
  - `app.modules.ai.safety.wrap_untrusted(label, text, *, max_chars)` / `UNTRUSTED_RULES` / `redact_for_logs`
  - `app.modules.ai.routing` (`AiWorkflow`, `TASK_WORKFLOWS`, `resolve`)
  - errors: `app.modules.ai.errors.AIProviderError` (subclass of `ExternalServiceError`), codes
    `provider_not_configured | invalid_credentials | quota_exceeded | model_unavailable | provider_timeout | budget_exceeded | provider_error`
- ✅ Models `app/models/ai_settings.py` + migration `c7e9b1d3f5a7` (scratch DB: 0 diffs vs models, downgrade clean; **applied to live `jobpilot`**)
- ✅ Providers: Gemini (`google-genai`), OpenAI-compatible, `list_models` / `test_connection`, error mapping, usage capture
- ✅ Registry (`ai/registry.py`) with prices (estimated, prices_as_of)
- ✅ `tasks._run` / `parse_resume` through runtime (mock still short-circuits)
- ✅ Settings / credentials / usage services + endpoints (`ai/settings_service.py`, `ai/usage.py`, `ai/router.py`)
- ✅ Frontend: `/resume/ai-settings` (`src/features/ai-providers/**`), link card on /settings — `npm run build` passes
- ✅ Tests `tests/test_ai_providers_{runtime,api,adapters}.py` (all green) + regression set green except one builder-caused failure
- 🔄 Browser check + screenshots `notes/screenshots/aiprov/`

## Decisions

- Dependency: `google-genai==1.55.0` (newest that keeps pydantic 2.11.4 / google-auth 2.40.1 /
  tenacity 9.1.2 pinned; it downgraded the venv's unpinned `websockets` 17.1 -> 15.0.1, which
  uvicorn 0.34 supports).
- Request user reaches the runtime through a mutable slot published by an *async* dependency
  (`context.request_ai_context`) and filled by `get_current_user` — a plain ContextVar set in a
  sync dependency would be lost (Starlette runs it in a context copy). Background work already
  under `app.core.actor.actor_context` (automation pipeline, executor) is picked up too.
- Server-level keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`) serve only the
  server's own default provider (`LLM_PROVIDER`); a user who picks another hosted provider
  must bring a key.
- Mock calls are never recorded or limited; Ollama calls are recorded at cost 0. The server
  default daily limit (`AI_DEFAULT_DAILY_CALL_LIMIT`, 500) applies to hosted calls only; a
  user's own limit counts every model call.
- Enums `AiCredentialStatus` / `AiUsageStatus` live in `app/models/ai_settings.py` (not the
  shared `enums.py`) to avoid shared-file churn.
- Usage pruning: `ai.usage.prune_usage_events()` exists but is **not** scheduled —
  `tests/test_automation.py::test_build_scheduler_registers_every_job` pins the job set, so
  wiring it is left to integration.

## Known, not mine

- `tests/test_ai_ollama.py::test_strict_schema_requires_non_nullable_keys_without_touching_the_original`
  fails because resume-builder added list fields to `ParsedResume` (achievements, …).
- `tests/test_db_conventions.py` pins 28 tables; `tests/test_migrations.py` runs `upgrade head`
  (multiple heads now) — both for integration.

## Blockers

none
