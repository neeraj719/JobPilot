# JobPilot AI — API reference

Generated from `app.routes`; the authoritative, always-current schema is the OpenAPI document the
running backend serves at **`/openapi.json`** (Swagger UI at **`/docs`**, ReDoc at **`/redoc`**).

* Base URL: `http://localhost:8000` in development; every application endpoint lives under
  `settings.API_PREFIX` = **`/api/v1`**.
* The bundled demo ATS is mounted at **`/demo-ats`** (no prefix, no auth, `include_in_schema=False`).
* Content type is `application/json` everywhere except `POST /api/v1/resumes` (multipart upload)
  and the demo-ATS HTML forms.

---

## Authentication

JWT bearer access tokens with a rotating refresh token in an HttpOnly cookie.

| Step | Call | Result |
|---|---|---|
| 1 | `POST /api/v1/auth/register` or `POST /api/v1/auth/login` (optional `remember_me`) | `TokenResponse` **and** a `refresh_token` HttpOnly cookie — or, for an account holding several roles, `RoleSelectionRequired` (no cookie yet) |
| 1b | `POST /api/v1/auth/select-role {selection_token, role, remember, remember_me}` | only after `RoleSelectionRequired`: `TokenResponse` acting as `role` + the cookie |
| 2 | every other call | `Authorization: Bearer <access_token>` |
| 3 | on `401` | `POST /api/v1/auth/refresh` (cookie only, no body) → new access token + rotated cookie → retry once |
| 4 | sign out | `POST /api/v1/auth/logout` — revokes the refresh token and clears the cookie |

```json
// POST /api/v1/auth/login  {"email": "...", "password": "..."}
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "expires_in": 1800,
  "active_role": "USER",
  "available_roles": ["USER"],
  "requires_role_selection": false,
  "user": { "id": "…", "email": "demo@jobpilot.ai", "full_name": "Aarav Sharma", "role": "USER", "roles": ["USER"], "active_role": "USER" }
}
```

**Active role.** A user can hold several roles (the owner holds `ADMIN` and `USER`). The access
token's `role` claim is the role the session *acts as*; every guard checks it, not membership. Login
and register return one of two shapes, discriminated by `requires_role_selection`:

```json
// POST /api/v1/auth/login for an account holding ADMIN and USER  (HTTP 200, no Set-Cookie)
{
  "requires_role_selection": true,
  "selection_token": "eyJhbGciOi...",          // 5 minutes, single use, cannot call the API
  "available_roles": ["ADMIN", "USER"],
  "user": { "…": "…", "role": "ADMIN", "roles": ["ADMIN", "USER"], "active_role": null }
}
// then POST /api/v1/auth/select-role {"selection_token": "...", "role": "USER", "remember": true}
// -> TokenResponse with "active_role": "USER", and the refresh cookie
```

* `POST /api/v1/auth/switch-role {role}` (bearer **and** the refresh cookie) changes the active role
  without signing out: it rotates the refresh token and returns a new `TokenResponse`. Switching to
  the current role is a no-op `200` that hands back the same access token. A role not held is `403
  role_not_held`.
* `POST /api/v1/auth/refresh` keeps the session's active role.
* If a role is revoked while a session is acting as it, the next call is `401 role_revoked` and so is
  the refresh; sign in again.
* Selection errors: `401 selection_token_expired`, `401 invalid_selection_token`, `401
  selection_token_used`, `403 role_not_held`.
* `remember` is only recorded in the audit trail; the frontend keeps the per-device default in
  `localStorage` (`jobpilot.preferredRole.<userId>`). The server stores no role preference.

* Access tokens expire after `ACCESS_TOKEN_EXPIRE_MINUTES` (30); refresh tokens after
  `REFRESH_TOKEN_EXPIRE_DAYS` (14) with `remember_me`, else 12 hours. Reusing a rotated refresh
  token revokes the whole family.

