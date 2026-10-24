# ai-model-choice — ask which configured AI model to use before each AI run

You are **ai-model-choice**, a senior full-stack engineer (FastAPI + SQLAlchemy 2 + Alembic;
React 18 + TS + Tailwind + Radix + react-query + zustand) on JobPilot AI
(`C:\Users\Neera\projects\job application`, branch `develop`, Windows). Read, binding:
`notes/resume-studio-plan.md` §1, §5, §6, §7 (stack, DB rules, security, verification protocol,
shell quirks), `docs/CONTRACTS.md` §18 (AI providers), `docs/DESIGN.md` (theme v2), the AI runtime
(`backend/app/modules/ai/{runtime,routing,context,settings_service,settings_schemas,registry,usage}.py`,
`app/models/ai_settings.py`, `app/modules/ai/router.py`) and the frontend
`src/features/ai-providers/**` + `pages/resume/AiModelSettings.tsx`. Nobody else edits the tree.
Do not commit. Progress file `notes/ai-model-choice-progress.md`.

## What the owner wants

"If we configured more AI models, then while processing it should also ask which one should I use
to process this." Today the runtime silently resolves a model per task → workflow
(`routing.resolve_from`: workflow override → user default → server default, plus fallback). When
a user has **two or more usable models**, every AI action must let them choose the model for
*this run* — quickly, without leaving the page — and optionally remember the choice. One usable
model → never ask.

## Design (binding; refine details, keep the contract)

### Backend
1. **Candidates endpoint** `GET /api/v1/ai/choices?task=<task>` → `{ task, workflow, mode,
   default: ChoiceId, candidates: Choice[] }` where `Choice = { id: "<provider>:<model>", provider,
   provider_name, model, label, source: "workflow_default"|"user_default"|"server_default"|
   "credential"|"local", hosted, privacy_note, cost_hint ("free, local" | "≈ $x per 1k tokens" from
   the registry prices when known | "unknown"), available: bool, unavailable_reason?, last_used_at? }`.
   Candidates = the resolved default for the task (first, marked), then one entry per provider the
   user has a working credential for (model = the user's model for that workflow if set, else the
   provider's default; include the user's recently used models for that provider from
   `transaction.ai_usage`, max 3 per provider), Ollama local models when the server is reachable
   (reuse `/providers/ollama/models`), and the server default when allowed. Hidden: providers not
   allowed by `AI_ALLOW_HOSTED_PROVIDERS`, credentials with status error (listed as
   `available:false` with the reason). Cache per user for 60 s (invalidate on settings/credential
   change via `evict_clients`-style hook).
2. **Per-run override**: every AI-triggering endpoint accepts an optional `ai: { provider, model }`
   (reuse `settings_schemas.WorkflowTarget`) in its JSON body (multipart endpoints: form field
   `ai_provider` / `ai_model`). Endpoints in scope: `ats` — `POST /jd/parse`, `/jd/upload`,
   `/jd/fetch`, `POST /analyses`, `/analyses/{id}/polish`, `/analyses/{id}/auto-optimize`,
   `/targets/{id}/tailor`, `/targets/{id}/snapshot[/upload]`, `/targets/{id}/refresh`;
   `resumes` — `POST /resumes/build` (generate from profile/text when it calls the LLM),
   `/{id}/reparse`, the writing endpoints (rewrite bullet, draft summary, improve grammar — find
   them in `resumes/router.py` and `resume-studio` features), and the generic `ai/tasks` entry
   points if the UI calls them. Validate the override in one dependency
   (`ai/choice.py::validate_choice(db, user, target) -> Target`): provider known and allowed,
   credential present when `requires_key` (409 `ai_credential_missing`), hosted allowed
   (403 `ai_hosted_disabled`), model non-empty and, when the provider lists models, one of them or
   the user's recently used (422 `ai_model_unknown`). Carry the validated target through the
   existing AI context (`context.AiUserSlot` gets `target_override: Target | None`; `ai_user()` /
   `request_ai_context()` keep working) so **no call-site signature changes** are needed:
   `runtime.resolve_current(task)` returns the override with `source="per_run"` when set; fallback
   rules still apply after the override fails. `record_usage` stores `source="per_run"` and the
   chosen provider/model. Limits (`check_limits`) apply to the chosen provider.
3. **Settings**: `AiProviderSettings.model_prompt_mode` (`String(10)`, `ask`|`default`, default
   `ask`), exposed in `SettingsRead`/`SettingsWrite` as `model_prompt_mode`; Alembic migration with
   the next id after the current head (check `alembic heads`; single head, downgrade included,
   update `tests/test_migrations.py` / `test_db_conventions.py` only if they pin columns);
   `docs/DATABASE.md` + `docs/CONTRACTS.md` §18 updated. `PUT /ai/settings` also accepts a
   `remember: { workflow, provider, model }` convenience, or the frontend writes
   `workflow_models[workflow]` directly — pick one and document it.
