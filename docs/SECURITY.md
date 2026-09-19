# JobPilot AI — Security Model

Security is a first-class requirement (spec §22). This document lists what the MVP implements and
what is deliberately **not** done.

## Authentication & sessions
* Passwords hashed with bcrypt (12 rounds). Password policy enforced at registration.
* Short-lived JWT access tokens (30 min) sent in the `Authorization` header — never in a cookie —
  so cross-site request forgery cannot replay them.
* Opaque refresh tokens stored **hashed** (SHA-256), delivered in an `HttpOnly`, `SameSite`
  cookie scoped to the auth path, rotated on every refresh. Reuse of a revoked token revokes the
  whole family (session theft detection).
* Role-based access (USER / ADMIN) via `require_roles`. Every query is scoped to the current user.
* Rate limiting: global per-IP/user window plus a stricter limit on register / login / refresh
  (Redis-backed, in-memory fallback). `X-Forwarded-For` is ignored unless `TRUST_PROXY_HEADERS=true`,
  so a client cannot pick its own bucket (or forge the IP written to `audit_logs`).
* Unknown emails still pay the bcrypt cost, so response time does not enumerate accounts.

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