**Stay signed in.** `remember_me` (default `false`) on login, register and select-role sets the
session's lifetime and cookie: `true` → persistent cookie (`Max-Age=1209600`) and a 14-day session;
`false` → a browser-session cookie (no `Max-Age`) and a 12-hour session. Refresh and switch-role keep
the choice; `TokenResponse.remembered` reports it (`null` when no cookie was set). The password is
never stored by the app; see `docs/SECURITY.md`, "Sessions and remembered devices".

```text
# POST /api/v1/auth/login {"email": "...", "password": "...", "remember_me": false}
set-cookie: refresh_token=USER.…; HttpOnly; Path=/api/v1/auth; SameSite=lax
# POST /api/v1/auth/login {"email": "...", "password": "...", "remember_me": true}
set-cookie: refresh_token=USER.…; HttpOnly; Max-Age=1209600; Path=/api/v1/auth; SameSite=lax
```

**Sessions and devices.** Every signed-in browser is a live refresh token:

```json
// GET /api/v1/auth/sessions   (bearer + the refresh cookie marks "is_current")
[
  { "id": "…", "created_at": "2026-10-04T11:44:02Z", "expires_at": "2026-10-18T11:44:02Z",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; …) Chrome/128.0.0.0 Safari/537.36",
    "device_label": "Chrome on Windows", "is_current": true, "remembered": true }
]
```

A session's `id` is its current refresh-token row, so it changes whenever that device refreshes and
`created_at` is its latest refresh. Re-read the list after acting on it.

**Re-authentication.** The endpoints that sign sessions out, change the password or change "Stay
signed in" need an access token issued less than 10 minutes ago **or** the header
`X-Reauth-Password: <current password>` (percent-encode non-ASCII passwords). Otherwise
`401 {"error": {"code": "reauth_required", "details": {"reason": "stale_token" | "invalid_password"}}}`;
do **not** answer it by refreshing the token, ask for the password. More than 5 wrong passwords per
user in 15 minutes is `429`.

Refresh errors: `401 missing_refresh_token`, `invalid_refresh_token`, `refresh_token_expired`,
`refresh_token_reused` (theft response: every session of the user was revoked), `session_revoked`
(this device was signed out from the device list or by a password change), `role_revoked`.
* Keep the access token in memory (the frontend persists it to `sessionStorage` only) and let the
  cookie carry the refresh token, so a stolen access token dies in half an hour.
* `GET /api/v1/integrations/gmail/callback` is the **one** unauthenticated application endpoint:
  Google redirects a browser there with no bearer token, so the single-use `oauth_state` identifies
  and authorises the user instead.
* Every query is scoped to the caller: another user's job, application or email is a `404`, never
  someone else's data.

## Errors

Every failure — including unhandled ones — comes back in the same envelope:

```json
{ "error": { "code": "review_blocked", "message": "This application is not ready to submit",
             "details": { "blockers": ["1 required question is unanswered"] } } }
```

| Status | `code` | Raised when |
|---|---|---|
| 400 | `app_error` | generic domain error |
| 401 | `unauthorized` | missing/expired token, bad credentials |
| 403 | `forbidden` | authenticated but not allowed |
| 404 | `not_found` | unknown id, or a row that belongs to someone else |
| 409 | `conflict` | duplicate, or an illegal state change (e.g. a second concurrent run) |
| 409 | `requires_user` | automation paused and needs a human (CAPTCHA/OTP/unknown question) |
| 422 | `validation_failed` | a domain rule rejected the input (`details` explains) |
| 422 | `validation_error` | request body failed schema validation (`details` = pydantic errors) |
| 429 | `rate_limited` | `RATE_LIMIT_PER_MINUTE` (120/min) or `AUTH_RATE_LIMIT_PER_MINUTE` (10/min) |
| 502 | `external_service_error` | an upstream (LLM, Gmail, job board) failed |
| 500 | `internal_error` | unhandled — the traceback is logged, never returned |

