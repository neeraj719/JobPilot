# resume-upload — "Upload my original resume" as a first-class action, kept as the original

You are **resume-upload**, a senior full-stack engineer / product designer (FastAPI + SQLAlchemy 2;
React 18 + TS + Tailwind + Radix + react-query) on JobPilot AI
(`C:\Users\Neera\projects\job application`, branch `develop`, Windows). Read, binding:
`notes/resume-studio-plan.md` §1, §5, §6, §7 (incl. the **shared-file protocol**), `docs/DESIGN.md`
(theme v2; skeletons, not spinners), `docs/CONTRACTS.md` §16, `backend/app/modules/resumes/
{router,service,schemas}.py`, `app/models/resume.py` (`kind` UPLOADED|CREATED|TAILORED, nullable
file columns, `has_file`), `frontend/src/features/resume/api.ts` (`useUploadResume` → `POST
/resumes`, `MAX_RESUME_BYTES`), `pages/resume/{CreateResume,MyResumes,ResumeDashboard,ResumeEditor}.tsx`,
`features/resume-studio/components/badges.tsx`. Do not commit. Progress file
`notes/resume-upload-progress.md`.

## Concurrency (binding)
Two other agents work in this tree now. **ai-model-choice** owns `app/modules/ai/**`,
`app/modules/resumes/router.py`, `app/modules/ats/**`, `frontend/src/features/ai-providers/**`,
`features/ats/**`, `features/resume-studio/**`, `pages/resume/AiModelSettings.tsx`.
**linkedin-connect** owns `app/modules/integrations/linkedin*`, `app/models/linkedin.py`,
`app/modules/resumes/router_linkedin.py`, `features/linkedin/**`, and adds one "Connect LinkedIn"
card to `CreateResume.tsx` late. Both add Alembic migrations off `f6b8d0c2e4a7`; **you add no
migration** (no schema change is needed — if you believe one is, stop and write it in the report
instead). You own: NEW `frontend/src/features/resume-upload/**`, NEW
`backend/app/modules/resumes/router_upload.py` (if any new endpoint is needed; include it with one
line where routers are registered), `pages/resume/ResumeDashboard.tsx`, `pages/resume/MyResumes.tsx`,
and the upload-related parts of `pages/resume/CreateResume.tsx`. Shared files (`CreateResume.tsx`,
`lib/queryClient.ts`, `types/api.ts`, `features/resume/api.ts`): re-read immediately before each
edit, keep edits minimal and local, never reformat. If the editor (`ResumeEditor.tsx`,
`features/resume-studio/**`) needs a change for uploaded resumes, put the component in your
folder and ask for a one-line mount in the report rather than editing their files. Ports: backend
`8105` (`REDIS_URL=redis://localhost:6379/18`, `AUTH_RATE_LIMIT_PER_MINUTE=1000`), Vite `5235`;
test DB `jobpilot_test_upload`.

## What the owner said
"In the resume we don't have the option to just upload the original resume — add that in the best
place." Today upload exists only as the second card inside Create Resume ("Upload PDF or DOCX — we
read your existing resume; you review what was extracted") and always drops the user into the
editor. The owner wants the plain case: *upload my real resume file, keep it as the original, and
use it* — obvious from the dashboard and the resume list, without a build/review detour.

## Deliver
1. **Dashboard** (`ResumeDashboard.tsx`): header gets a second action **"Upload resume"** (outline,
   next to the gradient "New resume"); the first-visit start card offers two equal buttons "Upload
   my resume" / "Build from my profile"; the quick action "Import a resume" becomes **"Upload my
   resume · PDF or DOCX, kept as the original"** and deep-links to `/resume/new?mode=upload`.
   Drag-and-drop anywhere on the dashboard and on My Resumes opens the upload sheet with the file
   pre-attached (full-page drop overlay with the dashed brand border, Esc cancels).
