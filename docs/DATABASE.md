# JobPilot AI — Database Schema

PostgreSQL 18 in production and in the test suite, SQLite for the no-Docker local run (all
column types are portable: `Uuid`, `JSON`, `DateTime(timezone=True)`, string-backed enums).
27 tables in five named schemas (`master`, `unified`, `transaction`, `media`, `audit`).
Migrations: Alembic (`backend/alembic/versions`). Models: `backend/app/models/*.py`.
Enums: `backend/app/models/enums.py`.

## Conventions

Six rules hold for **every** table. They are enforced by tests
(`backend/tests/test_db_conventions.py`), not by review.

### 1. Every table has `id`, `is_active` and `deleted_at`

(And `created_at`, `updated_at`, `created_by`, `updated_by` — seven columns in all; see
rule 6 for the four this rule does not cover.)

`id` is a uuid primary key (`UUIDMixin`). `is_active` and `deleted_at` come from
`LifecycleMixin` in `backend/app/models/base.py` and mean two different things:

| Column | Meaning |
|---|---|
| `is_active` | A **business** switch: a user disabled, a job no longer open, an integration paused. The row is still real and still returned when asked for; it is simply not in play. `NOT NULL DEFAULT true`, queried explicitly. |
| `deleted_at` | The **soft-delete tombstone**. `NULL` = the row exists. A timestamp = it is deleted and must behave as if gone. Nothing filters on it by hand. |

Deleting sets *both* (`deleted_at = now()`, `is_active = false`), so a deleted row is never
also "active". The pair is not redundant: `is_active = false, deleted_at IS NULL` is the
ordinary "paused / closed / disabled but still here" state.

The four append-only tables (`audit_logs`, `application_events`, `resume_versions`,
`automation_runs`) carry the columns purely for uniformity — nothing ever deletes from them,
and the global filter needs no exceptions.

### 2. Soft delete, through one global filter

`backend/app/core/soft_delete.py` registers a single `do_orm_execute` listener on
`Session` that appends

```python
with_loader_criteria(LifecycleMixin, lambda cls: cls.deleted_at.is_(None), include_aliases=True)
```

to **every ORM SELECT** — `select()`, `Session.get()`, eager loads and lazy relationship
loads alike. No module filters on `deleted_at` itself; eighteen modules each remembering a
`.where(...)` is eighteen chances to forget one, and the one forgotten is a data leak.

Use `soft_delete(obj)` to delete. The one way past the filter is explicit, per statement:

```python
db.scalars(select(Resume).execution_options(include_deleted=True))
db.get(User, user_id, execution_options={"include_deleted": True})
```

It is used only where tombstones are the point — `app/seed.py --force`, which is a rebuild
tool and still hard-deletes. Caveat: the filter rewrites queries, so it cannot hide an
instance the session is already holding in its identity map; expunge or use a fresh session.

Authentication respects tombstones for free: `get_current_user` does `Session.get(User, …)`
and login looks the user up by email, so a soft-deleted account simply is not found (401).

### 3. Partial unique indexes on the keys a user can re-create

A tombstoned row still occupies a UNIQUE key, so deleting something and adding it back
would fail. Every key a user can delete and legitimately re-create is therefore
`UNIQUE (…) WHERE deleted_at IS NULL`:

| Index | Table / columns |
|---|---|
| `uq_users_email_active` | `master.users (email)` |
| `uq_company_pref_user_name_active` | `master.company_preferences (user_id, normalized_name)` |
| `uq_connected_account_user_source_active` | `master.connected_accounts (user_id, source)` |
| `uq_browser_session_user_source_active` | `master.browser_sessions (user_id, source)` |
| `uq_roles_name_active` | `master.roles (name)` |
| `uq_user_roles_user_role_active` | `master.user_roles (user_id, role_id)` |

Keys nothing user-facing deletes stay plain UNIQUE constraints (`job_sources`,
`job_matches`, `applications`, `email_messages`, `user_profiles.user_id`, …) — a partial
index there would cost a scan and buy nothing.

### 4. Every link is a uuid foreign key

27 uuid primary keys, 37 uuid foreign keys, no natural or composite keys between tables.

