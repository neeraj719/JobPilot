# modules — a multi-module workspace: launcher after login, one sidebar per module

You are **modules**, a senior full-stack developer on JobPilot AI. Read
`notes/resume-studio-plan.md` §1, §5, §6, §7 first (stack, DB rules, security rules, how to
verify — binding), then this file. Nobody else is editing the tree. Do not commit.

## What the owner asked for

JobPilot has grown into several products in one sidebar. The owner wants it to feel like a
suite of **modules**: after login the user sees a page of module boxes — **Resume** first (the
owner's primary concern), then **Job Apply** (discovery, queue, applications, interviews,
companies, automation, emails) — opens one, and from then on sees only that module's own
sidebar, with a switcher to move between modules. Design this the way mature products do
(Atlassian / Google / GitLab product switchers), make it dynamic (modules are data, not
hard-coded menus scattered around) and keep every existing URL working.

## Design (binding)

### Modules
| code | name | home route | what it contains |
|---|---|---|---|
| `resume` | Resume Studio | `/resume` | the 7 Resume pages (`RESUME_NAV_CHILDREN` in `components/layout/navigation.ts`), unchanged |
| `apply` | Job Apply | `/dashboard` | Dashboard, Analytics, Jobs, Application Queue, Applications, Interviews, Companies, Automation, Emails |

Account pages (Profile, Settings, notifications) belong to no module: they are reachable from
the user menu in every module and keep their routes. Add a third, **disabled** module entry
`insights` ("Career Insights — coming soon") so the launcher demonstrates the "not yet
available" state; it has no routes.

**URLs do not move.** `/jobs`, `/applications/:id`, `/emails` and the rest stay exactly as
they are (notifications in the database link to them). The active module is derived from the
current path through the registry; `/` and `/home` serve the launcher.