Responses carry `X-RateLimit-Remaining`; a `429` also carries `Retry-After: 60`. `/health`,
`/docs`, `/openapi.json` and `/demo-ats/*` are exempt from rate limiting.

## Pagination

Every list endpoint takes `page` (1-based) and `page_size` (1–100, default 20) and returns the same
envelope:

```json
{ "items": [ ... ], "total": 137, "page": 1, "page_size": 20 }
```

In the OpenAPI schema these appear as `PageResponse_JobCard_`, `PageResponse_ApplicationRead_` and
so on — one generated component per item type.

---

## Endpoints

`Auth = yes` means the route depends on `get_current_user` and requires a bearer token.

### System

| Method | Path | Auth | Summary |
|---|---|:--:|---|
| `GET` | `/health` | no | Liveness probe: app name, env and active LLM provider |

### Auth

| Method | Path | Auth | Summary |
|---|---|:--:|---|
| `POST` | `/api/v1/auth/register` | no | Create an account (also creates the empty profile, preferences and automation config) |
| `POST` | `/api/v1/auth/login` | no | Exchange email + password for an access token, or for a role choice when the account holds several (`TokenResponse` or `RoleSelectionRequired`) |
| `POST` | `/api/v1/auth/select-role` | no | Trade the role-selection token from login for a session acting as the chosen role (sets the refresh cookie) |
| `POST` | `/api/v1/auth/switch-role` | yes | Change the active role without signing out (rotates the refresh cookie) |
| `POST` | `/api/v1/auth/refresh` | no | Rotate the refresh cookie and issue a new access token (same active role) |
| `POST` | `/api/v1/auth/logout` | no | Revoke the refresh token and clear the cookie |
| `GET` | `/api/v1/auth/me` | yes | Current user |
| `PUT` | `/api/v1/auth/me/password` | yes + reauth | Change the password; signs out every other session and rotates this one |
| `GET` | `/api/v1/auth/sessions` | yes | Signed-in sessions and devices (`SessionRead[]`) |
| `DELETE` | `/api/v1/auth/sessions/{id}` | yes + reauth | Sign out one session (`404 session_not_found` if not yours); clears the cookie when it is this device |
| `POST` | `/api/v1/auth/sessions/revoke-others` | yes + reauth | Sign out of every other device → `{ok, revoked, message}` |
| `POST` | `/api/v1/auth/sessions/current/remember` | yes + reauth | `{remember}`: turn "Stay signed in" on/off for this device (rotates the cookie) → `SessionRead` |

### Profile & preferences

| Method | Path | Auth | Summary |
|---|---|:--:|---|
| `GET` | `/api/v1/profile` | yes | Current user's candidate profile |
| `PUT` | `/api/v1/profile` | yes | Update the candidate profile |
| `GET` | `/api/v1/preferences/job` | yes | Job search preferences |
| `PUT` | `/api/v1/preferences/job` | yes | Update job search preferences |
| `GET` | `/api/v1/profiles/standing-answers` | yes | Answers you saved once for reuse on every application |
| `PUT` | `/api/v1/profiles/standing-answers` | yes | Save a standing answer (replaces the one for the same `question_key`) |
| `DELETE` | `/api/v1/profiles/standing-answers/{standing_answer_id}` | yes | Delete a standing answer (204) |

### Resumes

