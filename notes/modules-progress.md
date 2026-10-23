# modules — progress (multi-module workspace)

Brief: `notes/modules-prompt.md` + the owner's **amendment** below. Plan rules:
`notes/resume-studio-plan.md` §1/5/6/7. Test DB `jobpilot_test_modules`; private servers
8095 (API) / 5205 (Vite), Redis db 11.

## Owner amendment (binding, received mid-task)

1. Seed: `apply` inserted with `is_enabled = false` (status AVAILABLE), `resume` enabled,
   `insights` COMING_SOON. Seed (migration + app seed path) inserts **missing rows only**,
   never overwrites an admin's later `is_enabled` / `status` / `sort_order`.
2. Admin platform control: `GET /workspace/admin/modules`, `PUT /workspace/admin/modules/{code}
   {is_enabled?, status?, sort_order?}` behind `require_admin`, audited
   (`workspace.module_catalog_updated`, before/after), validated (cannot disable the last
   enabled module; cannot make a COMING_SOON module available without a `home_path`). In
   Settings › Admin next to the per-user toggles, with the note "Switching a module off hides
   it for everyone and returns 403 from its API".
3. Launcher: platform-disabled module = muted card "Not available right now" (distinct from
   "Coming soon"); admins get an "Enable" affordance opening the admin panel. Deep links into
   a disabled module → launcher + toast.
4. API: `require_module` covers platform switch, per-user switch, role check — in that order.
5. Scheduler: `due_users` skips users for whom `apply` is unavailable
   (`workspace.service.module_available(db, user_id, "apply")`), with a test.
6. Tests: seed idempotent + non-overwriting; catalog PUT validation + audit; launcher payload
   `apply` `available=false, reason="platform_disabled"`; `/jobs` 403 while disabled, 200 after
   enabling; scheduler skip.
7. Live DB: psql output showing resume enabled / apply disabled; browser: login → launcher
   with Resume Studio openable and Job Apply muted (screenshot).

Coordination: developer "theme" owns `frontend/src/index.css`, `tailwind.config.*`,
`index.html`, `components/ui/**`, `components/common/**`, `features/dashboard/chart-theme.ts`,
`docs/DESIGN.md` — do not edit those. New shared primitives go in `features/workspace/components/`.

## Checklist

- ✅ Models `app/models/workspace.py` (+ enums `ModuleStatus`, `WorkspaceLanding`); `home_path` nullable
- ✅ Migration `f6b8d0c2e4a7` (down `e5a7c9b1d3f6`), seeds resume on / apply **off** / insights coming soon
- ✅ Live `jobpilot`: migration applied; then aligned in place to the amended migration (see Decisions); `alembic check` clean
- ✅ `app/modules/workspace/` (schemas, service, router) at `/api/v1/workspace`, admin catalog endpoints
- ✅ `require_module()` in `app/core/deps.py`, applied in `main.py`; reason order platform → coming soon → user → role
- ✅ Scheduler skip (`app/worker/scheduler.py::due_users` → `module_available`)
- ✅ Pinned counts (35 → 38) in tests + `db_restore_check.sh`; conftest seeds catalog (all enabled) after each truncate
- ✅ `tests/test_workspace.py` (amended) + migration seed test — pass
- ✅ Full suite run #1 (pre-amendment code): 1320 tests, 1 failure (`test_runner_demo_ats::test_pipeline_auto_applies_with_standing_answers_only`, passes alone — order/timing flake), 3 skipped
- ✅ Frontend registry, workspace api/types, launcher, switcher, ModuleRoute, Login/ChooseRole → `/home`
- ✅ Settings › Workspace + Settings › Admin (per-user)
- ✅ Code-splitting: main 1,188 kB → 448 kB (gzip 332 → 133 kB); charts no longer on first paint
- ✅ Frontend for the amendment (lowercase reasons, `features/workspace/copy.ts`, `AdminCatalogCard` with the 403 note + confirm on switch-off, muted "Not available right now" card + admin "Enable")
- ✅ `npm run build` passes (final: main 449.9 kB / gzip 133.0 kB; first paint = index + react + ui)
- ✅ Browser check on 8095/5205 (live DB) — 20 screenshots in `notes/screenshots/modules/`; see Incident for 13–17
- ✅ Docs: `docs/DATABASE.md` (38 tables, 62 FKs, 3 rows, ER), `docs/CONTRACTS.md` (§1 prefix + guards, new §19)
- ✅ Full backend suite run #2 (final code): JUnit `tests=1328 failures=0 errors=0 skipped=3` (520 s)
- ✅ Cleanup: modules.check@ / modules.admin@ soft-deleted (+ their workspace/role rows), 8095/5205 stopped, scratch DB dropped

**Done.** Remaining follow-ups are in the final report (not blockers).

## Decisions

* Reason codes are lowercase (`platform_disabled`, `coming_soon`, `disabled_for_user`,
  `role_required`), like the API's existing `details.reason` values (`stale_token`).
* Visibility: tombstoned/inactive rows and modules above the active role are **hidden**;
  everything else is listed with `available` + `unavailable_reason` (platform-disabled modules
  are listed muted, per the amendment).
* Guard fails open only when the catalog has never heard of the code (unseeded DB); a
  tombstoned row is refused.
* Order: pinned first, then the user's `sort_order`, then the catalog's.
* `GET /workspace/modules?summary=true` adds card numbers (launcher only).
* Added `GET /workspace/admin/users?email=` (exact, case-insensitive): there was no admin user
  list anywhere in the app.
* Audit: per-user toggle → `user_id` = target, `meta.admin_id`; catalog update → `user_id` =
  admin, `meta.before/after`. Only written when something changed.
* "Last enabled module" = the last module anybody can use (enabled **and** AVAILABLE), so
  making it COMING_SOON is refused too (409 `last_enabled_module`).
* `home_path` is nullable: a COMING_SOON module has no route (`insights`); making a module
  usable without one is 422 `home_path_required`.
* Live DB alignment: `f6b8d0c2e4a7` had been applied before the amendment. Rather than
  downgrade (which drops the owner's 4 `user_module_settings` / 2 preference rows) the
  equivalent was applied in place:
  `ALTER TABLE master.modules ALTER COLUMN home_path DROP NOT NULL; UPDATE master.modules SET is_enabled=false WHERE code='apply'; UPDATE master.modules SET home_path=NULL WHERE code='insights';`
  — the result is identical to a fresh `upgrade head` (checked with `alembic check`).
* The test fixtures seed every module enabled (the suite exercises every module's API).

## Incident (browser check, 2026-10-23 19:34 UTC)

For the Job Apply sidebar / platform on-off screenshots I built a scratch DB
(`jobpilot_modules_scratch`, `alembic upgrade head`) and started API 8096 + Vite 5206 on it.
Both failed to bind: **someone else's servers already listen on 8096/5206, and that API
uses the live DB**. My script ran against them, so Job Apply was switched **on platform-wide
on the live DB for ~9 s** (19:34:16 → 19:34:25 UTC, two `workspace.module_catalog_updated`
audit rows by `modules.admin@jobpilot.ai`) and then off again through the confirm dialog.
Checked afterwards: 0 automation runs and 0 application changes in that window; the only
actor was the throwaway admin; `master.modules` is back to resume on / apply off.
Screenshots 13–17 therefore come from the live DB. Lesson: verify the port is free (or that
the responding server is yours) before driving it.

## Blockers

None.