**One junction table per many-to-many relationship, named after both sides**
(`user_roles`). **One-to-many keys live on the owning row**, not in a shared table: a future
"where does this user live" is `user_profiles.location_id`, not a row in a hub table. A
generic "everything this user links to" table was considered and rejected — a user has many
roles but one location, so no single row shape fits both cardinalities, and forcing them
together means nullable foreign keys, which contradicts this very rule. A consolidated
per-user view can be added later if one read picture is wanted.

### 5. Roles are rows, not a column

`users.role` (an enum column) is gone. `master.roles` holds the role rows — `USER` and
`ADMIN`, inserted by the migration so a freshly migrated database needs no seed — and
`master.user_roles` grants them. `User.role` is now a **property** returning the most
privileged role held, so `require_roles`, `UserRead.role` and the JWT claim are unchanged;
`UserRead.roles` additively exposes the full list. Grants go through
`auth.service.assign_role` / `revoke_role`; a revoke tombstones the junction row, and the
partial unique index is what lets the same role be granted again.

`user_profiles` stays a separate 1:1 table rather than being folded into `users`: the hot
auth path reads four columns, the answer engine reads forty, and they change on completely
different schedules.

### 6. Seven standard columns, with the timestamps owned by the database

Every table carries the same seven columns, from the single `StandardColumnsMixin` in
`backend/app/models/base.py`. A table that is missing one is a bug, not a variation.

| Column | Shape | Who fills it |
|---|---|---|
| `id` | `uuid PRIMARY KEY` | the ORM (`uuid4`) |
| `created_at` | `timestamptz NOT NULL DEFAULT now()` | the **database**, on INSERT |
| `updated_at` | `timestamptz NOT NULL DEFAULT now()` | the **database**, on INSERT and on every real UPDATE |
| `created_by` | `uuid NULL` → `master.users.id` `ON DELETE SET NULL` | the acting user, stamped at flush |
| `updated_by` | `uuid NULL` → `master.users.id` `ON DELETE SET NULL` | the acting user, stamped at flush |
| `is_active` | `boolean NOT NULL DEFAULT true` | the business switch (rule 1) |
| `deleted_at` | `timestamptz NULL` | the soft-delete tombstone (rule 1) |

**The timestamps are the database's, not the ORM's.** There is no Python-side
`default=` or `onupdate=` on either — one mechanism, and it is the one that also sees
the writes the ORM never hears about: a hand-written `UPDATE` in psql, a bulk
`update()` statement, a migration, a restore. `updated_at` is maintained by one trigger
per table, `trg_<table>_updated_at`, calling a single `public.set_updated_at()`
function. The DDL lives in `backend/app/core/db_triggers.py` because two callers need
it and must not drift: the migration, and `tests/conftest.py` (which builds its schema
from `Base.metadata.create_all`, and metadata knows nothing about triggers — a trigger
that existed only in production would make the test proving it meaningless).

The trigger carries a `WHEN` guard so that a statement that changes nothing leaves the
timestamp alone: "last modified" should mean it.

```sql
CREATE TRIGGER trg_jobs_updated_at BEFORE UPDATE ON "unified"."jobs" FOR EACH ROW
WHEN (OLD::text IS DISTINCT FROM NEW::text) EXECUTE FUNCTION public.set_updated_at();
```

The comparison is on the row *text*, not on the rows. The obvious `OLD.* IS DISTINCT
FROM NEW.*` is a trap: row comparison goes field by field and 20 of the 27 tables carry
a `json` column, which has no equality operator — so it works right up until the two
rows are equal as far as that column, i.e. it raises `could not identify an equality
operator for type json` on exactly the no-op update the guard exists for.

Two consequences worth knowing:

* `obj.created_at` is `None` between `Session.add()` and the flush. Read it after
  `db.flush()`; the value does not exist until the INSERT runs.
* an explicitly supplied value still wins, because a server default only applies when
  the INSERT names no value. That is what lets `app/seed.py` fabricate three weeks of
  history on past dates.

**`created_by` / `updated_by` are stamped from the acting user**, by two flush
listeners on `AuditUserMixin` (`backend/app/core/actor.py`), never by hand — eighteen
modules each remembering two assignments is eighteen chances to forget one. The actor
is published once, at the entry point:

