# Local LLM — Ollama provider so JobPilot runs without paid API keys

You are a senior backend developer on JobPilot AI (FastAPI + SQLAlchemy 2 + PostgreSQL,
repo `C:\Users\Neera\projects\job application`). Read `docs/ARCHITECTURE.md` §4 and
`backend/app/modules/ai/provider.py`, `factory.py`, `providers/openai.py` and
`providers/mock.py` before writing code. Do not commit.

## Why

The user wants the product to run for themselves and friends at near-zero cost, so the LLM
must be a free local model instead of the OpenAI or Anthropic APIs. The `LLMProvider`
abstraction already exists with `mock`, `openai` and `anthropic` backends; add a fourth,
`ollama`, and make it the recommended default for local use.

## Target machine (already measured, do not re-measure)

- Windows 11, 12th-gen Intel i5-12450H, 12 logical cores
- 15.6 GB RAM, typically 4 to 6 GB free while Postgres, Redis, Chromium and the dev server run
- NVIDIA GeForce RTX 3050 Laptop GPU with 4 GB VRAM
- 320 GB free disk
- Ollama is **not** installed; `winget` is available; nothing listens on port 11434

## Scope

### 1. Install and run Ollama locally

- Install with `winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements`.
  If winget fails, download the official Windows installer from ollama.com and run it
  silently. Report which path you used.
- Start the server (`ollama serve` runs as a background service after install on Windows;
  confirm `GET http://localhost:11434/api/tags` answers).
- Pull the default model: `qwen2.5:3b-instruct`. It fits in 4 GB VRAM with room for context,
  runs fully on the GPU, follows JSON instructions well, and is the right size for this
  machine. Also pull `qwen2.5:7b-instruct` as an optional higher-quality model; it will
  split between GPU and CPU and be slower, so it is not the default.
- Record the measured tokens per second for both on a 300-token JSON completion in your
  report (`ollama run <model> --verbose`).

### 2. `OllamaProvider` (`backend/app/modules/ai/providers/ollama.py`)

- Talk to Ollama's native API with `httpx`: `POST /api/chat` with `stream: false`, and for
  `complete_json` pass `format: "json"` (or the JSON schema object when the provided
  schema is available, Ollama supports structured outputs) so the model is constrained to
  valid JSON. Keep the existing `extract_json` fallback for safety.
- Settings in `app/core/config.py`: extend `LLM_PROVIDER` literal with `"ollama"`, add
  `OLLAMA_BASE_URL: str = "http://localhost:11434"`, `OLLAMA_KEEP_ALIVE: str = "10m"`,
  and `OLLAMA_NUM_CTX: int = 8192`. `LLM_MODEL` defaults to `qwen2.5:3b-instruct` when the
  provider is `ollama` and nothing is set. Respect `LLM_TIMEOUT_SECONDS`; local models are
  slower than APIs, so raise the default for ollama to 120 seconds if the global default is
  lower.
- `is_configured()` returns true when the base URL answers `/api/tags` **and** the
  configured model is in the list; `describe()` reports base URL, model, whether the model
  is pulled, and the Ollama version from `/api/version`.
- Register it in `factory.py`; `provider_status()` and `GET /ai/status` must show it.
- Temperature low (0.1) for structured tasks; honour any `temperature` the task passes.
- Handle these failure modes with the project's existing exception types and clear
  messages: server down (connection refused), model not pulled (404), timeout, and a
  response that is not valid JSON after one retry with a "return only JSON" nudge.
- Do not touch `providers/mock.py`, `tasks.py`, `prompts.py` or `schemas.py`; another
  developer is editing those for the resume recommendations feature at the same time.

### 3. Prompt-fit check against a small model

Run each existing task once against `qwen2.5:3b-instruct` using the seeded demo data
through the real provider (parse resume, explain match, answer question, cover letter,
classify email, interview prep). For every task, record whether the output validated
against its Pydantic schema. If a task fails validation more than once in three attempts,
fix the **provider side** (schema-constrained output, system message, retries), not the
prompt text, and note it. Report the pass table.

### 4. Configuration and docs

- `.env.example`: document the `ollama` provider as the recommended local option with the
  three new variables. In the real `.env`, set `LLM_PROVIDER=ollama` and
  `LLM_MODEL=qwen2.5:3b-instruct` so the running dev server picks it up on restart. Change
  nothing else in `.env`.
- `docker-compose.yml`: add a commented-out `ollama` service block with the
  `ollama/ollama` image, a named volume, and the NVIDIA GPU reservation stanza, with a
  comment that on this machine Ollama runs natively on the host and the API container
  reaches it via `host.docker.internal:11434`. Do not enable it.
- `docs/ARCHITECTURE.md` §4 and `README.md` quick start: how to install Ollama, pull the
  model, and set the two variables. Mention the 7b option and its trade-off.

### 5. Tests

- Unit tests for `OllamaProvider` with `httpx` mocked: `complete`, `complete_json` happy
  path with `format: json`, server down, model missing, timeout, non-JSON retry path,
  `is_configured` true and false, `describe`.
- A factory test that `LLM_PROVIDER=ollama` builds the provider and `provider_status`
  reports it.
- One opt-in live test, skipped unless `JOBPILOT_LIVE_OLLAMA=1`, that runs `complete_json`
  against the real server and validates a tiny schema.
- Run the tests you added plus `tests/test_ai.py` with
  `TEST_DATABASE_URL=postgresql+psycopg://jobpilot:jobpilot@localhost:5432/jobpilot_test_llm`.
  Do not run the whole suite; other agents are running theirs.

## Hard constraints

- Local only. Never send resume or profile text to any external service during this work.
- Do not change the behaviour of the `mock`, `openai` or `anthropic` providers.
- Do not touch `backend/app/modules/adapters`, `companies`, `jobs`, `resumes`,
  `backend/app/models`, `backend/alembic`, or the frontend; other developers are there.
- No database changes.
- Do not commit, stash, reset or checkout.

## Report

1. Install path used, Ollama version, models pulled with sizes, measured tokens per
   second for each.
2. Files added or changed, one line each.
3. The task pass table from §3 with any provider-side fixes you made.
4. Test summary line and any failures in full.
5. Decisions not covered here, and anything unfinished with the reason.
