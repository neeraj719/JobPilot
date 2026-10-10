# Stay signed in — remember a device safely, never store the password

You are "stay-signed-in", a senior full-stack developer on JobPilot AI (FastAPI + SQLAlchemy 2
+ PostgreSQL backend, React/Vite/Tailwind frontend, repo `C:\Users\Neera\projects\job application`).
The "role-select" change (active role in the access token, `/auth/select-role`,
`/auth/switch-role`, `ChooseRole` page) is already in the tree; build on it. Read
`docs/SECURITY.md`, `backend/app/modules/auth/{router,service,schemas}.py`,
`backend/app/core/security.py`, `backend/app/models/user.py` (`RefreshToken`),
`frontend/src/stores/auth.ts`, `frontend/src/pages/Login.tsx`, `frontend/src/pages/Settings.tsx`
before writing code. Do not commit.

## What the owner asked for, and the safe reading of it

"After the first login, ask the user whether to save the login so they do not have to type
it again, and make sure it is secure." The secure version of this is **not** storing the
password anywhere in our app. It is three things:

1. A **"Stay signed in on this device"** choice at login that controls how long the
   session cookie lives.
2. Letting the **browser's own password manager** offer to save the credentials, which
   is what users expect from "save my login" and is encrypted by the OS.
3. A **Sessions and devices** view where the user sees every remembered device and can
   sign any of them out.

Do not implement anything that writes the password, or a reversible form of it, to
localStorage, sessionStorage, IndexedDB, cookies, or the database.

## Scope

### 1. Backend — session lifetime and device list

- `POST /auth/login`, `/auth/register`, `/auth/select-role` accept `remember_me: bool =
  false`.
  - `remember_me=true`: refresh token and cookie live `settings.REFRESH_TOKEN_EXPIRE_DAYS`
    (14 days today), persistent cookie with `max_age`, as now.
  - `remember_me=false`: refresh token lives 12 hours (constant `SHORT_SESSION_HOURS = 12`
    in the auth module; do not edit `app/core/config.py`) and the cookie is a **session
    cookie** (no `max_age`, no `expires`) so it dies when the browser closes.
  - Rotation on `/auth/refresh` and `/auth/switch-role` must preserve the original
    choice: a remembered session stays remembered, a short one stays short. The
    `RefreshToken` row has no column for this and you must not add one; encode it the same
    way role-select encodes the active role in the opaque refresh token, or infer it from
    the row's `expires_at - created_at` span. Say which you chose.
- Reuse detection: if a refresh token that is already `revoked_at` or `replaced_by_hash`
  is presented again, revoke **every** active refresh token of that user, audit
  `auth.refresh_reuse_detected`, and return 401. If this already exists, confirm it with a
  test rather than reimplementing.
- `GET /auth/sessions`: the user's active refresh tokens as `SessionRead { id, created_at,
  expires_at, user_agent, device_label, is_current, remembered }`. `device_label` is a
  friendly parse of the user agent ("Chrome on Windows"); `is_current` matches the cookie
  on the request. Use only columns that exist on `RefreshToken`.
- `DELETE /auth/sessions/{id}`: revoke one (404 if not the user's). `POST
  /auth/sessions/revoke-others`: revoke everything except the current one. Both audited.
- Changing the password (`PUT /auth/me/password`) must revoke all other sessions and
  rotate the current one. Confirm or add.
- Re-authentication for sensitive actions: `PUT /auth/me/password` and the sessions
  endpoints that revoke must require the access token to be younger than 10 minutes
  (`iat` claim) **or** the request to carry `X-Reauth-Password` verified against the hash.
  Return 401 `reauth_required` otherwise. Keep the check in one dependency in
  `app/core/deps.py`.

### 2. Frontend — login, browser save, sessions

- `Login.tsx`: a "Stay signed in on this device" checkbox, default **off**, with helper
  text "Keeps you signed in for 14 days. Only use on a device you own." Send `remember_me`
  through the store. The `ChooseRole` page forwards the same choice to `/auth/select-role`.
- Browser password manager: keep `autoComplete="email"` and `"current-password"` (already
  present), make sure the form is a real `<form>` with a submit, and after a successful
  login call the Credential Management API when available:
  `navigator.credentials.store(new PasswordCredential({ id: email, password, name }))`
  inside a feature check and a try/catch. The browser then shows its own "Save password?"
  prompt; our code never keeps the password after the call. Do **not** add a custom
  "save my password" UI of our own.
- Access token stays in `sessionStorage` as today. Do not move it to `localStorage`.
- `Settings.tsx`: a "Sessions and devices" card listing sessions from `/auth/sessions`
  with device label, signed-in date, expiry, a "This device" badge, "Remembered" badge, a
  "Sign out" button per row and a "Sign out of all other devices" button. If the API
  answers `reauth_required`, open a small dialog asking for the current password and
  retry with `X-Reauth-Password`.
- First-login nudge: after the first successful login on a device that did not tick
  "Stay signed in", show a one-time dismissible banner "Want to skip the login next time?
  Turn on Stay signed in from Settings or at your next login." Store the dismissal flag in
  localStorage keyed by user id. This is the "ask the user after one-time login" the
  owner wanted, done without storing credentials.
- Keep `frontend/src/types/api.ts` in sync; re-read it right before each edit and append
  in a delimited `// --- auth sessions ---` block.

### 3. Tests

- Backend: remember_me true vs false cookie attributes and token expiry; rotation
  preserves the choice; reuse detection revokes the family; sessions list, revoke one,
  revoke others, is_current flag; password change revokes others; reauth dependency
  (fresh token passes, stale token fails, stale + correct password passes, stale + wrong
  password fails and is rate limited).
- Frontend: `npm run build` passes.
- Run your tests plus `tests/test_auth.py` and `tests/test_security_regressions.py` with
  `TEST_DATABASE_URL=postgresql+psycopg://jobpilot:jobpilot@localhost:5432/jobpilot_test_sessions`.
  Do not run the full suite.
- Live check on a venv uvicorn at port 8060: log in without remember, inspect the
  `Set-Cookie` header (no Max-Age); log in with remember (Max-Age present); list
  sessions; revoke others. Use the account `garima.sharma@jobpilot.ai` only if the password
  is provided in `JOBPILOT_TEST_USER_PASSWORD`; otherwise register a throwaway user
  `stay.signed.in.check@jobpilot.ai` and soft-delete it afterwards, and say so.

### 4. Docs

`docs/SECURITY.md`: a "Sessions and remembered devices" section covering cookie flags,
lifetimes, rotation, reuse detection, re-authentication, and the explicit statement that
the application never stores passwords client-side. `docs/API.md`: the new endpoints.

## Hard constraints

- Never persist the password or a reversible form of it anywhere. Never put tokens in
  localStorage.
- Keep `httponly`, `secure` (as configured) and `samesite` on the refresh cookie.
- No database schema changes; do not edit `app/models`, `alembic`, `app/core/config.py`,
  `adapters`, `companies`, `jobs`, `resumes`, `ai`, or `frontend/src/features/{companies,resume}`.
- Routers stay thin. Do not commit, stash, reset or checkout.

## Report

1. Files added or changed. 2. Test summary and failures in full; build result.
3. Live check transcript showing the two Set-Cookie headers and the sessions list.
4. How the remember choice survives rotation and why. 5. Decisions not covered; anything
unfinished with the reason.
