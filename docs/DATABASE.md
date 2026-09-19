# JobPilot AI — Database Schema

PostgreSQL 16 in production, SQLite for unit tests (all column types are portable:
`Uuid`, `JSON`, `DateTime(timezone=True)`, string-backed enums). Migrations: Alembic
(`backend/alembic/versions`). Models: `backend/app/models/*.py`. Enums: `backend/app/models/enums.py`.

## Entity relationship overview

```
users ──1:1── user_profiles
  │ ──1:1── job_preferences
  │ ──1:1── automation_configs
  │ ──1:1── email_integrations
  │ ──1:N── company_preferences ──N:1── companies
  │ ──1:N── resumes ──1:N── resume_versions
  │ ──1:N── connected_accounts
  │ ──1:N── browser_sessions
  │ ──1:N── notifications
  │ ──1:N── refresh_tokens
  │ ──1:N── automation_runs
  │ ──1:N── job_matches ──N:1── jobs
  └ ──1:N── applications ──N:1── jobs ──N:1── companies
                │                  └──1:N── job_sources
                ├──1:N── application_answers
                ├──1:N── application_events
                ├──1:N── application_documents
                ├──1:N── email_messages
                └──1:N── interviews
audit_logs (user_id?, application_id?, automation_run_id?)
skills (taxonomy)
```

## Tables

| Table | Purpose | Notable columns / constraints |
|---|---|---|
| `users` | account | `email` unique, `hashed_password` (bcrypt), `role` USER/ADMIN |
| `refresh_tokens` | rotating refresh tokens | `token_hash` unique (sha256), `revoked_at`, `replaced_by_hash` |
| `user_profiles` | candidate facts used by the answer engine | personal, professional (JSON lists), `skill_experience` (skill→years), `work_authorization` (country→bool), `requires_sponsorship`, `canonical_answers` |
| `job_preferences` | targeting | `desired_titles`, `min_salary`, `desired_salary`, `currency`, `notice_period_days`, `preferred_locations`, `work_modes`, `employment_types`, `min_match_score`, `only_posted_within_hours` |
| `company_preferences` | P1/P2/P3/AVOID per user | unique `(user_id, normalized_name)` |
| `companies` | normalised company registry | `normalized_name` unique, `domain`, `email_domains` (learned sender domains), `ats_type` |
| `jobs` | one normalised posting | `dedupe_hash` (company+title+location), `apply_url`, `application_type`, skills JSON, salary/experience ranges |
| `job_sources` | where a job was seen | unique `(source, external_id)`; several rows per job = cross-platform duplicate |
| `job_matches` | per-user match analysis | unique `(job_id, user_id)`; `match_score` + part scores, `missing_skills`, `explanation` |
| `resumes` / `resume_versions` | uploaded files + parsed JSON history | `is_default`, `parsed_data`, `parse_status`, `sha256` |
| `skills` | taxonomy with aliases | `normalized_name` unique |
| `applications` | the tracked application | unique `(user_id, job_id)`; `status` (13 states), `automation_state` (IDLE/RUNNING/SUCCESS/FAILED/PAUSED/REQUIRES_USER/RETRYING), `pause_reason`, `form_snapshot` (detected fields + values shown in the Approval Center), `applied_at`, `external_application_id`, `next_action` |
| `application_answers` | one row per form question | `question_key` (canonical), `status` ANSWERED/NEEDS_USER_INPUT/SKIPPED, `answer_source`, `is_sensitive`, `rationale` |
| `application_events` | timeline | `event_type`, `from_status`, `to_status`, `actor` |
| `application_documents` | resume / cover letter attached | |
| `email_integrations` | Gmail OAuth (read-only) | `encrypted_credentials` (Fernet), `scopes`, `oauth_state` |
| `email_messages` | classified emails | unique `(user_id, provider_message_id)`; `classification`, `matched_by`, `is_simulated`, `status_applied` |
| `interviews` | rounds + AI prep | `prep_material` JSON |
| `automation_configs` | daily automation settings | limits, schedule, `auto_submit_enabled` (default off) |
| `automation_runs` | pipeline executions | `steps` JSON, `stats` JSON, `status` |
| `connected_accounts` | job-platform accounts | unique `(user_id, source)`, `encrypted_credentials` |
| `browser_sessions` | isolated Playwright storage state per (user, source) | `encrypted_storage_state` |
| `notifications` | in-app notifications | `type`, `is_read`, `link` |
| `audit_logs` | every automated / security action | `action` (dotted), `level`, `metadata` |

## Status vocabulary

`ApplicationStatus`: DISCOVERED → QUEUED → IN_PROGRESS → APPLIED → APPLICATION_RECEIVED →
RECRUITER_CONTACTED / ASSESSMENT / INTERVIEW → OFFER, plus REJECTED, WITHDRAWN, NO_RESPONSE, SKIPPED.

`RESPONSE_STATUSES` (count as "the company replied"): APPLICATION_RECEIVED, ASSESSMENT, INTERVIEW,
RECRUITER_CONTACTED, REJECTED, OFFER.

Email classification → status: APPLICATION_RECEIVED → APPLICATION_RECEIVED, RECRUITER_MESSAGE →
RECRUITER_CONTACTED, INTERVIEW → INTERVIEW, ASSESSMENT → ASSESSMENT, REJECTION → REJECTED,
OFFER → OFFER (never downgrades an application).

## Encryption at rest

`email_integrations.encrypted_credentials`, `connected_accounts.encrypted_credentials` and
`browser_sessions.encrypted_storage_state` are Fernet-encrypted with `ENCRYPTION_KEY`. Passwords are
bcrypt hashes. Refresh tokens are stored as SHA-256 hashes. No plaintext secret is ever persisted.
