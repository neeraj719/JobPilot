# linkedin-connect — "Connect LinkedIn" in Create Resume: auto-fill from the official API, sync options

You are **linkedin-connect**, a senior full-stack engineer (FastAPI + SQLAlchemy 2 + Alembic;
React 18 + TS + Tailwind + Radix + react-query) on JobPilot AI
(`C:\Users\Neera\projects\job application`, branch `develop`, Windows). Read, binding:
`notes/resume-studio-plan.md` §1, §5, §6, §7 (stack, DB rules, security, verification, shell
quirks, **shared-file protocol**), `docs/CONTRACTS.md`, `docs/DESIGN.md` (theme v2), the existing
Gmail OAuth flow (`backend/app/modules/integrations/{gmail_oauth,service,router}.py`,
`app/models/email.py::EmailIntegration` — token encryption, state handling, revoke), the LinkedIn
export importer (`app/modules/resumes/importers.py::linkedin_members/parse_linkedin/import_linkedin`),
`app/models/profile.py` (UserProfile = master profile), `frontend/src/pages/resume/CreateResume.tsx`,
`frontend/src/pages/Settings.tsx` (Connected accounts section). Do not commit. Progress file
`notes/linkedin-connect-progress.md`.

## Concurrency (binding)
Another agent ("ai-model-choice") is working in the same tree right now. It owns
`app/modules/ai/**`, `app/modules/ats/router.py`, `app/modules/resumes/router.py`,
`frontend/src/features/ai-providers/**`, `pages/resume/AiModelSettings.tsx`,
`features/ats/**`, `features/resume-studio/**` and adds its own Alembic migration off the current
head `f6b8d0c2e4a7`. Therefore:
- Your migration id is **`d2e4f6a8b0c1`**, `down_revision = "f6b8d0c2e4a7"`. Two heads are
  expected and deliberate; do NOT merge them, do not run `alembic upgrade head` (ambiguous) —
  upgrade with your revision id (`alembic upgrade d2e4f6a8b0c1`) on your test DB and on the real
  `jobpilot` DB. `tests/test_migrations.py` may pin the table count: update it only if your run
  shows it needs +N for your tables, and say so in the report.
- Do not edit the files listed above. Your resume-creation endpoint lives in a NEW file
  `app/modules/resumes/router_linkedin.py` (or under integrations) and is included from
  `app/api/router.py` (or wherever routers are registered) with a one-line addition.
- Shared frontend files you may touch with ONE minimal, late edit each, re-reading the file
  immediately before editing: `pages/resume/CreateResume.tsx` (add the source card + branch, UI
  itself lives in `features/linkedin/**`), `lib/queryClient.ts` (append `qk.linkedin`),
  `types/api.ts` (append types), `pages/Settings.tsx` (mount your `LinkedInAccountCard` in the
  Connected accounts section). Everything else of yours is new files.

## What the owner wants
In Create Resume, besides "Import LinkedIn export", users can **connect their LinkedIn account**
and have their details auto-filled, with **sync options**.

## Reality you must design around (and explain honestly in the UI and docs)
- LinkedIn's generally available API ("Sign In with LinkedIn using OpenID Connect", scopes
  `openid profile email`) returns only: name, given/family name, picture, email, locale, `sub`.
  It does NOT return positions, education or skills.
- Full profile data via API exists only through **Member Data Portability (3rd party)**
  (`r_dma_portability_3rd_party`, Member Snapshot API) — for EU/EEA members, after LinkedIn
  approves the app. Support it behind a config flag; degrade gracefully when the scope is absent.
- Scraping the profile page or automating the browser against LinkedIn is forbidden by its
  terms and by this project's rules — do not do it, do not leave hooks for it.
- So the honest product: connect → instant auto-fill of identity basics + photo; full history via
  (a) the snapshot API when available, else (b) the existing export ZIP, now linked to the
  connection so "Sync" can tell the user when their export is older than X days.

## Backend
1. **Config** (`app/core/config.py`): `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`,
   `LINKEDIN_REDIRECT_URI` (default `http://localhost:8000/api/v1/integrations/linkedin/callback`),
   `LINKEDIN_AUTH_BASE` (default `https://www.linkedin.com/oauth/v2`), `LINKEDIN_API_BASE`
   (default `https://api.linkedin.com`), `LINKEDIN_DMA_ENABLED: bool = False`,
   `LINKEDIN_AUTO_SYNC_HOURS: int = 24`. Secrets never logged; `.env.example` updated.
