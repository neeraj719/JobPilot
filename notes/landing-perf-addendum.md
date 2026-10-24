# landing-perf addendum — tree state, image/text collision, Choose-role restyle, logout destination

Read `notes/landing-perf-prompt.md` first (sections A–D are still binding), then this file.

## 0. State of the tree (important)

The previous agent was stopped by the owner mid-way through the landing-perf brief. It had modified
about 30 files in `frontend/src` (landing skeleton/hero/nav/sections, `loadLanding.ts`,
`heroShared.tsx`, AuthDialog/LoginForm/RegisterForm, `authModal.ts`, AppShell/Sidebar/Topbar,
`modules/prefetch.ts`, `modules/resume/prefetchData.ts`, `modules/registry.ts`, `ModuleRoute.tsx`,
`lib/queryClient.ts`, several `features/*/api.ts`, `ScoreRing.tsx`, `AnimatedNumber.tsx`,
`ErrorBoundary.tsx`, `pages/Home.tsx`, `AuthLayout.tsx`, `AuthHero3D.tsx`) and wrote NO progress
entry. Its last words were "apply the Home and prefetch-data changes", so `Home.tsx` and
`prefetchData.ts` may be half-edited.

First step, before any new work: `git diff --stat`, `npx tsc --noEmit`, `npm run build`. Read
every half-edited file, finish or revert each change deliberately (never blind `git checkout` of a
file: the v2 theme and landing work in the same files are wanted — check `git diff` per file), and
write a "landing-perf (resumed)" entry in `notes/theme-identity-progress.md` listing what you kept.
Then work through A–D of the main brief and E–G below. Verify after each section; do not leave the
tree broken between sections.

## E. A 3D illustration collides with text (owner screenshot, not available to you)

The owner reports an illustration overlapping copy. Audit EVERY composition where a 3D image sits
beside or behind text, at 360, 390, 412, 768, 1024, 1280, 1366, 1440 and 1920 px, light and dark:
launcher hero band and module tiles (`pages/Home.tsx`), landing hero and bento tiles
(`features/landing/*`), Resume Dashboard start card, auth hero (`AuthLayout.tsx` + `AuthHero3D`),
every `EmptyState` with an illustration, the choose-role page. Rule: text and image live in separate
grid/flex tracks with `min-w-0` on the text column, the image is `object-contain` inside a box with
`max-h` / `aspect-ratio`, never absolutely positioned over the text column, and at narrow widths
the image moves below or shrinks (`hidden` under a breakpoint only if it adds nothing). Prove it
with a Playwright overlap check: for each composition, the text block's and the image's
`getBoundingClientRect()` must not intersect at any breakpoint; print the table. Fix what fails and
keep the shots as `after/overlap-<place>-<w>-<theme>.png`.

## F. Choose-role page still wears the old theme

After login a multi-role user lands on `/choose-role` (`pages/ChooseRole.tsx` + role cards), which
is still v1. Restyle to v2 to match Login/Register exactly: same `AuthLayout` split hero (3D scene /
poster, display headline "Choose how you want to work today" or similar, gradient wordmark), a glass
card with a short title and helper line, role options as selectable cards (icon chip, name, one-line
description, gradient border + check when selected, keyboard arrows + Enter, `role="radiogroup"`),
a gradient primary "Continue" button with `loading` state, and a quiet "Sign out" link. The role
button's inline spinner may stay inside the button only. Skeleton for the role list, no layout
shift. Shots `after/choose-role-{light,dark}-{1440,390}.png` + a one-role and a three-role state.

## G. Logout lands on /choose-role instead of the landing page (bug)

Root cause to confirm: logout clears the access token but leaves `pendingRoleSelection` (and/or
other auth fields) set in the persisted zustand store, so `ProtectedRoute` sees
`!accessToken && pendingRoleSelection` and redirects to `/choose-role`. Fix properly:
1. One `logout()` action in `stores/auth` that: calls the backend revoke endpoint (best effort,
   with timeout), clears access token, pending role selection, remembered-device/stay-signed-in
   state (cookie cleared server-side), user profile and any per-user cache, calls
   `queryClient.clear()` (or `removeQueries` for user-scoped keys), and resets persisted storage so
   a reload cannot resurrect the state. Make it idempotent and safe if the network call fails.
2. Navigation: every sign-out entry point (account menu, Settings › Security, 401 handler, the
   choose-role "Sign out" link) ends on `/` (the landing page) with a "Signed out" toast; the 401 /
   session-expired path ends on `/?auth=login` with a "Session expired, please sign in again" toast
   and the deep link preserved in `state.from` so sign-in returns there.
3. Route guards: `/choose-role` with no pending selection → `/`; signed-in user on `/` → `/home`
   (unchanged); anonymous `/login` and `/register` continue to work.
4. Cross-tab: logging out in one tab logs out the others (storage event or BroadcastChannel) and
   they also land on `/`.
Verify with Playwright: login (single-role and multi-role users), logout from the account menu,
assert URL `/`, reload stays on `/`, no `/choose-role` flash in the frame sequence; session-expiry
path; two-tab logout. Add/adjust frontend unit tests if the store has them. Backend: if the revoke
endpoint or refresh-cookie clearing is incomplete, fix it in `app/modules/auth` and add a pytest
(run with your own `TEST_DATABASE_URL=…/jobpilot_test_landingperf`).

## Report (in addition to the main brief's report)
Tree-state triage (kept / reverted / finished per file), the overlap table, choose-role shots,
logout root cause with the exact store fields involved and the test evidence.
