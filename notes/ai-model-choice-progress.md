# ai-model-choice — progress

Brief: `notes/ai-model-choice-prompt.md`. Owner: ai-model-choice agent. Do not commit.

## Checklist
- ✅ Backend contract: `ai.context.AiUserSlot.target_override` (+ `set_target_override`, `current_target_override`,
  `ai_user(..., target_override=)`), `routing.resolve_from(..., override=)` → `source="per_run"`,
  `runtime.resolve_current` picks the override (only for the slot's user), usage rows carry `source`.
- ✅ Migration `e6f8a0b2c4d7` (down `f6b8d0c2e4a7`): `master.ai_provider_settings.model_prompt_mode`
  (String(10), NOT NULL, default `ask`), `transaction.ai_usage_events.source` (String(20), NULL).
  Upgrade/downgrade/upgrade + `alembic check` clean on a scratch DB; applied to live `jobpilot`
  (`alembic upgrade e6f8a0b2c4d7`). Second head `d2e4f6a8b0c1` (linkedin-connect) is deliberate —
  `tests/test_migrations.py` (`upgrade head`) fails until integration merges the heads.
- ✅ Endpoints: `GET /ai/choices?task=`, `PATCH /ai/settings {model_prompt_mode?, remember?}`,
  `PUT /ai/settings` accepts optional `model_prompt_mode` (None = keep). `ai: {provider, model}` on
  ats jd/parse, jd/fetch, analyses, auto-optimize, polish (optional body), snapshot, refresh
  (optional body `{use_ai, ai}`), tailor; multipart `ai_provider`/`ai_model` on jd/upload,
  snapshot/upload, resume upload; resumes import/text, reparse (optional body), ai/rewrite-bullet,
  ai/responsibility-to-achievement, ai/improve-text, ai/draft-summary (responses gain
  `ai_provider`/`ai_model`). ATS background polish receives the override.
- ✅ Backend tests `tests/test_ai_choice.py` (21 pass). Final full suite (junit): tests=1405,
  failures=0, errors=0, skipped=3, exit 0. Alembic heads: `e6f8a0b2c4d7` (mine) + `d2e4f6a8b0c1`
  (linkedin-connect), deliberate; integration merges them.
- ✅ Frontend: `features/ai-providers/useAiChoice.ts` (query, store, `runWithModel`),
  `components/AiModelPickerDialog.tsx` (lazy, mounted by `AiModelPickerHost` in `App.tsx`),
  `AiRunButton.tsx` (split button + popover + helper text), `AiModelChip.tsx`, `ModelPromptCard.tsx`.
- ✅ Wiring: Analyse, JD preview/upload/fetch (when "Refine with AI" is on), Polish / Retry polish,
  Auto-optimize, Tailor, editor Draft summary / Improve wording / bullet Rewrite·Achievement·Improve
  (+ "Rewrite once with…" submenu), Re-run extraction (ParsedDataPanel), Create Resume paste import.
- ✅ Settings card + dashboard note. `tsc` clean, build main chunk 350.00 kB.
- ✅ Verification (stub :8102, backend :8101 on live DB, Vite :5231): Playwright proofs all PASS —
  one model → no chevron/no dialog; two → dialog on Analyse, Esc cancels, stub chosen → :8102 logs
  chat/completions model=stub-json-1 + analysis chip; Remember → workflow_models.generation;
  chevron one-off qwen → no dialog, stub untouched, routing unchanged; Don't ask again → mode
  default + undo toast, no dialog after; settings card + dashboard note. 24 screenshots in
  `notes/screenshots/ai-model-choice/`. Contrast checker 0 failures. Build main chunk 350.15 kB.
- ✅ Cleanup: choice.check@jobpilot.ai soft-deleted (with its resume + credential), servers stopped.
- Docs: `docs/CONTRACTS.md` §16 "Per-run model choice" + §18 note, `docs/DATABASE.md` columns.

## Decisions
- "Remember" = `PATCH /ai/settings {remember: {workflow, provider, model}}` (validated like PUT);
  PUT stays a full replacement, so a partial PATCH avoids clobbering the routing from the picker.
- A hosted per-run choice needs the existing data-sharing acknowledgement (422
  `data_residency_ack_required`); hosted candidates without it are listed `available:false`.
- `POST /resumes/build` makes no model call, so it takes no `ai` field.
- Mock ("Built-in rules") is a candidate only when it is the routed default.
- Ollama embedding models are never offered (the provider listing already drops `*embed*`).
- (Designer fix) The ATS suggestion polish has its own task `polish_suggestions` → workflow `analysis`
  (`ats.llm.TASK_POLISH`, threaded through `run_analysis` / `auto_optimize` / `start_polish` /
  `polish_analysis`); Analyse / Polish / Auto-optimize use it, so the badge reads "Default for ATS
  analysis" and Remember writes `analysis`. Tailor keeps `tailor_resume` → `generation` (targets.tailor
  passes `polish_task=TASK_TAILOR`). Create Resume upload goes through the picker;
  `features/ai-providers/useAiChoiceForUpload.ts` is exported for the resume-upload sheet.
- Picker settings writes use `patchAiSettings` (not a mutation hook): the dialog unmounts the moment
  the user decides, and react-query drops `mutate()` callbacks of unmounted components.
- Not routed through the picker (no model call from the UI path): job-target snapshot paste/upload
  and refresh (no "use AI" switch on that page; API accepts `ai`), `POST /resumes/build`,
  Create Resume upload / LinkedIn import (shared page, minimal edit only covered paste), old
  `/resume` page (`pages/Resume.tsx`) re-parse, ATS apply/undo (re-run analysis → polish uses routing).

## Blockers
- none