2. **Model** `master.linkedin_connections` (`app/models/linkedin.py`, StandardColumnsMixin, soft
   delete, partial unique on `user_id` where not deleted): `user_id` FK, `subject` (LinkedIn
   `sub`), `name`, `email`, `picture_url`, `locale`, `scopes` (JSON list), `encrypted_access_token`,
   `encrypted_refresh_token` (nullable), `token_expires_at`, `status` (`connected|expired|revoked|
   error`), `last_error`, `last_synced_at`, `auto_sync` (bool, default true), `profile_snapshot`
   (JSON: normalised identity + optional DMA data), `snapshot_source` (`oidc|dma|export`),
   `export_imported_at` (nullable), `last_sync_diff` (JSON summary). Encryption via the same
   helper the Gmail integration uses. `docs/DATABASE.md` updated.
3. **OAuth** (`app/modules/integrations/linkedin_oauth.py`): authorization-code flow with
   `state` bound to the user (signed, 10-min expiry, single use — reuse the Gmail pattern) and
   PKCE (`S256`); scopes `openid profile email` plus `r_dma_portability_3rd_party` when
   `LINKEDIN_DMA_ENABLED`. Token exchange and `GET /v2/userinfo` via httpx with timeouts; ID-token
   `nonce` checked. Token refresh when a refresh token exists; otherwise mark `expired` when the
   60-day token lapses and prompt to reconnect.
4. **Endpoints** `/api/v1/integrations/linkedin` (require_module("resume")):
   `GET /` status (never returns tokens), `POST /connect` → `{authorization_url}`,
   `GET /callback` (public; validates state; on success redirects to
   `FRONTEND_URL/resume/new?source=linkedin&connected=1`, on failure `…&error=<code>`),
   `POST /sync` → refetch userinfo (+ snapshot domains PROFILE, POSITIONS, EDUCATION, SKILLS,
   CERTIFICATIONS, LANGUAGES when DMA scope granted), store snapshot, compute a **diff against
   UserProfile** (`{field, current, incoming, action: add|replace|same}` per field; lists diffed by
   stable keys) and return it — nothing written yet; `POST /apply` with the user's selected
   changes → writes to UserProfile (empty fields filled, non-empty only when ticked), audit row;
   `PATCH /` `{auto_sync}`; `DELETE /` → revoke at LinkedIn (best effort), wipe tokens, soft
   delete. `POST /api/v1/resumes/from-linkedin` (new file) → builds a `ParsedResume` from the
   snapshot (DMA → same normaliser as `parse_linkedin`; OIDC-only → identity + current
   UserProfile via the existing profile-based builder) and calls
   `service.create_resume_from_parsed(..., change_source=SYSTEM, note="Imported from LinkedIn")`;
   when an export ZIP is uploaded while connected, `import_linkedin` sets `export_imported_at`.
5. **Auto sync**: a job in the existing scheduler (`app/modules/automation` scheduler or the
   tasks runner the project already uses — find it) runs every `LINKEDIN_AUTO_SYNC_HOURS` for
   connections with `auto_sync` and a valid token, stores the snapshot + diff, and creates a
   notification "LinkedIn: 2 changes found — review" linking to `/resume/new?source=linkedin`.
   It never writes to the profile by itself. Skips users whose `resume` module is unavailable.
6. **Tests** (pytest, `TEST_DATABASE_URL=…/jobpilot_test_linkedin`, `LLM_PROVIDER=mock`): state
   tamper/expiry/reuse, PKCE verifier sent, callback happy path with a **fake LinkedIn server**
   (httpx `MockTransport` or `respx`) for token/userinfo/snapshot, tokens encrypted at rest (raw
   token never appears in the DB row), `GET /` masks everything, sync diff cases (empty profile,
   conflicting field, list merge), apply respects un-ticked conflicts, revoke wipes, DMA fixture
   → ParsedResume mapping (positions → experience with dates, education, skills dedup against
   user-added skills), from-linkedin creates a version with `change_source=SYSTEM`, scheduler
   skips disabled module. Full suite green (`--junitxml`, exit code).