### Backend (new module `app/modules/workspace/`, mounted at `/api/v1/workspace`)
Catalog + per-user settings, following `docs/DATABASE.md` (uuid ids, standard columns, soft
delete, partial unique indexes, `updated_at` triggers). Migration id `f6b8d0c2e4a7`,
`down_revision = 'e5a7c9b1d3f6'`; SQLite-safe like `f3b8d1a6c920_standing_answers.py`.
* `master.modules` — catalog seeded by the migration (and by the app's seed path, idempotent):
  `code` (partial-unique), `name`, `tagline`, `description`, `icon` (lucide name), `home_path`,
  `accent` (token name, not a hex), `sort_order`, `is_enabled` (platform-wide switch),
  `min_role` (`USER`|`ADMIN`), `status` (`AVAILABLE`|`COMING_SOON`).
* `master.user_module_settings` — one row per (user, module): partial-unique
  `(user_id, module_id)`; `is_enabled` (an admin can switch a module off for one user — e.g. a
  friend who only needs Resume), `is_pinned`, `sort_order`, `last_opened_at`, `open_count`.
* `master.user_workspace_preferences` — one row per user (partial-unique `user_id`):
  `landing` (`LAUNCHER`|`LAST_MODULE`), `last_module_id` (FK, SET NULL), `show_tips`.
* Endpoints (router thin, service owns the logic, ownership scoped to `user.id`):
  `GET /workspace/modules` → the user's visible modules in order, each with `available`
  (enabled platform-wide, enabled for the user, role allowed, status), `is_pinned`,
  `last_opened_at`, and a small `summary` for the card (resume: resumes, drafts, latest ATS
  estimate from `resumes.service` / `ats` summaries; apply: applications this week, queued,
  replies — read from the existing dashboard/stats service; never duplicate the queries, call
  the services); `GET /workspace/preferences`, `PUT /workspace/preferences {landing, show_tips}`;
  `POST /workspace/modules/{code}/open` (records last opened, returns the module);
  `PUT /workspace/modules/{code} {is_pinned?, sort_order?}` (user's own ordering);
  admin: `GET /workspace/admin/users/{user_id}/modules`, `PUT /workspace/admin/users/{user_id}/
  modules/{code} {is_enabled}` behind `app.core.deps.require_admin`, audited
  (`workspace.module_toggled`), with a 404 for an unknown user. A disabled or role-blocked
  module's routes must also be refused on the API side where it matters: add a dependency
  `require_module("resume")` and apply it to the `resumes` and `ats` routers; `apply` module to
  `jobs`, `applications`, `automation`, `interviews`, `emails`, `companies`, `matching`,
  `dashboard` routers (one `dependencies=[Depends(...)]` on `include_router` in `main.py`; 403
  `module_disabled` with the module name in the message). Keep the demo ATS and auth untouched.
* Update the pinned schema counts: `tests/test_migrations.py` (`EXPECTED_TABLES` + the length
  assertion), `tests/test_db_conventions.py` (two `== 35`), `backend/scripts/db_restore_check.sh`
  (`EXPECTED_TABLES` default), `docs/DATABASE.md` (table count, FK count, the tables list, the
  ER overview). Apply the migration to the live DB with `alembic upgrade head` after it passes
  on your test DB; `tests/test_migrations.py::test_migration_matches_models` must pass.

### Frontend
* `src/modules/registry.ts`: the client-side module registry — `code`, `name`, icon component,
  `homePath`, `matches(pathname)` (prefix list), `navSections` (move the existing
  `NAV_SECTIONS` here: the Resume children become the `resume` module's sections, grouped
  sensibly, e.g. "Build" (Dashboard, My Resumes, Create), "Optimise" (ATS Optimizer,
  Job-Specific Resumes, Version History), "Settings" (AI Model Settings); the rest becomes the
  `apply` module's sections). Server data (`GET /workspace/modules`) decides visibility and
  order; the registry decides rendering. A module the server does not return is not rendered
  and its routes redirect to the launcher with a toast.
* `src/pages/Home.tsx` (`/` and `/home`): the **launcher**. A short greeting, then module
  cards in the user's order: icon, name, tagline, 2–3 live numbers from `summary`, "Open",
  pinned state, a keyboard-navigable grid (arrow keys, Enter), "Coming soon" cards disabled
  with a tooltip, an admin-only hint when a module is disabled for this user. Empty/loading/
  error states; light/dark; mobile single column. Premium but calm: no decorative charts.
* `AppShell` / `Sidebar`: the sidebar header becomes a **module switcher** (current module
  icon + name, a dropdown listing the user's modules with their taglines and a "All modules"
  link to the launcher; `Ctrl/Cmd+K`-free — use `Ctrl+Shift+M` via `lib/shortcuts.ts`). The
  sidebar renders only the active module's sections; the collapsed rail shows the module
  icon on top. Topbar title/breadcrumb: "Resume Studio › My Resumes". The brand logo links to
  the launcher. `useDocumentTitle` gets the module name.
* Post-login: `Login`/`ChooseRole` redirect to `/home` unless a `from` deep link exists;
  `/home` immediately forwards to `last_module.homePath` when `landing === 'LAST_MODULE'`
  (a visible "Switch module" always exists, so nobody is trapped). Opening a module posts
  `/open`. Settings page gains a "Workspace" section: landing choice, module order (drag or
  up/down buttons), pins; admins get a per-user module toggle in their existing user/admin
  area if one exists, otherwise a small "Modules for user" panel under Settings › Admin.
* Code-splitting: lazy-load each module's pages with `React.lazy` + `Suspense` per module
  (the main bundle is ~930 kB; measure before/after and report). Keep first paint of the
  launcher light.
* Types in `src/features/workspace/types.ts`; hooks in `src/features/workspace/api.ts`; keys
  under `qk.workspace`. Zod schemas for the forms. No new npm packages.

### Must not break
Every existing route and link; the Resume pages and their tests; notifications' `link`
values; the role selection flow; keyboard shortcut `Ctrl+B`; the demo ATS. Run the whole
backend suite at the end (it takes ~25 min; use `--junitxml` to read counts — the final pytest
summary line is not captured in this environment) plus `npm run build`.

## Verification protocol
Test DB `jobpilot_test_modules`; private servers on **8095 / 5205** with
`REDIS_URL=redis://localhost:6379/11`, started with the Bash tool's `run_in_background: true`
(never foreground); Playwright scripts written with the Write tool to `scratchpad/modules/`,
`page.set_default_timeout(15000)`, every Bash call with an explicit timeout ≤ 300000 ms.
Throwaway users `modules.check@jobpilot.ai` (USER) and `modules.admin@jobpilot.ai` (grant ADMIN
directly in the DB through `user_roles`), soft-deleted at the end; never touch the owner's
accounts. Screenshots (launcher light/dark/mobile, both module sidebars, switcher open,
Settings › Workspace, admin toggle, the 403 state after disabling a module) to
`notes/screenshots/modules/`. Stop your servers (taskkill the PIDs you started).
Keep `notes/modules-progress.md` updated (✅/🔄/⏳, decisions, blockers).

## Report (final message)
1. What the user sees now, step by step from login. 2. Files added/changed, migration id,
docs updated. 3. Backend: exact command, JUnit counts, every failure in full; `npm run build`
and bundle sizes before/after. 4. Browser check: screenshots and anything that looked wrong.
5. Decisions not covered here; anything unfinished and why.