4. Tests (pytest, own `TEST_DATABASE_URL=…/jobpilot_test_aichoice`, `LLM_PROVIDER=mock`):
   choices with 0/1/2+ usable models (one usable → `candidates.length == 1`), each validation error
   code, override reaches the runtime (`runtime.last_call()` shows the chosen provider/model) on
   at least `POST /ats/analyses` and `POST /jd/parse`, usage row `source="per_run"`, mode
   persisted, override ignored with 422 when `model_prompt_mode` is irrelevant? (no: the override
   is always honoured when valid, the mode only controls whether the UI asks). Full suite green
   (`--junitxml`, exit code).

### Frontend
5. **Hook + dialog**: `features/ai-providers/useAiChoice.ts` — `useAiChoice(task)` loads
   `/ai/choices` (react-query, `qk.aiProviders.choices(task)`, staleTime 60 s) and exposes
   `runWithModel(fn: (ai?: WorkflowTarget) => Promise<T>)`: if `mode === 'ask'` and ≥ 2 available
   candidates → opens `AiModelPickerDialog` and resolves with the chosen target; otherwise runs
   immediately with the default (no dialog). The dialog (v2 glass dialog, 520 px, mobile bottom
   sheet): title "Which model should process this?", one-line context (task label + what is sent,
   e.g. "Your resume and the job description"), a `radiogroup` of candidate cards (provider chip +
   model name, badges: "Default for ATS analysis", "Local · private", "Hosted", cost hint,
   "Last used 2 h ago"), unavailable ones disabled with the reason, "Remember for <workflow>"
   checkbox (writes `workflow_models`), a quiet "Don't ask again — always use my default" link
   (sets `model_prompt_mode = 'default'` with an undo toast), primary gradient "Run with <model>",
   Enter confirms, Esc cancels (the action is not run). Keyboard and screen-reader complete.
6. **Wire every AI action** through `runWithModel`: ATS Optimizer "Analyse", JD paste/upload/fetch
   parse, "Polish suggestions", "Auto-optimize", Job target "Tailor resume", snapshot/refresh,
   Create Resume generate-from-profile / import-from-text when it calls the LLM, editor "Rewrite
   with AI" / "Draft summary" / "Improve grammar", resume "Re-parse". Each such button becomes a
   **split button**: main part runs (asking if configured), the chevron opens a compact popover
   listing the same candidates for a one-off pick without the dialog; the button's helper text
   shows the model in effect ("qwen2.5:3b · local"). The resulting analysis/version shows which
   model produced it (already stored in usage / analysis rows — surface it as a small chip).
7. **Settings**: AI Model Settings page gets a "Before each AI run" card: radio "Ask me which model
   to use (when I have more than one)" / "Always use my routing below"; the Resume Dashboard AI
   model card shows the mode. Settings › Workspace untouched.
8. Skeletons for the candidates list (no spinner), error state when `/ai/choices` fails (fall back
   to running with the default and a toast), reduced motion respected, contrast checker 0
   failures with any new pairs.

## Verify
Private servers: backend `.venv/Scripts/python.exe -m uvicorn app.main:app --port 8101` with
`REDIS_URL=redis://localhost:6379/16` and `AUTH_RATE_LIMIT_PER_MINUTE=1000`, Vite `--port 5231`,
both `run_in_background: true`; Playwright scripts via the Write tool under
`scratchpad/ai-model-choice/`, explicit timeouts ≤ 300000 ms. Throwaway user
`choice.check@jobpilot.ai` with one resume from text. To get **two usable models** without real
keys: Ollama (local, reachable on this machine with `qwen2.5:3b-instruct`) plus an
OpenAI-compatible credential pointing at a tiny stub server you run on :8102 (implements
`/v1/models` and `/v1/chat/completions` returning valid JSON for the schema) — the registry's
openai-compatible provider accepts a base URL without a key. Prove: with one model → no dialog;
with two → dialog appears on "Analyse", choosing the stub routes the call to :8102 (stub logs
it), "Remember" updates routing, "Don't ask again" stops the dialog, the split-button popover
works, the chevron pick is one-off, the analysis shows the model chip. Screenshots light + dark,
1440 + 390: `notes/screenshots/ai-model-choice/{dialog,split-button,popover,settings-card,
analysis-chip,skeleton}-*.png`. `npm run build` green (main chunk ≤ 352 kB), `tsc` clean, pytest
full suite green, contrast 0. Soft-delete the throwaway user, stop servers and the stub.

## Report
1. API contract (choices response, override field, error codes, settings field) in ten lines.
2. Migration id, tables/columns touched, docs updated. 3. Files changed, frontend components added.
4. Test counts (backend, with junit numbers) and the Playwright proof list with screenshot paths.
5. Anything unfinished, and any AI call site you could not route through the picker and why.
