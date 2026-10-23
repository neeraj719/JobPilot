# Local AI upgrade — best free, low-resource parsing and recommendations

You are "local-ai-upgrade", a senior ML/backend engineer on JobPilot AI (FastAPI + SQLAlchemy 2 +
PostgreSQL, React frontend, repo `C:\Users\Neera\projects\job application`). Read
`backend/app/modules/ai/{tasks,factory,provider}.py`, `backend/app/modules/ai/providers/ollama.py`,
`backend/app/modules/ai/resume_parser.py`, `backend/app/modules/resumes/{service,recommendations,apply}.py`
and `backend/app/modules/resumes/extract*` (or wherever `try_extract_text` lives) first. Do not commit.

## Machine (measured, do not re-measure the hardware)

Windows 11, i5-12450H (12 threads), 15.6 GB RAM with typically 4–6 GB free, NVIDIA RTX 3050
Laptop **4 GB VRAM**, Ollama 0.35.1 running on :11434 with `qwen2.5:3b-instruct` (default) and
`qwen2.5:7b-instruct` pulled. Everything must stay local and free, and must load light.

## Current design you must keep

- Resume parsing: the deterministic rule-based parser (`resume_parser.parse_resume_text`) is the
  base; an LLM may only fill empty fields, verified against the text
  (`tasks.merge_parsed_resume`). Never let a model overwrite name/contact/experience.
- Recommendations are deterministic (`recommendations.py`); the LLM only drafts copyable text for
  `WEAK_SUMMARY` and `EXPERIENCE_BULLETS` (`COPYABLE_CATEGORIES`), and `looks_like_advice`,
  `invented_numbers`, `copies_experience` and the bullet checks in `apply.py` gate everything.
- Target jobs follow the resume's `target_role` or the preferred titles (`load_target_jobs`,
  `role_matches`).
- Never fabricate candidate facts.

## Research already done (use it, verify tags exist when pulling)

- Small instruct models that fit 4 GB VRAM at Q4: `qwen3:4b-instruct-2507` (non-thinking; reported
  ~99% JSON validity with constrained output), `phi4-mini` (~3.2 GB), `gemma3:4b`. Thinking-mode
  models are bad at constrained JSON: use non-thinking variants only.
- Embeddings: `embeddinggemma` (308M, <200 MB RAM quantised, top sub-500M model on MTEB at launch,
  Ollama ≥ 0.11.10). `nomic-embed-text` is the fallback.
- PDF text: `pymupdf4llm` is light and layout-aware but **AGPL/GPL** — do not add it. Prefer a
  permissive option (`pypdfium2`, Apache/BSD) only if it measurably beats the current extractor.
- GLiNER2 (205M, CPU) is an option for entity extraction but pulls in PyTorch; do **not** add it in
  this step — mention it in the report only if your measurements show the rule parser failing.

## Scope

### 1. Model bake-off (measure, then pick)

Write `backend/scripts/bench_local_llm.py` that, for each candidate model, runs:
- `parse_resume` through `OllamaProvider.complete_json` with the ParsedResume schema on three
  inputs: `tests/helpers/documents.SAMPLE_RESUME_TEXT`, a second synthetic resume you write
  (two jobs, a projects section, a multi-line skills block), and the text of the owner's current
  default resume read from the live DB **read-only** (`media.resumes.text_content` for
  `neerajmishra1085@gmail.com`; it never leaves the machine);
- `classify_email` on five short emails you write (interview, rejection, received, assessment,
  recruiter);
- the bullet rewrite used by `apply.strengthen_bullet` on the owner's six bullets, recording how many
  rewrites pass `bullet_problem`.
Record per model: JSON validity rate, field accuracy against the rule-based parse for name, email,
phone, number of experience entries and skills overlap, email accuracy, bullet pass rate, median
latency, tokens/s, and whether it ran fully on GPU (`ollama ps`). Unload between models
(`keep_alive: 0`). Pull only what you test; afterwards `ollama rm` every model you did not choose,
keeping the chosen default plus `qwen2.5:3b-instruct` as a fallback and the embedding model.
Choose the default by: validity first, then field accuracy, then bullet pass rate, then speed.
Set `LLM_MODEL` in `.env` (touch no other line) and the provider default if it changed.

