# JobPilot AI — Security Model

Security is a first-class requirement (spec §22). This document lists what the MVP implements and
what is deliberately **not** done.

## Authentication & sessions
* Passwords hashed with bcrypt (12 rounds). Password policy enforced at registration.
* Short-lived JWT access tokens (30 min) sent in the `Authorization` header — never in a cookie —
  so cross-site request forgery cannot replay them.
* Opaque refresh tokens stored **hashed** (SHA-256), delivered in an `HttpOnly`, `SameSite`
  cookie scoped to the auth path, rotated on every refresh. Reuse of a revoked token revokes the
  whole family (session theft detection). Lifetimes, remembered devices and the device list: see
  [Sessions and remembered devices](#sessions-and-remembered-devices).
* Role-based access (USER / ADMIN) via `require_roles`. Every query is scoped to the current user.
* **The active role lives in the token.** An account can hold several roles; it acts as one per
  session, chosen after the password step (`/auth/select-role`) and switchable later
  (`/auth/switch-role`). The choice is the access token's signed `role` claim, and the refresh token
  carries it as a prefix (`"<ROLE>.<random>"`) that is covered by the stored SHA-256 hash, so a client
  cannot edit it without invalidating the token. Keeping it in the token rather than in the database
  means two devices can act as different roles at once, no extra lookup or column is needed, and
  least privilege is the default: an owner browsing as `USER` is refused by an `ADMIN` guard until
  they deliberately switch. Every request still re-checks the claim against `master.user_roles`:
  if a role is revoked mid-session the very next call fails with `401 role_revoked` (not at token
  expiry), refresh refuses with the same code, and the user must sign in again and choose among the
  roles they still hold. The 5-minute role-selection token cannot call the API and is single-use;
  switching requires the refresh cookie and rotates it, so an access token alone can neither change
  role nor extend itself.
* Rate limiting: global per-IP/user window plus a stricter limit on register / login / refresh
  (Redis-backed, in-memory fallback). `X-Forwarded-For` is ignored unless `TRUST_PROXY_HEADERS=true`,
  so a client cannot pick its own bucket (or forge the IP written to `audit_logs`).
* Unknown emails still pay the bcrypt cost, so response time does not enumerate accounts.

## Sessions and remembered devices

"Save my login so I do not have to type it again" is implemented **without the application ever
storing the password**, on the client or the server:

* **The application never stores passwords client-side.** The password is typed into the login
  form, sent once over HTTPS to `POST /auth/login`, and dropped. Nothing writes it, or anything
  reversible derived from it, to `localStorage`, `sessionStorage`, IndexedDB, cookies or the
  database (only the bcrypt hash exists, server-side). The access token stays in `sessionStorage`
  (dies with the tab); tokens never go to `localStorage`.
* **Saving the password is the browser's job.** The login page is a real `<form>` with
  `autocomplete="email"` / `"current-password"`, and after a successful sign-in it calls
  `navigator.credentials.store(new PasswordCredential({id, password, name}))` where the Credential
  Management API exists (feature-checked, errors swallowed), so the browser's own password manager
  (OS-encrypted) shows its "Save password?" prompt. There is no custom "save my password" UI.
* **"Stay signed in on this device"** (`remember_me`, default **off**) on `/auth/login`,
  `/auth/register` and `/auth/select-role` only decides how long the refresh session lives:

  | | refresh token lifetime | refresh cookie |
  |---|---|---|
  | `remember_me=false` | 12 hours (`SHORT_SESSION_HOURS` in `app/modules/auth/service.py`) | **session cookie**: no `Max-Age`/`Expires`, gone when the browser closes |
  | `remember_me=true` | `REFRESH_TOKEN_EXPIRE_DAYS` (14 days) | persistent, `Max-Age` = 14 days |

  Both are `HttpOnly`, `SameSite` (`COOKIE_SAMESITE`, `lax` by default), `Secure` per
  `COOKIE_SECURE` (forced on in production) and scoped to `Path=/api/v1/auth`. On a new tab or a
  reopened browser the app calls `/auth/refresh` once at start-up, which is how a remembered device
  skips the login. The choice can be changed later for the current device from Settings → Security
  (`POST /auth/sessions/current/remember`, which rotates the cookie into the other lifetime).
* **Rotation keeps the choice.** Every `/auth/refresh` and `/auth/switch-role` replaces the refresh
  token; the successor gets the same kind of lifetime (sliding: 14 days or 12 hours from the
  rotation) and the same kind of cookie. No column records the choice: it is read back from the
  presented row's own lifetime, `expires_at - created_at` (remembered if longer than halfway between
  12 hours and 14 days). The server sets both values, so a client cannot influence it, and the same
  rule labels every row in the device list, including other devices whose raw token is never seen.
* **Reuse detection.** Presenting a refresh token that was already rotated (`replaced_by_hash`) or
  revoked revokes **every** live session of that user, audits `auth.refresh_reuse_detected` at
  ERROR and answers `401 refresh_token_reused`. Two deliberate exceptions keep honest clients from
  tripping it: an **expired** token is answered `401 refresh_token_expired` first (a browser left
  open past a 12-hour session retries its dead cookie), and a session the user **signed out from the
  device list** (or that a password change signed out) is revoked *and* tombstoned (`deleted_at`),
  so when that device wakes up it gets `401 session_revoked` instead of signing out every other
  device too.