| Method | Path | Auth | Summary |
|---|---|:--:|---|
| `POST` | `/api/v1/resumes` | yes | Store, extract and parse a resume. Parsing failures still return 201 with |
| `GET` | `/api/v1/resumes` | yes | Every resume of the current user (default first) |
| `GET` | `/api/v1/resumes/{resume_id}` | yes | Get one resume |
| `PATCH` | `/api/v1/resumes/{resume_id}` | yes | Rename / retarget / set default |
| `PUT` | `/api/v1/resumes/{resume_id}/parsed-data` | yes | Save edited parsed data (new version) |
| `POST` | `/api/v1/resumes/{resume_id}/reparse` | yes | Re-run extraction and parsing |
| `GET` | `/api/v1/resumes/{resume_id}/versions` | yes | Version history |
| `GET` | `/api/v1/resumes/{resume_id}/recommendations` | yes | Resume improvement recommendations (`?refresh=true` bypasses the 10-minute cache) |
| `GET` | `/api/v1/resumes/{resume_id}/recommendations/history` | yes | Health and average match score per resume version (before/after chart) |
| `GET` | `/api/v1/resumes/{resume_id}/download` | yes | Download the original file |
| `DELETE` | `/api/v1/resumes/{resume_id}` | yes | Delete a resume |

`GET /resumes/{id}/recommendations` returns `ResumeRecommendations`:
`{resume_id, resume_version, generated_at, overall_score (0-100), target_summary {jobs_analysed,
top_titles[{title,count}], top_skills[{skill,count,share}]}, recommendations[{id, category, priority,
title, detail, evidence[{label, job_id, field}], suggested_text, estimated_score_gain, action, skills}],
score_projection {current_average, projected_average, delta, added_skills, jobs_improved},
version_history[{version_number, created_at, note, overall_score, average_match_score, is_current}],
ai_polished, ai_provider, cached}`. `category` is one of `MISSING_SKILL`, `KEYWORD_GAP`,
`WEAK_SUMMARY`, `EXPERIENCE_BULLETS`, `TITLE_ALIGNMENT`, `SECTION_MISSING`, `LENGTH_AND_FORMAT`,
`STALE_CONTENT`; `priority` is `HIGH` / `MEDIUM` / `LOW`; `action` (missing skills only) is `add`,
`learn` or `list`. Nothing is stored: the result is computed on demand and cached in process memory
for 10 minutes. `/recommendations/history` returns the `version_history` list alone. Both return 404
for a resume that belongs to another user.

### Companies & priorities

| Method | Path | Auth | Summary |
|---|---|:--:|---|
| `GET` | `/api/v1/companies/preferences` | yes | The user's company priority list |
| `PUT` | `/api/v1/companies/preferences` | yes | Replace the whole priority list |
| `POST` | `/api/v1/companies/preferences` | yes | Add or update one company priority |
| `DELETE` | `/api/v1/companies/preferences/{preference_id}` | yes | Remove one company priority |
| `GET` | `/api/v1/companies` | yes | Companies with the user's priority, open jobs and application count (`q`, `priority`) |
| `POST` | `/api/v1/companies` | yes | Add a company by name (`{name, website?, board_url?, ats_type?}`), `201`; idempotent on the normalised name; a `board_url` is verified like `PUT .../board` before anything is written; without one, `auto_detect` (default `true`) looks the board up and stores it. Returns `CompanyRead` + `detection`, `detection_saved`. Rate limited (10/min/user) when it reaches third-party sites |
| `POST` | `/api/v1/companies/detect-board` | yes | Find a company's public job board from `{name?, website?}` without saving (`BoardDetection`); 10/min/user |
| `GET` | `/api/v1/companies/suggestions` | yes | Known-board companies for the Quick start panel (`?limit=20`), minus the user's list, ordered by tag then name |
| `POST` | `/api/v1/companies/{company_id}/detect-board` | yes | Re-run board detection for a company and store a found board; `200` with `detection.method=NONE` when nothing is found; 10/min/user |
| `GET` | `/api/v1/companies/{company_id}` | yes | One company (includes `ats_type`, `ats_board_token`, `ats_board_url`) |
| `PUT` | `/api/v1/companies/{company_id}/board` | yes | Verify and save the company's public job board — see below |
| `DELETE` | `/api/v1/companies/{company_id}/board` | yes | Stop reading the company's board (clears token and URL) |
| `POST` | `/api/v1/companies/{company_id}/blacklist` | yes | Avoid a company and skip its open applications |