### 2. Local embeddings for better recommendations

- `backend/app/modules/ai/embeddings.py`: `embed(texts: list[str]) -> list[list[float]] | None` via
  Ollama `POST /api/embed` with `EMBEDDING_MODEL` (setting in `app/core/config.py`, default
  `embeddinggemma`, plus `EMBEDDINGS_ENABLED: bool = True`), batched, 30 s timeout, an in-process LRU
  cache keyed by sha256 of model+text (cap 5,000 vectors), `cosine()` helper, and `None` on any
  failure so callers fall back to today's deterministic behaviour. Pull the model.
- Use it in `recommendations.load_target_jobs` only:
  - rank the role-matched candidates (user's own and pool) by cosine similarity between the resume
    text and `title + required skills + first 600 chars of description`, and take the top N;
  - when the token rule `role_matches` yields fewer than `MIN_TARGET_JOBS`, accept pool jobs whose
    **title** embedding has cosine ≥ a threshold you calibrate (start 0.75) to any target role,
    still excluding titles the token rule proves are a different role (e.g. Frontend vs Backend).
    Report the threshold you chose and the titles it admitted/rejected for the owner's role
    "Python Developer" and for "Full Stack Engineer".
- Keep `jobs_fingerprint`/cache keys correct when embeddings change the selection.
- Do not change `matching/scoring.py` in this step.

### 3. Speed of the analysis

The polish call currently sends up to 12 recommendations to the LLM and takes 6–10 s on every
analysis. Send only the `COPYABLE_CATEGORIES` recommendations (skip the call when there are none),
and make sure the Ollama request uses the configured `keep_alive`. Report the before/after time of
`GET /resumes/{id}/recommendations?refresh=true` for the owner's resume.

### 4. Text extraction check

Extract the owner's stored DOCX (`media.resumes.file_path`, read-only) with the current extractor
and find why the first bullet reads `Leading the project� guiding` (likely a dash in a symbol font,
a soft hyphen or a tab). Fix the extractor so dashes/bullets/smart quotes normalise to plain text
(e.g. `—`/`–` → `-`, `•` → bullet marker, non-breaking spaces → space, U+FFFD never emitted).
Add a test with a DOCX containing those characters. Run the same check on a generated PDF.

### 5. Tests

- Unit tests for `embeddings.py` with httpx mocked (success, batching, cache hit, failure → None).
- `load_target_jobs` tests: ranking by similarity with a fake `embed`, the semantic admission
  threshold, the different-role exclusion, and the no-embeddings fallback.
- Extractor normalisation test.
- Run with `TEST_DATABASE_URL=postgresql+psycopg://jobpilot:jobpilot@localhost:5432/jobpilot_test_ai_upgrade LLM_PROVIDER=mock EMBEDDINGS_ENABLED=false`
  (plus the tests that need it enabled with mocks): your new tests, `tests/test_ai.py`,
  `tests/test_ai_ollama.py`, `tests/test_resume_recommendations.py`, `tests/test_resume_apply.py`,
  `tests/test_resumes.py`. Not the full suite.

## Constraints

- Free, local, permissive licences only. No API keys. No resume text sent off the machine.
- Memory: never keep two chat models loaded; the embedding model may stay loaded alongside one.
- Do not touch auth, adapters, companies, jobs, the frontend, the sidebar/top bar, or the database
  schema. No migrations.
- The owner uses the app on :8000/:5173; do not restart those. Use port 8095 if you need a server.
- Do not commit, stash, reset or checkout. Do not use a bare `python` command (it hangs here);
  use `backend/.venv/Scripts/python.exe`. Write multi-line Python to a file and run it rather than
  piping heredocs (backslash escapes get mangled in this shell), and check edited files for control
  characters.

## Report

1. The bake-off table (model, size, GPU fit, JSON validity, field accuracy, email accuracy, bullet
   pass rate, median latency, tok/s) and the model you chose, with why.
2. Models removed and models kept, with disk sizes.
3. Embedding results: threshold, titles admitted/rejected for both roles, and the owner's new
   target-job list for "Python Developer".
4. Analysis time before/after.
5. The cause and fix of the `�` character.
6. Files changed; test summary line and failures in full.
7. Anything unfinished, with the reason.