2. **My Resumes**: the existing "Upload" button opens an **Upload sheet** (Radix Sheet/Dialog from
   `features/resume-upload/UploadResumeSheet.tsx`, reused by the dashboard and the drop overlay):
   dropzone (PDF/DOCX, size limit from `MAX_RESUME_BYTES`, clear errors for type/size/encrypted
   PDF), name (prefilled from the file name), target role (optional), "Set as default" (on by
   default when the user has no default), and the decision **"After upload"**: ◉ *Keep as my
   original — use this file as-is* (default) / ○ *Open in the editor to review what we extracted*.
   Upload progress bar (real `XMLHttpRequest`/fetch progress, not a spinner), then success state
   with the parse result in one line ("We read 4 roles, 2 degrees, 18 skills" or "We could not
   read everything — you can still use the file") and buttons "View", "Check against a job",
   "Open in editor". Empty state on My Resumes also gets an "Upload my resume" primary.
3. **Create Resume**: "Upload PDF or DOCX" becomes the **first** card, titled **"Upload my
   resume"**, description "Keep your original file as-is. We also read it so scoring and tailoring
   work." Its panel reuses the same dropzone + "After upload" choice; with *Keep as original* the
   flow ends on the new resume's page (below), not in the editor. Keep the other cards and the
   `MODES` shape (linkedin-connect inserts a card later).
4. **Uploaded resume page** (`/resume/my/:id` for `kind === 'UPLOADED'`, inside `MyResumes.tsx`
   detail or a new `features/resume-upload/UploadedResumeView.tsx` mounted from it): the
   **original file preview** (PDF inline via an `<iframe>`/`<object>` on `GET /resumes/{id}/download`
   with `inline` disposition — add a `?disposition=inline` option in `router_upload.py` if the
   existing endpoint forces attachment; DOCX: show the extracted text with a "Download DOCX"
   button and a note that browsers cannot preview DOCX), file facts (name, size, uploaded date,
   pages when known), "Download original", "Replace file" (new upload → new version with
   `change_source=USER`, the old file kept in the version row if the model supports it; otherwise
   document the limitation), "Set as default", "Check against a job", "Tailor for a company", and
   **"Edit a copy in the editor"** which duplicates into a CREATED resume (reuse
   `useDuplicateResume`) so the original is never modified. Badge "Original file" next to
   "Uploaded" in lists (`badges.tsx` is not yours — add your badge in your folder and render it
   from the pages you own).
5. **Backend** (only if needed, in `router_upload.py`): inline download disposition; `GET
   /resumes/{id}/file-info` (name, size, content type, page count via existing extraction);
   `POST /resumes/{id}/file` replace-file as a new version. Reuse `service.*`; no model changes.
   Security: file type sniffing (not just extension), size limit, same ownership checks as the
   existing download; no path from user input.
6. **Everything** behind skeletons, keyboard accessible (dropzone focusable, Enter/Space opens the
   picker), reduced motion respected, mobile 390 layout (sheet becomes bottom sheet), theme v2
   tokens only, contrast 0 failures.
7. **Tests**: pytest (own test DB) for any new endpoint (inline disposition headers, file-info,
   replace creates a version, sniffing rejects a renamed .exe, ownership 404); full suite green
   (`--junitxml` + exit code). Playwright on your private servers with user
   `upload.check@jobpilot.ai`: upload from the dashboard button (keep as original) → lands on the
   uploaded resume page with the PDF preview; drag-and-drop on My Resumes; upload with "open in
   editor" → editor; Create Resume first card; DOCX path; oversize and wrong-type errors; "Edit a
   copy" creates a CREATED resume and leaves the original untouched; default toggle. Screenshots
   light + dark, 1440 + 390 in `notes/screenshots/resume-upload/`. `npm run build` green (main
   chunk ≤ 352 kB; your code in the resume module chunk or lazy), `tsc` clean. Soft-delete the
   throwaway user, stop servers.

## Report
1. Where "upload my original resume" now lives (the four entry points) in five lines.
2. Backend endpoints added (if any) and why; confirmation of no migration.
3. Files added/changed; the exact minimal edits made to shared files.
4. Test counts, Playwright proof list with screenshot paths.
5. Anything unfinished; any one-line mounts you need from the other agents' files.
