# resume-builder — progress

Stream: resume-builder (plan `notes/resume-studio-plan.md`, scope `notes/resume-builder-prompt.md`).
Test DB `jobpilot_test_builder`; ports API 8091 / Vite 5201. No commits.

## Checklist

- ✅ Backend: ParsedResume additive fields (headline, location, achievements, languages, section_order; entry location/url) + `RESUME_SECTION_KEYS`
- ✅ Backend: `resumes/templates.py` (classic / modern / compact, data definitions) + `GET /resumes/templates`
- ✅ Backend: `resumes/render.py` (DOCX via python-docx, PDF via reportlab) + `GET /{id}/export`, `/download` renders DOCX for file-less resumes
- ✅ Backend: `resumes/importers.py` (prefill, import text, import LinkedIn ZIP/CSV, zip-slip + size guards) + `POST /build`
- ✅ Backend: drafts (GET/PUT/DELETE), duplicate, archive/unarchive, PATCH template, parsed-data `note`/`change_source`
- ✅ Backend: `resumes/diff.py` (version diff, resume diff), restore, `GET /history`, `GET /summary`
- ✅ Backend: AI writing help (`resumes/writing.py` + `ai/tasks.py` / `ai/prompts.py` append-only), routed via `resumes/llm.py`
- ✅ Backend tests `tests/test_resume_builder.py` (34 passing)
- ✅ Frontend: `features/resume-studio` (api, types, schema, layout mirror, preview, template picker, diff, badges, editor parts)
- ✅ Frontend: My Resumes (list + detail), Create Resume, Editor, Version History
- ✅ `npm run build`
- 🔄 Browser check + screenshots

## Decisions

- New dependencies: `reportlab==4.4.4` (PDF export, lazy import); npm `@dnd-kit/core@6.3.1`, `@dnd-kit/sortable@10.0.0`, `@dnd-kit/utilities@3.2.2`.
- No migration (the scaffold's columns were enough).
- `extraction.py`: DOCX list paragraphs keep a "- " marker; PDF 0x7F (WinAnsi bullet) reads as a bullet — makes exports (and other generators' files) parse correctly.
- Archived resumes: never default, excluded from `get_default_resume` / list; `matching/service.py::_default_resume` has its own query (integration).
- "AI versions to review" = resumes whose current version has change_source AI (no review flag in the schema).
- Editor saves with `change_source=AI` when at least one AI-sourced suggestion was applied since the last save (note says how many).
- Section "remove" hides the section via `section_order`; content is kept.

## Blockers / notes

- Earlier: 3 polish-test failures in `tests/test_resume_recommendations.py` from the ai-providers runtime change; on the final run (178 tests incl. that file) everything passed.