`PUT /api/v1/companies/{company_id}/board` body:

```json
{"ats_type": "GREENHOUSE", "board_url": "https://boards.greenhouse.io/stripe"}
```

`ats_type` is one of `GREENHOUSE`, `LEVER`, `ASHBY`, `SMARTRECRUITERS`. `board_url` is the
board URL (any of the forms listed in `app/modules/adapters/boards/urls.py`, e.g.
`job-boards.greenhouse.io/stripe`, `jobs.lever.co/spotify`, `jobs.ashbyhq.com/ramp`,
`jobs.smartrecruiters.com/BoschGroup`) or a bare token (`stripe`). The board is fetched once
through the vendor's public API; the response is `{"company": CompanyRead, "board_job_count": int}`.
Errors: `422 invalid_board_url` (no token in the value, or another vendor's URL),
`422 board_not_found` (404, an empty board, or a payload that is not the vendor's documented
shape), `502 board_unreachable` (network error / vendor 5xx), `404` unknown company.

### Jobs

| Method | Path | Auth | Summary |
|---|---|:--:|---|
| `GET` | `/api/v1/jobs` | yes | Job cards with match score, company priority and application state (see filters below) |
| `GET` | `/api/v1/jobs/sources` | yes | Job sources and their adapters (Greenhouse, Lever, Ashby, SmartRecruiters are real: `is_mock=false`) |
| `POST` | `/api/v1/jobs/discover` | yes | Run discovery across the enabled sources; a board source (`GREENHOUSE`, `LEVER`, `ASHBY`, `SMARTRECRUITERS`) is searched only when some company has a board configured on it |
| `GET` | `/api/v1/jobs/{job_id}` | yes | Job detail |
| `POST` | `/api/v1/jobs/{job_id}/analyze` | yes | Score this job for the current user |
| `POST` | `/api/v1/jobs/{job_id}/queue` | yes | Queue this job for application |
| `POST` | `/api/v1/jobs/{job_id}/skip` | yes | Skip this job |

### Matching

| Method | Path | Auth | Summary |
|---|---|:--:|---|
| `POST` | `/api/v1/matching/analyze-all` | yes | Re-analyze every active job |
| `GET` | `/api/v1/matching/summary` | yes | Match counts for the current user |

### Applications (queue, answers, approval)

| Method | Path | Auth | Summary |
|---|---|:--:|---|
| `GET` | `/api/v1/applications/queue` | yes | The work queue, ordered by company priority, then match score, then freshness |
| `GET` | `/api/v1/applications/review-summary` | yes | Counters for the Approval Center badge |
| `GET` | `/api/v1/applications` | yes | Application list (`status`, `source`, `company`, `from`, `to`, `q`, `sort`) |
| `GET` | `/api/v1/applications/{application_id}` | yes | Full detail: answers, events, documents, emails, `form_snapshot`, review |
| `PATCH` | `/api/v1/applications/{application_id}` | yes | Edit notes, next action, auto-submit flag |
| `GET` | `/api/v1/applications/{application_id}/events` | yes | The application timeline |
| `GET` | `/api/v1/applications/{application_id}/review` | yes | What the Approval Center shows, including every blocker |
| `POST` | `/api/v1/applications/{application_id}/start` | yes | Prepare answers and hand the application to the browser/adapter runner |
| `POST` | `/api/v1/applications/{application_id}/answers/generate` | yes | Re-run the answer engine, keeping everything you typed yourself |
| `PUT` | `/api/v1/applications/{application_id}/answers` | yes | Save the answers the user typed (`{answers: [{id, answer, save_as_standing?}]}`; `save_as_standing` also keeps it as a standing answer) |
| `POST` | `/api/v1/applications/{application_id}/approve` | yes | Human approval: validate, then submit through the adapter |
| `POST` | `/api/v1/applications/{application_id}/submit` | yes | Alias of ``/approve`` kept for API symmetry (section 11) |
| `POST` | `/api/v1/applications/{application_id}/resume-automation` | yes | Continue after you resolved a pause (answered a question, finished a CAPTCHA) |
| `PATCH` | `/api/v1/applications/{application_id}/status` | yes | Manual status change (moving to INTERVIEW also creates an interview row) |
| `POST` | `/api/v1/applications/{application_id}/skip` | yes | Skip with a reason |
| `POST` | `/api/v1/applications/{application_id}/withdraw` | yes | Withdraw a submitted application |
| `POST` | `/api/v1/applications/{application_id}/cover-letter` | yes | Generate a cover letter from the profile and job |
| `PUT` | `/api/v1/applications/{application_id}/cover-letter` | yes | Replace the cover letter with your own text |

### Automation

| Method | Path | Auth | Summary |
|---|---|:--:|---|
| `GET` | `/api/v1/automation/config` | yes | Schedule, limits, minimum score, auto-submit rails, resolved per-source apply modes |
| `PUT` | `/api/v1/automation/config` | yes | Update the config (validated: schedule, timezone, limits, sources, `source_modes`) |
| `POST` | `/api/v1/automation/run` | yes | Start the pipeline in a background thread; returns the RUNNING run |
| `GET` | `/api/v1/automation/runs` | yes | Run history, newest first |
| `GET` | `/api/v1/automation/runs/{run_id}` | yes | One run with its per-step results and stats |
| `POST` | `/api/v1/automation/runs/{run_id}/cancel` | yes | Ask a running pipeline to stop |
| `GET` | `/api/v1/automation/status` | yes | Enabled, next run, last run, today's submitted/remaining |

### Emails

| Method | Path | Auth | Summary |
|---|---|:--:|---|
| `GET` | `/api/v1/emails` | yes | Classified mail (`classification`, `application_id`, `unlinked`, `q`) |
| `POST` | `/api/v1/emails/simulate` | yes | Inject a realistic simulated email (demo + tests) |
| `GET` | `/api/v1/emails/{email_id}` | yes | One email with its full body |
| `POST` | `/api/v1/emails/{email_id}/link` | yes | Link an email to an application |
| `POST` | `/api/v1/emails/{email_id}/unlink` | yes | Detach a wrongly linked email |
| `POST` | `/api/v1/emails/{email_id}/classify` | yes | Override the classification |
| `POST` | `/api/v1/emails/{email_id}/read` | yes | Mark an email as read |

### Integrations

| Method | Path | Auth | Summary |
|---|---|:--:|---|
| `GET` | `/api/v1/integrations` | yes | Gmail status, connected platform accounts and every adapter |
| `POST` | `/api/v1/integrations/gmail/connect` | yes | Start the read-only Gmail OAuth flow |
| `GET` | `/api/v1/integrations/gmail/callback` | no | OAuth redirect target (unauthenticated: identified by the one-time state) |
| `POST` | `/api/v1/integrations/gmail/sync` | yes | Fetch and classify recent recruiting mail |
| `DELETE` | `/api/v1/integrations/gmail` | yes | Revoke and wipe the Gmail connection |
| `GET` | `/api/v1/integrations/accounts` | yes | Connected job-platform accounts |
| `POST` | `/api/v1/integrations/accounts` | yes | Connect (or update) a job-platform account |
| `DELETE` | `/api/v1/integrations/accounts/{account_id}` | yes | Remove a connected account |

### Dashboard

| Method | Path | Auth | Summary |
|---|---|:--:|---|
| `GET` | `/api/v1/dashboard/stats` | yes | Today/week/month/totals, rates and the "needs you" list |
| `GET` | `/api/v1/dashboard/charts` | yes | Time series, by company/source/status, funnel, match distribution (`range=7d\|30d\|90d`) |
| `GET` | `/api/v1/dashboard/activity` | yes | Merged audit + application-event timeline (`kind` discriminator) |

### Interviews

| Method | Path | Auth | Summary |
|---|---|:--:|---|
| `GET` | `/api/v1/interviews` | yes | Every interview of the current user, newest first (or soonest when ``upcoming``) |
| `POST` | `/api/v1/interviews` | yes | Add an interview round by hand |
| `GET` | `/api/v1/interviews/{interview_id}` | yes | One interview with its prep material |
| `PATCH` | `/api/v1/interviews/{interview_id}` | yes | Reschedule, change type/outcome/notes |
| `POST` | `/api/v1/interviews/{interview_id}/prep` | yes | Generate the AI preparation sheet and store it on the interview |
| `DELETE` | `/api/v1/interviews/{interview_id}` | yes | Remove an interview round |

### Notifications

| Method | Path | Auth | Summary |
|---|---|:--:|---|
| `GET` | `/api/v1/notifications/unread-count` | yes | Number of unread notifications |
| `POST` | `/api/v1/notifications/read-all` | yes | Mark every notification as read |
| `GET` | `/api/v1/notifications` | yes | Notifications, newest first (`unread_only`) |
| `POST` | `/api/v1/notifications/{notification_id}/read` | yes | Mark one notification as read |

### Audit log

| Method | Path | Auth | Summary |
|---|---|:--:|---|
| `GET` | `/api/v1/audit` | yes | The user's audit trail (`application_id`, `automation_run_id`, `action_prefix`) |

### AI

| Method | Path | Auth | Summary |
|---|---|:--:|---|
| `GET` | `/api/v1/ai/status` | yes | Which LLM provider is active |

### Browser sessions

| Method | Path | Auth | Summary |
|---|---|:--:|---|
| `GET` | `/api/v1/browser/sessions` | yes | Browser contexts stored for the current user. Storage state is never returned |
| `DELETE` | `/api/v1/browser/sessions/{session_id}` | yes | Forget a stored browser context (cookies/localStorage) for this user |
| `GET` | `/api/v1/browser/screenshots/{application_id}/{name}` | yes | Serve an automation screenshot, but only for the caller's own application |
| `GET` | `/api/v1/browser/status` | yes | Whether Playwright Chromium can be launched here (sync probe, cached) |

### Demo ATS (no auth, not in the OpenAPI schema)

| Method | Path | Auth | Summary |
|---|---|:--:|---|
| `GET` | `/demo-ats` | no | Landing page: every demo company and its open roles |
| `GET` | `/demo-ats/jobs.json` | no | Machine-readable catalogue consumed by ``DemoAtsAdapter.search_jobs`` |
| `GET` | `/demo-ats/jobs/{slug}` | no | Job description page with an Apply button |
| `GET` | `/demo-ats/jobs/{slug}/apply` | no | The application form. ``?captcha=1`` renders a (never-solved) CAPTCHA widget |
| `POST` | `/demo-ats/jobs/{slug}/apply` | no | Validate, store the submission as JSONL and confirm -- plus a simulated email |
| `GET` | `/demo-ats/submissions.json` | no | The most recent submissions (newest first) - for debugging and the demo script |


### Common `GET /api/v1/jobs` filters

`q`, `min_score`, `max_score`, `salary_min`, `location`, `work_mode`, `company`, `experience_min`,
`experience_max`, `source`, `posted_within_hours`, `status` (an `ApplicationStatus`, or `NONE` for
"not applied yet"), `priority` (`P1`/`P2`/`P3`/`AVOID`) and `sort` (`match` | `posted` | `salary`).

Company priority is *derived* — a `company_id` link, an exact normalised-name match, or the longest
preference that is a whole-word prefix of the company name ("Google" covers "Google (Demo
Careers)"). The list, the detail page and the `priority` filter all use the same resolution.

---

## The demo scenario as a curl walkthrough

Assumes a seeded backend on `http://localhost:8000` (`python -m app.seed`). `jq` is optional.

```bash
BASE=http://localhost:8000/api/v1

# 1. Log in as the demo user and keep the access token.
TOKEN=$(curl -s -X POST $BASE/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@jobpilot.ai","password":"DemoPass123!"}' | jq -r .access_token)
AUTH="Authorization: Bearer $TOKEN"

# 2. The dashboard is already alive: jobs found, applications today, what needs you.
curl -s -H "$AUTH" $BASE/dashboard/stats | jq '{today, totals, attention}'

# 3. Discover jobs across every enabled source (mock boards + the demo ATS).
curl -s -X POST -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"limit":25}' $BASE/jobs/discover | jq '{jobs_found, jobs_new, duplicates_merged}'

# 4. Look at the best matches, then pick a demo-ATS job (those have a real form to fill).
curl -s -H "$AUTH" "$BASE/jobs?sort=match&min_score=75&page_size=5" \
  | jq '.items[] | {title, company: .company.name, match_score, company_priority}'
JOB=$(curl -s -H "$AUTH" "$BASE/jobs?source=DEMO_ATS&status=NONE&page_size=1" | jq -r '.items[0].id')

# 5. Queue it, which creates an application in the work queue.
APP=$(curl -s -X POST -H "$AUTH" $BASE/jobs/$JOB/queue | jq -r .id)

# 6. Start the automation: answers come from the profile, then Playwright opens the demo ATS form,
#    detects the fields, fills everything it can - and stops at whatever it cannot know.
curl -s -X POST -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"run_in_background":true}' $BASE/applications/$APP/start | jq '{status, automation_state}'

# poll until it pauses (a few seconds)
curl -s -H "$AUTH" $BASE/applications/$APP \
  | jq '{automation_state, pause_reason, detected: (.form_snapshot.fields | length),
         filled: (.form_snapshot.filled | length)}'

# 7. Answer the questions it refused to invent, then check the review.
curl -s -H "$AUTH" $BASE/applications/$APP \
  | jq '[.answers[] | select(.status=="NEEDS_USER_INPUT") | {id, question_text}]'
curl -s -X PUT -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"answers":[{"id":"<answer-id>","answer":"1 December 2026"}]}' \
  $BASE/applications/$APP/answers | jq '.[] | {question_key, status}'
curl -s -H "$AUTH" $BASE/applications/$APP/review | jq '{can_submit, blockers}'

# 8. Approve: the browser submits the real form and the ATS hands back DEMO-XXXXXX.
curl -s -X POST -H "$AUTH" $BASE/applications/$APP/approve \
  | jq '{status, external_application_id, confirmation_message}'

# 9. The demo ATS replies "Thank you for applying..."; the classifier links it and moves the
#    application to APPLICATION_RECEIVED. Simulate any other reply the same way.
curl -s -H "$AUTH" "$BASE/emails?application_id=$APP" \
  | jq '.items[] | {subject, classification, matched_by}'
curl -s -X POST -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"application_id\":\"$APP\",\"kind\":\"INTERVIEW\"}" $BASE/emails/simulate \
  | jq '{classification, status_applied}'
curl -s -H "$AUTH" $BASE/applications/$APP | jq '{status, last_response_at}'

# 10. Run the whole pipeline unattended (discover, match, filter, queue, autofill, review).
RUN=$(curl -s -X POST -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"dry_run":false}' $BASE/automation/run | jq -r .id)
curl -s -H "$AUTH" $BASE/automation/runs/$RUN | jq '{status, stats, steps: [.steps[].step]}'
```

`backend/scripts/smoke_e2e.py` runs exactly this sequence as an assertive smoke test against any
deployment:

```bash
cd backend
./.venv/Scripts/python.exe scripts/smoke_e2e.py --base-url http://localhost:8000 --with-browser
```