* **HTTP** — `deps.get_current_user` records it on the request's `Session`
  (`set_session_actor`), and `ActorMiddleware` publishes it in a `ContextVar` for the
  whole request. It has to be the session for the dependency: Starlette runs sync
  dependencies in a *copy* of the request's context, so a `ContextVar` set inside one
  is discarded on return (and `ContextVar.reset` in a `yield` dependency raises
  outright, because `__enter__` and `__exit__` land in different contexts).
* **background work** — `actor_context(user_id)` around the entry point:
  `automation.pipeline.run_pipeline`, the apply thread in
  `applications.executor.run_in_background` (a new thread starts with an empty context,
  so the id is passed across the boundary by hand), and `integrations.service.sync_gmail`.
* **registration** — `auth.service.create_user` generates the user's id up front so the
  account can be its own `created_by`, and wraps the profile / preferences / automation
  config / role rows it creates in `actor_context(user.id)`.

`NULL` is a real answer and means *no user did this*: a scheduler decision
(`mark_no_response`, `cleanup_expired_browser_sessions`), a migration, a seed run. Rows
that predate this convention read as system writes, which is what they were. An
explicitly supplied `created_by` is never overwritten.

The columns are deliberately **not indexed** — an audit trail, not a query path — and
deliberately **not** in the API schemas. Migration `b9f41c7d2e58` adds the four columns
to all 27 tables, backfills `updated_at` from `created_at` (and `created_at` from
`job_sources.discovered_at` / `automation_runs.started_at` where the row already knew),
and creates the function and the 27 triggers. It runs on SQLite too, with two documented
differences: the audit columns are added there without the foreign key (SQLite cannot
add a constraint without rewriting the table, and rewriting all 27 would put rule 3's
partial unique indexes through a reflect-and-recreate round trip), and the SQLite
trigger — an `AFTER UPDATE` that writes the row again, guarded by
`WHEN NEW.updated_at IS OLD.updated_at` so it cannot re-fire — bumps the timestamp on
any UPDATE statement rather than only on one that changed something.

## Entity relationship overview

```
users ──N:M── roles   (through user_roles)
  │ ──1:1── user_profiles
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

All 27 carry the seven standard columns — `id` / `created_at` / `updated_at` /
`created_by` / `updated_by` / `is_active` / `deleted_at` — and all 27 carry the
`trg_<table>_updated_at` trigger; only what is *extra* is listed.

| Table | Purpose | Notable columns / constraints |
|---|---|---|
| `users` | account | `email` partial-unique (`WHERE deleted_at IS NULL`), `hashed_password` (bcrypt); no `role` column — see `user_roles` |
| `roles` | role catalogue | `name` partial-unique (`USER`, `ADMIN`), inserted by the migration |
| `user_roles` | user↔role junction | partial-unique `(user_id, role_id)`; a revoked grant is a tombstoned row |
| `refresh_tokens` | rotating refresh tokens | `token_hash` unique (sha256), `revoked_at`, `replaced_by_hash` |
| `user_profiles` | candidate facts used by the answer engine | personal, professional (JSON lists), `skill_experience` (skill→years), `work_authorization` (country→bool), `requires_sponsorship`, `canonical_answers` |
| `job_preferences` | targeting | `desired_titles`, `min_salary`, `desired_salary`, `currency`, `notice_period_days`, `preferred_locations`, `work_modes`, `employment_types`, `min_match_score`, `only_posted_within_hours` |
| `company_preferences` | P1/P2/P3/AVOID per user | partial-unique `(user_id, normalized_name)` |
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
| `automation_configs` | daily automation settings | limits, schedule, `auto_submit_enabled` (default off), `source_modes` JSON (`{source: AUTO_APPLY \| DISCOVER_ONLY}`, default `{}` = adapter capability) |
| `automation_runs` | pipeline executions | `steps` JSON, `stats` JSON, `status` |
| `connected_accounts` | job-platform accounts | partial-unique `(user_id, source)`, `encrypted_credentials` |
| `browser_sessions` | isolated Playwright storage state per (user, source) | partial-unique `(user_id, source)`, `encrypted_storage_state` |
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
