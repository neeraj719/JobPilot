# resume-upload — progress

Brief: `notes/resume-upload-prompt.md`. No migration (none needed: `media.resumes` already has the file
columns and `media.resume_versions.file_path` keeps the previous file on replace).
Ports: backend 8105 (REDIS db 18), Vite 5235; test DB `jobpilot_test_upload`; user `upload.check@jobpilot.ai`.

## Checklist
- ✅ backend `app/modules/resumes/router_upload.py` (+2 lines in `main.py`) + `tests/test_resume_upload.py` (16 pass)
- ✅ `features/resume-upload/` — api (XHR progress), ResumeDropzone, AfterUploadChoice, UploadProgressBar, UploadResumeSheet (+useUploadSheet), PageFileDrop, OriginalFileBadge, UploadedResumeView (+EditCopyButton, ReplaceFileDialog); tsc clean
- ✅ dashboard entry points (`ResumeDashboard.tsx`): header "Upload resume" (outline), start card two buttons, quick action → `/resume/new?mode=upload`, page drop overlay, Original-file badge in Recently edited
- ✅ My Resumes: Upload button → sheet, drop overlay, empty state "Upload my resume", badge on UPLOADED cards (wrapper, card untouched), detail → `UploadedResumeView` + header (Check / Tailor / History / Edit a copy)
- ✅ Create Resume: first card "Upload my resume" + dropzone + After-upload choice + progress; keep-original ends on `/resume/my/:id`, template card hidden then (file is the original)
- ✅ verification: own tests 16/16; full suite run 1 = 1394 tests, 3 failures (all ai-model-choice in-progress:
  `ai_provider/ai_model` fields in writing-help responses); run 2 = 1405 tests, 0 failures, 3 skipped, exit 0; `tsc` clean; `npm run build` green,
  main chunk 350.15 kB (≤ 352), feature code in the lazy resume `pages-*` chunk; contrast `failures: 0`;
  Playwright 24 checks (first 1 + flows 22 + shots 1) on :8105/:5235, 49 screenshots in `notes/screenshots/resume-upload/`
- ✅ cleanup: upload.check@jobpilot.ai + its resumes soft-deleted (is_active=false, deleted_at set); :8105/:5235 stopped

## Decisions
- Inline preview: `GET /resumes/{id}/file?disposition=inline|attachment` (new path in router_upload — the existing
  `/download` lives in router.py, owned by ai-model-choice, and forces attachment). The frontend fetches it with the
  bearer token and shows a blob: URL in an `<iframe>` (an iframe cannot send the Authorization header).
- "Edit a copy": `POST /resumes/{id}/edit-copy` → a CREATED resume (`source_resume_id` = original). The existing
  `/duplicate` keeps `kind` (an UPLOADED copy sharing the file), which is not what the brief asks for.
- Replace file: `POST /resumes/{id}/file` → new version, `change_source=USER`; the old version rows keep their
  `file_path`, the old file stays on disk.

## Verification notes
- Browser runs used `vite build --outDir <scratchpad>/ru_dist` + `vite preview :5235`, not the dev server: the other
  agents' edits triggered HMR full reloads in the dev server mid-upload. Backend :8105 ran with `LLM_PROVIDER=mock`
  and `RATE_LIMIT_PER_MINUTE=3000` (the per-IP limiter 429'd the rapid test runs). One earlier run with Ollama:
  upload + parse took ~96 s (qwen output cut off twice, deterministic fallback) — the sheet shows the "reading" phase.
- Playwright script: `<scratchpad>/ru_browser.py first|flows|shots`; setup `ru_setup.py`; cleanup `ru_cleanup.py`.
