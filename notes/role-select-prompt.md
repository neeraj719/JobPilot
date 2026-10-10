# Role selection — choose which role to act as at login, switch any time after

You are "role-select", a senior full-stack developer on JobPilot AI (FastAPI + SQLAlchemy 2 +
PostgreSQL backend, React/Vite/Tailwind frontend, repo `C:\Users\Neera\projects\job application`).
Read `docs/CONTRACTS.md` (auth section), `backend/app/modules/auth/{router,service,schemas}.py`,
`backend/app/core/{security,deps}.py`, `backend/app/models/user.py`,
`frontend/src/stores/auth.ts`, `frontend/src/router.tsx`, `frontend/src/pages/Login.tsx` and
`frontend/src/components/layout/{UserMenu,Topbar}.tsx` before writing code. Do not commit.

## Why

Roles are rows in `master.user_roles`, so a user can hold several (the owner holds ADMIN and
USER). Today `User.role` collapses that to the highest role and nothing in the product lets
the user choose. The owner wants: when an account has more than one role, a page after
password entry asks which role to sign in as, and the role can be switched later without
logging out.

## Design (follow it; do not store the choice in the database)

The **active role is a claim in the access token**. Everything that checks a role checks the
active role, not role membership. The choice is remembered per device in the browser.

### 1. Backend

- `app/core/security.py`: `create_access_token(user_id, role, extra)` already takes `role`.
  Treat that claim as the **active role**. Add `create_role_selection_token(user_id,
  roles: list[str])` → a short-lived JWT (5 minutes, constant in the auth module, not in
  `config.py`) with `"type": "role_selection"` and the allowed roles; and
  `decode_role_selection_token`.
- `app/core/deps.py`: `get_current_user` reads `payload["role"]`, validates that the user
  still holds it (compare to `{r.name for r in user.roles}`; if not, 401
  `role_revoked`), and stores it on `request.state.active_role` and on the user object as a
  non-persisted attribute `user.active_role`. `require_roles` checks `user.active_role`.
  Also treat a token with no `role` claim (issued before this change) as the user's
  highest role so existing sessions keep working.
- `auth/schemas.py`: `TokenResponse` gains `active_role: str` and `available_roles:
  list[str]`. New `RoleSelectionRequired` response: `{ "requires_role_selection": true,
  "selection_token": str, "available_roles": [...], "user": UserRead }`. `UserRead` gains
  `active_role` and `roles` (list of names). New requests `SelectRoleRequest {
  selection_token, role, remember: bool = false }` and `SwitchRoleRequest { role }`.
- `auth/router.py` + `service.py`:
  - `POST /auth/login` and `POST /auth/register`: if the user holds exactly one role,
    behave as today but include `active_role` and `available_roles`. If more than one,
    return `RoleSelectionRequired` with HTTP 200 and **do not** set the refresh cookie
    yet. Use a discriminated union response model so OpenAPI documents both shapes.
  - `POST /auth/select-role`: validates the selection token and that `role` is in its list
    and still held; issues access + refresh tokens with that active role, sets the
    cookie, audits `auth.role_selected`. Rate-limit like login.
  - `POST /auth/switch-role` (authenticated): validates the user holds `role`; rotates the
    refresh token (reuse the existing rotation path) and returns a new `TokenResponse`
    with the new active role; audits `auth.role_switched`. Switching to the role you
    already have is a no-op 200.
  - `POST /auth/refresh`: the new access token carries the **same active role** as the
    session being refreshed. Store the active role alongside the refresh token so refresh
    can recover it: the `RefreshToken` model has no column for it and you must not add
    one, so encode it into the opaque refresh token payload you already hash (for
    example `"<role>.<random>"` before hashing) or keep an in-process map keyed by token
    hash as a fallback if that is not feasible. Document which you chose and why.
  - `GET /auth/me` returns `active_role` and `roles`.
- Audit: both new events go through `app.core.audit.audit` with the user id.
- No database schema change, no migration, no edits to `app/models/*`.

### 2. Frontend

- `stores/auth.ts`: handle the two login response shapes. Add `activeRole`,
  `availableRoles`, `pendingRoleSelection` (selection token + roles + user), actions
  `selectRole(role, remember)` and `switchRole(role)`. Remember the per-device default
  role in `localStorage` under `jobpilot.preferredRole.<userId>` when `remember` is
  ticked; when a later login requires a selection and a remembered role is still
  available, auto-select it silently and show a small toast "Signed in as Admin. Switch".
- New page `pages/ChooseRole.tsx` at `/choose-role`: card per role with a short
  description (Admin: manage users and system; User: your own job search), a "Remember on
  this device" checkbox, and a "Not you? Sign out" link. Only reachable while a selection
  is pending; otherwise redirect to `/login` or `/dashboard`.
- `router.tsx`: `ProtectedRoute` sends a user with a pending selection to
  `/choose-role`.
- `UserMenu.tsx`: show the active role as a badge and, when `availableRoles.length > 1`,
  a "Switch role" submenu that calls `switchRole` and then reloads the current route's
  data (invalidate react-query caches).
- `Settings.tsx`: an "Account roles" card listing roles with the active one marked, the
  switch action, and the remembered-device preference with a "Forget" button.
- Keep `frontend/src/types/api.ts` in sync. Other developers are also adding types to
  that file right now: re-read it immediately before each edit and add your types in a
  clearly delimited `// --- auth roles ---` block at the end.

### 3. Tests

- Backend: single-role login unchanged; multi-role login returns the selection shape and
  no cookie; select-role happy path, wrong role, expired token, revoked role; switch-role
  happy path, role not held (403), no-op; refresh preserves the active role; a token
  without a role claim still works; `require_roles` honours the active role (an
  ADMIN+USER user acting as USER is refused by the admin guard).
- Frontend: `npm run build` passes. If the project has component tests, add one for the
  store's response handling.
- Run your tests plus `tests/test_auth.py` and `tests/test_security_regressions.py` with
  `TEST_DATABASE_URL=postgresql+psycopg://jobpilot:jobpilot@localhost:5432/jobpilot_test_roles`.
  Do not run the full suite.
- Live check: start a venv uvicorn on port 8050 and log in as
  `neerajmishra1085@gmail.com` (the owner's account, holds ADMIN and USER; password is in
  the environment variable `JOBPILOT_OWNER_PASSWORD` if set, otherwise skip the live check
  and say so). Show the selection response, then select USER, then switch to ADMIN, then
  refresh, and confirm the active role at each step via `/auth/me`. Do not change that
  account's data.

### 4. Docs

Update `docs/API.md` and `docs/CONTRACTS.md` auth sections, and `docs/SECURITY.md` with a
short paragraph on why the active role lives in the token and what happens when a role is
revoked mid-session.

## Hard constraints

- No database changes. Do not edit `app/models`, `alembic`, `app/core/config.py`,
  `adapters`, `companies`, `jobs`, `resumes`, `ai`, or `frontend/src/features/{companies,resume}`.
  Other developers are working there.
- Do not weaken any existing security behaviour: refresh rotation, cookie flags, rate
  limits, audit.
- Routers stay thin. Do not commit, stash, reset or checkout.

## Report

1. Files added or changed, one line each. 2. Test summary line and failures in full;
frontend build result. 3. The live check transcript (trimmed) or why it was skipped.
4. How refresh recovers the active role and why. 5. Decisions not covered; anything
unfinished with the reason.