* **Sessions and devices** (`GET /auth/sessions`): every live refresh token of the user with a
  friendly device label parsed from the user agent ("Chrome on Windows"; a hint, never trusted),
  `is_current` for the cookie on the request and `remembered`. Sign out one
  (`DELETE /auth/sessions/{id}`, `404` if it is not the caller's) or all others
  (`POST /auth/sessions/revoke-others`); both are audited (`auth.session_revoked`,
  `auth.sessions_revoked_others`). A signed-out device keeps its current access token until it
  expires (at most `ACCESS_TOKEN_EXPIRE_MINUTES`), then cannot refresh.
* **Password change** (`PUT /auth/me/password`) signs out every other session (revoked and
  tombstoned, as above) and rotates the current one, so this device stays signed in with a fresh
  refresh token.
* **Re-authentication for sensitive actions.** `PUT /auth/me/password`,
  `DELETE /auth/sessions/{id}`, `POST /auth/sessions/revoke-others` and
  `POST /auth/sessions/current/remember` depend on `require_recent_auth` (`app/core/deps.py`): the
  access token's `iat` must be under 10 minutes old, **or** the request must carry
  `X-Reauth-Password` with the current password (percent-encoded UTF-8 accepted for non-ASCII
  passwords). Otherwise `401 reauth_required` (`details.reason`: `stale_token` or
  `invalid_password`). Wrong passwords are audited (`auth.reauth_failed`) and limited to 5 per user
  per 15 minutes (`429`). The web client never answers `reauth_required` by refreshing the token; it
  asks for the password in a dialog and retries once. Limitation: `iat` measures the age of the
  access token, and `/auth/refresh` mints a new one, so whoever holds the refresh cookie can obtain
  a fresh token; the check protects against a stolen access token and an unattended tab, not against
  a stolen cookie (which reuse detection and the device list address).
* **First-login nudge.** After a sign-in without "Stay signed in", the app shows a one-time,
  dismissible banner pointing to the option. The dismissal flag (`jobpilot.staySignedInNudgeDismissed.<userId>`
  in `localStorage`) is not a secret.

## Secrets & data at rest
* Nothing secret is hardcoded; configuration comes from environment variables (`.env.example`).
  The development defaults are published, so the app **refuses to start** with `ENV=production`
  while `SECRET_KEY` or `ENCRYPTION_KEY` is still a default (and forces `COOKIE_SECURE`,
  hides `/docs`, `/redoc` and `/openapi.json`).
* OAuth token bundles, job-platform credentials and Playwright storage state are Fernet-encrypted
  with `ENCRYPTION_KEY`. Encrypted blobs are never returned by the API (`has_credentials: bool` only).
* Resume uploads are validated (extension **and** magic bytes, size limit enforced *while streaming*,
  so an oversized body is never buffered) and stored outside the web root under a per-user
  directory; downloads require ownership.
* Form attachments are resolved from the application's own resume row and must live under
  `UPLOAD_DIR`; a file answer can never be typed in, so the automation cannot be pointed at
  an arbitrary server file.
* API keys for LLM providers live only on the server; the frontend never sees them.

## Gmail
* OAuth 2.0 only — the app never asks for or stores a Gmail password.
* Least privilege: only `gmail.readonly` (+ `openid`, `userinfo.email` for the account address).
  No send/modify scope is requested, and `include_granted_scopes` is off.
* The OAuth `state` is generated per flow, carries its issue time (15-minute TTL) and is verified
  on callback **together with a matching `HttpOnly` state cookie**, so a consent URL handed to a
  victim cannot attach their mailbox to someone else's account. A mismatch burns the state.
* `GMAIL_SCOPES` is validated against a read-only allow-list at startup: the scope set cannot be
  widened by configuration, and a write-capable scope returned by Google is refused.
* Disconnect revokes the token at Google (best effort) and wipes the encrypted bundle.

## Browser automation
* One isolated Playwright `BrowserContext` per (user, job source); contexts are never shared.
* Chromium keeps its renderer sandbox; `--no-sandbox` is only added when
  `BROWSER_DISABLE_SANDBOX=true` (set for the container images, where user namespaces are blocked).
* CAPTCHA, OTP, 2FA, login walls and account-registration prompts are **detected** and the run is
  paused with `REQUIRES_USER`. There is no solver, no stealth plugin, no anti-bot evasion.
* Sensitive questions (work authorization, sponsorship, legal declarations, demographic/voluntary
  data) are never answered by the AI; they come from explicit profile facts or the user.
* Submission requires explicit approval (Approval Center) unless the user has enabled auto-submit
  for a specific supported source. Hard rails: daily limit, per-platform limit, delays, retry limit.
* Real third-party sites (LinkedIn, Naukri, Indeed, …) ship as mock adapters in the MVP. Production
  adapters must use official APIs / partner programmes and respect each site's terms and rate limits.

## Web hardening
* Security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`).
* The bundled demo ATS (`/demo-ats`) is the only unauthenticated write on the API. It is **not
  mounted when `ENV=production`**, its apply endpoint has its own per-IP rate limit and upload
  size cap, and `submissions.json` returns metadata only — never an applicant's details.
* The demo seed refuses to run in production (it creates an account whose password is config).
* Strict CORS allow-list. Input validation with Pydantic v2 on every endpoint.
* Uniform error envelope; stack traces never leak to clients. Structured JSON logs in production.

## Auditability
* Every automated action (job found, analysed, application started, field filled, paused, resumed,
  submitted, email classified/linked, automation steps) and every security-relevant user action
  (login, failed login, password change, integration connect/disconnect) is written to `audit_logs`
  with actor, level and metadata.

## Known gaps (MVP)
* No email verification / password reset flow yet.
* No per-tenant KMS; a single `ENCRYPTION_KEY` (rotate by re-encrypting).
* No CSP header on the API (the frontend is served by Nginx; add a CSP there for production).