7. **Docs**: `docs/INTEGRATIONS.md` (new or extend): how to create the LinkedIn app, products to
   request ("Sign In with LinkedIn using OpenID Connect"; optional "Member Data Portability
   (3rd party)"), redirect URI, env vars, what data each scope yields, the no-scraping rule;
   `docs/CONTRACTS.md` new section; `.env.example`.

## Frontend (`src/features/linkedin/**`, theme v2, skeletons not spinners)
8. **Create Resume**: new source card **"Connect LinkedIn"** placed before "Import LinkedIn
   export" (keep that one; rename its description to "…or upload the ZIP export for your full
   history"). States: not connected → explanation of exactly what LinkedIn shares (name, email,
   photo; full history needs the export or the EU portability API) + gradient "Connect LinkedIn"
   button (opens the authorization URL in the same tab); connected → avatar, name, email,
   "Connected · synced 2 h ago", buttons "Sync now", "Create resume from LinkedIn", "Add export
   for full history" (reveals the existing ZIP dropzone), auto-sync toggle, "Disconnect"; after
   returning from the callback (`?source=linkedin&connected=1`) the card auto-runs a sync and
   opens the **Review changes dialog**: diff rows with checkboxes (incoming vs current, conflicts
   unticked by default, additions ticked), "Apply N changes" → profile updated, toast; then
   "Create resume" enabled. Errors (`?error=`) shown inline with a retry.
9. **Settings › Connected accounts**: `LinkedInAccountCard` with the same connected state,
   scopes granted, last sync, auto-sync toggle, "Review latest changes" when `last_sync_diff` has
   items, disconnect with confirm.
10. Notifications deep link works; `useLinkedIn()` hooks under `features/linkedin/api.ts` with
    `qk.linkedin.*`; skeleton for the card; contrast 0 failures; mobile 390 layout; no new npm
    packages.

## Verify
Private servers: backend `.venv/Scripts/python.exe -m uvicorn app.main:app --port 8103` with
`REDIS_URL=redis://localhost:6379/17`, `AUTH_RATE_LIMIT_PER_MINUTE=1000`,
`LINKEDIN_AUTH_BASE=http://localhost:8104/oauth/v2`, `LINKEDIN_API_BASE=http://localhost:8104`,
`LINKEDIN_CLIENT_ID=dev`, `LINKEDIN_CLIENT_SECRET=dev`,
`LINKEDIN_REDIRECT_URI=http://localhost:8103/api/v1/integrations/linkedin/callback`,
`LINKEDIN_DMA_ENABLED=true`; a **fake LinkedIn server** you write (FastAPI, :8104) implementing
`/oauth/v2/authorization` (auto-approves and redirects with code+state), `/oauth/v2/accessToken`,
`/v2/userinfo`, and `/rest/memberSnapshotData` returning a realistic fixture (3 positions,
2 educations, 12 skills, 1 certification); Vite `--port 5233` proxied to :8103. All with
`run_in_background: true`, Playwright scripts via the Write tool under
`scratchpad/linkedin-connect/`, explicit timeouts. Throwaway user `linkedin.check@jobpilot.ai`.
Prove with screenshots (`notes/screenshots/linkedin-connect/`, light + dark, 1440 + 390):
Create Resume card not connected / connected, the OAuth round trip landing back with the Review
dialog, applied profile, resume created from LinkedIn (editor shows 3 positions), Settings card,
auto-sync toggle, disconnect, and the OIDC-only degradation (run the fake server with DMA
disabled: card explains that only basics were filled and offers the export). `npm run build`
green (main chunk ≤ 352 kB — your code must be in the resume module chunk or its own lazy chunk),
`tsc` clean, pytest full suite green, contrast 0. Soft-delete the throwaway user; stop servers.

## Report
1. The API contract and the data each path yields (OIDC vs DMA vs export) in ten lines.
2. Migration id (`d2e4f6a8b0c1`), table, docs touched; confirmation you left two heads.
3. Files changed/added; the four shared-file edits exactly as made.
4. Backend test counts (junit), Playwright proof list with screenshot paths.
5. What the owner must do to go live (LinkedIn app registration steps, env vars), and anything
   unfinished.
