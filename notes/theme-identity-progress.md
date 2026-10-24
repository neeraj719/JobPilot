# theme-identity — progress

Stream: **theme-identity**. Brief now: `notes/theme-modern-prompt.md` (supersedes
`notes/theme-identity-prompt.md`, see Pivot). Private servers: API :8097 (live DB,
`REDIS_URL=…/13`, `LLM_PROVIDER=mock`, rate limits raised for the screenshot run only), Vite :5207.
Throwaway user `identity.check@jobpilot.ai` (text-imported resume, one ATS analysis 89/100, six
job targets in different stages so the status pills show).
Screenshot script: `scratchpad/theme-identity/shots.py before|after [name]`.

## Pivot (2026-10-24, from the owner via coordinator)
The identity brief (dark indigo sidebar, stronger type, three brand touches, layout leftovers,
density) is superseded by **theme-modern**: modern / Gen-Z / 3D but professional, across the
whole product. Kept from the identity pass (they are part of the new brief): the dark indigo
sidebar tokens + rail/switcher/sheet/tooltips, the type-scale work, the `.bg-hero` brand
gradient, `ease-drawer`, the AI-settings select fix, the Job-Specific Resumes pill/board polish,
the extended contrast checker. The "before" set taken before any code change stays the before set.

## Amendment (2026-10-24, owner via coordinator, binding): skeletons, never spinners
Everywhere, loading is a shimmer skeleton shaped like the content — never a spinner or a
"Loading…" screen. Skeleton system in `components/ui/skeleton.tsx` + `components/common/skeletons.tsx`
(Skeleton with shimmer on transform, opacity-pulse under reduced motion, base/highlight tokens
in both themes; PageSkeleton, AppShellSkeleton, StatRowSkeleton, CardGridSkeleton, TableSkeleton,
ListSkeleton, FormSkeleton, DetailSkeleton, ChartSkeleton + feature-specific ones: launcher tiles,
resume card grid, editor three columns, ATS results, version timeline, AI provider cards, job
targets board), matching real dimensions (no layout shift). `LoadingState` becomes skeleton-only
(API kept), router `FullPageSpinner` → `AppShellSkeleton` / auth skeleton, lazy Suspense
fallbacks → `PageSkeleton`, every `isLoading` branch → matching composite, `isFetching` → keep
content + thin top progress bar. Allowed exceptions only: inline spinner in a button (`loading`
prop) / icon-only action; upload progress bar. Verify with a 1.5 s `page.route` delay:
`after/loading-*.png` (launcher, Resume Dashboard, My Resumes, editor, ATS, Version History,
AI settings, Settings › Workspace, auth bootstrap) light + dark + one reduced-motion shot.
Report lists every remaining `Spinner|LoadingState|Loading…|isLoading|isPending` usage + reason.

## Amendment 2 (2026-10-24, owner via coordinator, binding): public landing page
`/` for anonymous visitors → `pages/Landing.tsx` (lazy, no shell); signed-in `/` → `/home`.
Glass sticky navbar (logo, Features / How it works / Safety / FAQ anchors, theme toggle,
Log in ghost, Create account gradient) opening Radix Dialog modals (`?auth=login|register`,
focus trap, Esc, bottom sheet on mobile, same post-login routing as /login). `/login`,
`/register`, `/choose-role` stay full pages but share `features/auth/components/{LoginForm,
RegisterForm}.tsx` (one schema, one error handling). Sections: hero (display headline, two CTAs,
the interactive r3f scene — now its home — with static poster), "built for" strip, feature bento
with 3D art, How it works (3 steps, real product screenshots as WebP ≤ 200 kB in
`public/landing/`), safety/trust, FAQ accordion (Radix), final CTA, footer. No hype, no fake
testimonials/numbers/logos. Gates: LCP is text or preloaded poster, three chunk after first
paint and only on landing/auth, fonts preloaded, images lazy except poster, reduced motion →
poster, keyboard-navigable, AA (checker covers hero gradient pairs), SEO (`useDocumentMeta`,
OG image `public/landing/og.png`), explicit image sizes. Verify: shots light/dark 1440/390
(hero, bento, how-it-works, FAQ, footer, both modals, mobile sheet), 6 frames, reduced-motion
poster, Playwright login through the modal → /home, chunk table.

## Amendment 3 (2026-10-24, owner via coordinator, binding): heroes fit the visible UI
Launcher hero tile and Resume Dashboard start card (plus AuthLayout / landing heroes) must be
fully visible at 1440×900, 1366×768, 390×844, sidebar expanded and collapsed: no horizontal
scroll on `html` / `main`, illustration never clipped or overflowing, hero bottom ≤ 50 % of the
viewport on desktop (`min-h-[clamp()]` / `max-h`, no fixed px), full content width, text +
illustration grid on lg+, stacked with a scaled-down illustration on mobile; root-cause CSS
(overflow-hidden + radius on the surface, decorations clamped with inset inside a relative box,
`min-w-0`, no 100vw, `max-w-full` images, pointer-events-none glows); skeleton reserves the
same size. Verify with Playwright metrics → `after/hero-fit-*.png`.

## Review pass (2026-10-24, coordinator): two findings + polish of four plain pages
Ownership: another agent owns Landing*, features/landing, features/brand-3d, features/auth,
AuthLayout, public/3d/hero-scene*, index.html, vite.config.ts, package.json — not touched here.
1. Full-page dashboard capture looks shifted ~30 px left → measure `main` left/scrollLeft, fix if real.
2. Launcher loading → loaded must not shift (stat block min-h, non-wrapping labels, tip slot).
3. Polish Settings, editor form column, Version History, Job Target detail → `after/polish-*.png`.

Results:
- ✅ Finding 1: `main` left 256 / scrollLeft 0 / h1 left 288 / page-in transform = identity, before and after a
  full-page capture — no transform or scroll-container offset. Cause: a real horizontal overflow
  (cards in grids had `min-width: auto`, so a long unbreakable line widened the track — measured
  `/resume` at 390 px: scrollWidth 400 vs 390), which lets the window scroll sideways and slides the
  sticky topbar/content under the fixed rail in a capture. Fix at the root: `Card` gets `min-w-0`.
  Now scrollWidth == innerWidth on /resume, /home, /resume/my, targets, history, ats, ai-settings,
  new, editor, settings, profile at 390 and 1440; `shots.py` logs scrollX (0) for every shot;
  `after/resume-dashboard-*-1440.png` re-taken.
- ✅ Finding 2: stat cells are a fixed 62 px box (28 px value, 32 px two-line clamped label with
  `title`), tiles and skeleton tiles share `min-h-[18.5rem]`, stats use the full tile width (art only
  in the footer corner), tip card has a same-box placeholder while preferences load (in the
  skeleton grid and the loaded grid). `noshift.py`: hero, 3 tiles and tip — 0 px top and 0 px
  height delta at 1440 and 390, light and dark (`after/loading-launcher-*-{1440,390}.png`,
  `after/home-viewport-*.png`).
- ✅ Polish (before/after `after/polish-{settings,editor,version-history,job-target}-{before,after}-{light,dark}-{1440,390}.png`):
  Settings — pill rail in a card with gradient active pill (desktop) + scrollable pill row (mobile),
  section header band with gradient icon chip + one-line blurb, gradient switches (light; primary in
  dark for 3:1), Admin catalog rows with soft icon chips and a soft warning note. Editor — sticky
  section rail (xl) with "Sections" label, per-section icon chips (`sectionIcons.ts`), gradient
  active edge, form card header band (gradient icon chip, display title, entry count), roomier
  padding; editor skeleton follows. Version History — day pills with counts, gradient spine,
  change_source nodes (You / AI / System), AI versions on the soft gradient card, tabular version
  pill, display resume names; timeline skeleton follows. Job Target — soft-gradient header band
  (back link, display title, company + status + due pills, actions), clickable 6-step status
  stepper (gradient done/current, Rejected/Archived note), soft-gradient Tailored resume card,
  destructive-soft missing-skill pills, gradient activity spine; detail skeleton follows.
- ✅ Contrast 0 failures; `npm run build` green (index 352.7 / 105.3 kB gzip); identity.check
  soft-deleted again (06:51 UTC); :8097 / :5207 stopped.

## Checklist — identity pass (done before the pivot)
- ✅ Read plan §1/§7, DESIGN.md, theme-research.md, identity brief
- ✅ Private servers up; throwaway user + resume + ATS analysis + 6 job targets
- ✅ "Before" screenshots (pre-change) → `notes/screenshots/theme-identity/before/`
- ✅ Sidebar tokens (both themes) + Sidebar / ModuleSwitcher / rail / Sheet / tooltips
- ✅ Type scale (2xl 26 px, tighter tracking, `font-heading` 650), PageHeader brand eyebrow, StatCard 30 px tabular
- ✅ Brand gradient `.bg-hero` (hero-from / hero-to + hero-foreground / hero-muted), logo mark brand-600 / brand-400
- ✅ AppShell `ease-drawer`, Topbar blur, AI settings "Server default" select, no raw colours in scope
- ✅ Contrast checker extended (rail, hero, logo), 0 failures; `npm run build` passes

## Checklist — theme-modern
- ✅ Research → `notes/theme-research.md` §5 (46 refs; recommends indigo→violet→fuchsia, Bricolage, glossy 3dicons) + §6 v2 contrast matrix
- ✅ 19 CC0 3dicons PNG → 23 named WebP (480 + 240 px, 6–18 kB) in `public/3d/` + `LICENSES.md`
- ✅ Extra "before" shots served from a `git archive HEAD` export (Register, Profile, empty state, 404)
- ✅ Chunk table before (HEAD build): index 452.90 kB / 133.60 kB gzip, charts 434.10, pages 305.29/262.30/108.38, react 164.00 (`scratchpad/theme-identity/chunks-before.txt`)
- ✅ Tokens v2 (gradient family, soft gradient, glow, glass, skeleton, sidebar-glow), radius 12/16/20/24, Bricolage display + size-adjusted fallbacks, Inter Latin subset 352→108 kB (full file via unicode-range)
- ✅ Packages pinned: framer-motion 11.18.2, three 0.171.0, @react-three/fiber 8.18.0, @react-three/drei 9.122.0, @types/three 0.171.0 (dev)
- ✅ Primitives: gradient primary button (+ `solid`), fields with focus glow, glass dropdowns/popovers, glass scrim, pill tabs, Card variants (default/glass/gradient/soft), CardTitle display, StatCard counter (`AnimatedNumber`), EmptyState 3D slot (auto-mapped from the lucide icon), skeleton system
- ✅ Shell: glass topbar + TopProgressBar (`useIsFetching`), page-in transition, gradient active bar on the rail, auth pages lazy (main chunk 453 → 349 kB)
- ✅ 3D: HeroScene (r3f, lazy chunk 822 kB / 219 kB gzip ≤ 600), AuthHero3D poster-first with reduced-motion / <4 cores / WebGL fallback, poster rendered from the scene (`public/3d/hero-scene*.webp`)
- ✅ Auth layout v2 (3D hero, display headline, glass form card, gradient wordmark), launcher bento (hero tile + 3D module tiles + tilt + featured gradient border + launcher skeleton), 404, ATS ring (gradient stroke, spring fill, count-up), AI suggestion cards soft gradient edge, template picker tilt, dashboard start card 3D art
- ✅ Skeleton sweep across pages/features (14 feature skeleton files; every content-loading branch → matching composite; refresh keeps content); status spinners (editor autosave, automation running, run pipeline) → pulsing static icons; StatCard keeps its caption line while loading
- ✅ Loading shots (API held 1.5 s, client-side navigation): `after/loading-{launcher,resume-dashboard,my-resumes,editor,ats,version-history,ai-settings,settings-workspace,bootstrap}-{light,dark}-1440.png` + `loading-resume-dashboard-reduced-motion.png`
- ✅ Landing page + auth modals (`pages/Landing.tsx`, `features/landing/**`, shared `features/auth/components/*`, `?auth=` modals, bottom sheet on mobile, OG image compressed 555 → 175 kB); modal login → /home verified
- ✅ Contrast checker: landing pairs added; glass raised 72 % → 90 % so muted text + ring pass over the dark hero; 0 failures (302 gated pairs); §6 matrix in theme-research.md
- ✅ Page polish: Resume Studio / Profile / Settings / Job Apply inherit v2 through primitives (gradient primary, cards, pills, EmptyState 3D, skeletons); launcher mobile hero fixed
- ✅ After screenshots (131 files) reviewed: app pages light/dark 1440/390, login/register, switcher, rail, drawer, empty state, 404, profile, loading-*, hero frames (auth + landing), reduced-motion (login + landing + loading)
- ✅ docs/DESIGN.md v2 (tokens, type, shape, motion, 3D, loading rule, primitives, chunk table, landing/auth)
- ✅ Amendment 3 (hero fit): launcher hero moved out of the bento into a full-width band (`min-h-[clamp(10rem,26vh,15rem)]`, text + illustration grid on lg, stacked with a 112 px still on mobile, glow via inset radial layer, no negative offsets); module art clamped inside tiles; Resume Dashboard start card replaces the all-zero KPI row at the same height (no shift) as a grid; AuthLayout glows inset-based; stay-signed-in banner compacted (py-2.5). `hero_fit.py`: 16/16 pass — html/main scrollWidth == width everywhere; /home hero bottom 380/900 and 348/768, /resume start card bottom 383/900 and 383/768 (limit 384), mobile heroes fully visible (bottom 521 and 666 of 844); public `/`, `/login`, `/register` no overflow at all three sizes. Shots `after/hero-fit-*.png` (16)
- ✅ Cleanup: identity.check + identity.fresh soft-deleted (06:20 UTC; identity.check was restored temporarily for the hero-fit run); :8097 / :5207 stopped; :8000 / :5173 untouched

## Decisions
- Sidebar is a deep indigo-navy in both themes (light `#161d3b`, dark `#0b0e17`, one step under
  the canvas). New tokens `sidebar-muted`, `sidebar-section`, `sidebar-raised`. Worst rail pairs:
  text `sidebar-muted` on `sidebar-accent` 5.43:1 (light) / 5.53:1 (dark); UI `sidebar-primary`
  on `sidebar-accent` 4.32:1 / 5.09:1.
- `hero-to` moved from teal (#044f6a) to deep indigo-navy (#0a1f4b) so the gradient reads indigo.
- Job-Specific board: 8 columns get `minmax(11rem,1fr)` and scroll sideways instead of squeezing
  cards to "Pl…" at 1440 px.
- Tooltips/close buttons got optional `className` / `closeClassName` props (no new components).

- Chunk table after: index 351.9 / 105.0 kB gzip (was 452.9 / 133.6), HeroScene 822.4 / 219.5, motion 117.0 / 38.7,
  Landing 33.6 / 10.0, CSS 96.6 / 17.9 (was 71.5 / 13.1).
- Remaining non-button spinners: none. Status indicators (editor autosave, automation running, run
  pipeline) are pulsing static icons; ChooseRole keeps a spinner inside its role button (allowed).
- Follow-ups: the owner's :5173 Vite must be restarted to pick up the new Tailwind config; og:image
  needs an absolute URL at deploy time; `/` shows the landing skeleton briefly for a remembered
  device with no tab token.

## Blockers
- none

## Landing amendments (2026-10-24, landing agent)
- **Amendment 1 (full width):** every landing section background is edge to edge; content uses
  `features/landing/layout.ts` `LANDING_CONTAINER` (max 1440, px 5/8/12/16); navbar row uses the
  same container. Measured: at 1440 the hero container is 1440 wide (content 1312); at 1920 the
  container caps at 1440 (left 240) while sections span 1920; scrollWidth == innerWidth at 390,
  768, 1440, 1920.
- **Amendment 2 (hero fits first view):** `--nav-h` on the page root; hero `min-h: 100svh − nav −
  3rem` (max-h capped on ≥1280×700); headline `clamp(2.25rem, min(5vw+1rem, 7.4svh), 4.5rem)`;
  3D box `min(100%, 40rem, 100svh − nav − 7rem)`. Hero bottom 853/900, 721/768, 1033/1080.
- **Amendment 3 (light hero, premium 3D, responsive, PWA):** light hero on canvas + mesh + grid,
  dark keeps `.bg-hero`; both fade into the canvas (mask). HeroScene rebuilt (PBR, Lightformer
  env, ContactShadows, springs, ±6° parallax); poster re-rendered in place (hero-scene.webp 38 kB,
  -640 21 kB) and checked on /home and /login. Breakpoints 360→2560 verified (no h-scroll, no
  clipping). PWA: manifest + icons + vite-plugin-pwa 1.0.3 (precache 14 shell entries, /api
  NetworkOnly). AuthLayout copy now describes Resume Studio (auto-apply is off). Research in
  theme-research.md "Landing hero — light mode references".

## landing-perf (resumed) — 2026-10-24, landing-perf agent
Briefs: `notes/landing-perf-prompt.md` (A–D) + `notes/landing-perf-addendum.md` (0, E–G). Order 0 → G → A → B → C → F → E → D.
Private servers: API :8099 (venv, REDIS db 15, LLM mock), Vite :5221, preview :4201. Users perf.check (USER), perf.multi (USER+ADMIN).
Scripts + baselines: session scratchpad `…/scratchpad/theme-identity/landing-perf/` (renders.py / vitals.py "before" numbers
from the stopped agent are kept: renders.jsonl, vitals.jsonl; `base-1249/` = sources extracted from the 12:49 sourcemaps).

### 0. Tree triage (stopped agent's edits 12:40–13:04, diffed against the 12:49 sourcemap snapshot / HEAD)
- Tree was green when picked up: `tsc --noEmit` exit 0, `npm run build` OK (index 340.3 kB, Landing 30.8 kB).
- Kept (complete and coherent): ErrorBoundary.tsx (new; route + widget boundaries), router.tsx (RouteErrorBoundary per
  route chunk, Home lazy + LauncherRoute, launcher reload prefetch), ModuleRoute.tsx, modules/prefetch.ts (new; idle +
  intent prefetch, saveData aware), modules/resume/prefetchData.ts (new; complete), registry.ts (`prefetchData`),
  Home.tsx (narrow store selectors, idle prefetch of resume pages, hover data prefetch — complete, not half-edited),
  Topbar.tsx (memo + `FetchingBar` leaf owns `useIsFetching`), AppShell.tsx (memoised title + stable callbacks),
  Sidebar.tsx (memo + hover data prefetch), resume-studio/api.ts + ats/api.ts (shared query options, keepPreviousData),
  workspace/api.ts (catalog staleTime 5 min), JobTargets.tsx (memo rows/board/table, startTransition view switch),
  MyResumes.tsx (startTransition filters), ResumeEditor.tsx (memo PreviewPane from a debounced + deferred copy, stable
  section callbacks), SectionList.tsx (memo), AnimatedNumber.tsx + ScoreRing.tsx (spring writes to the DOM, no state per
  frame), ChartCard.tsx + ResumeScoreHistoryChart.tsx (widget ErrorBoundary), authModal.ts (new; modal hook + lazy dialog
  chunk + intent prefetch), Landing.tsx (lazy AuthDialog), LandingHero/Nav/Sections (memo, authIntent,
  content-visibility on below-fold sections), AuthLayout.tsx + AuthDialog.tsx (idle Home prefetch), heroShared.tsx,
  LandingSkeleton.tsx, loadLanding.ts, AuthHero3D.tsx (paint + visibility + interaction gates), index.html (no-flash theme
  script + background), stores/auth.ts (`hasSessionHint`), queryClient.ts (dev-only `window.__queryClient`),
  LoginForm/RegisterForm.
- Finished: Sidebar.tsx duplicated doc comment fixed. Reverted: nothing.
- Stale servers of the stopped agent on :5221 / :4201 stopped (owner's :5173 / :8000 untouched).

### Checklist
- ✅ 0 triage (above)
- ✅ G logout → landing. Measured before: account-menu sign-out went `/home → /login` (UserMenu hard-coded
  `navigate('/login')`); the `/choose-role` trap = a `pendingRoleSelection` surviving in sessionStorage
  (`jobpilot.auth`) made ProtectedRoute redirect `/` → `/choose-role` (probe: password step, leave the chooser, visit
  `/` → `/choose-role`). Fix: one `logout(reason)` in `stores/auth.ts` (revoke with 4 s timeout + skipAuth/skipRefresh,
  clears token/user/roles/pending/sessionRemembered/session hint, `queryClient.clear()`, `persist.clearStorage()`,
  BroadcastChannel + storage-event cross-tab, idempotent, toasts); `signOutReason` (memory) routes: user/remote → `/`,
  expired → `/?auth=login` + `state.from`; pending selection gets `createdAt` and is dropped after 5 min on load; `/`
  never redirected to /choose-role; /choose-role without pending → `/`. After: single + multi `/home → /`, reload `/`,
  no /choose-role in 12 frames; expiry `/resume/targets → /?auth=login` (from kept, modal open, toast); two-tab B
  `/home → /`. Shots `after/logout-{landing-signed-out,session-expired,multi-reload}.png`. Backend revoke already
  complete (no change).
- ✅ A reload "blue screen". Root cause (confirmed on the stopped agent's 12:36 build, frames in scratch
  `frames-before/`): the old `LandingSkeleton` painted the hero region with `.bg-hero` + `hero-foreground/10` bars in
  BOTH themes (light frame 10 = dark indigo block), and with no pre-JS theme resolution the dark theme painted the light
  canvas for ~1 s (frames 1–9). Fix (mostly by the stopped agent, kept): skeleton rendered from the hero's own
  constants (`heroShared.tsx`: section, backdrop mesh/band, grid, poster box, strip), no-flash `<script>` + `html`
  background in `index.html`, landing rendered without waiting for the bootstrap when there is no session hint,
  Landing chunk requested from the router at boot and from the skeleton on mount. Finished here: the text-shaped bars
  were invisible in light mode (`bg-skeleton` is not a Tailwind colour) and overlapped on the 1.02-leading headline in
  dark → hard-stop gradient band from `--skeleton` / `hero-foreground/12` over the middle 64 % of each line. Measured
  (Landing chunk held, then released): nav / hero / text column / headline / 3D box / strip deltas 0 px at 1440 and 390,
  light and dark; CLS 0 on the preview build. Frames (Fast-3G-like + 4× CPU, CDP captures ~100 ms):
  `after/reload-frames-{light,dark}-01…15.png` — canvas colour correct from frame 1 in both themes, light skeleton on
  the light mesh, then the hero.
- ✅ B light-mode bento. The featured tile was already on the soft gradient in light (`.bg-hero` only under `.dark`) when
  picked up; proved with a rendered-pixel sweep (`contrast_sweep.py`: every element owning text, computed colour
  composited over the backdrop pixels under its glyphs with the text hidden, worst 5 %; gradient-clipped text from its
  own ink pixels): 418 elements (light/dark × 1440/390), 0 below 4.5:1. Worst per theme: light 5.20 (muted copy on the
  soft-gradient tile + Safety panel), dark 6.49 (white on the gradient "Create account"). Audit of every `bg-hero` /
  `bg-gradient-brand` / dark surface: hero, featured tile, final CTA use ON_HERO / hero tokens under `.dark` only; no
  dark-on-dark left. `theme-contrast.py`: nested composites in `resolve()`; light mesh pairs (under-copy tint 14 %
  gated — 10.8 % measured — peaks 24 %/stacked as info), pill on the stacked peak, tile sub-cards card/80 on both soft
  ends, dark bloom 20 % (band) / 10 % (chips) gated with the 32 % corner peak as info, skeleton bars as info →
  failures 0 (330 gated pairs). Shots `after/landing-bento-{light,dark}-1440.png`.
- ✅ C auth modals (implemented by the stopped agent, verified + kept): `AuthDialog` `sm:max-w-lg md:max-w-xl`
  (576 px at 1440), 32 px padding (24 px sheet), inputs = form width (510 px), Sign in / Create account = default
  gradient button, white text, 48 px, full width, `loading`, hover lift, `dark:shadow-glow`; switch links in `primary`
  (#4150d7 / #92a8ff); register puts password + confirm side by side on md+ (single full-name field, so no first/last
  split). Same forms on `/login` + `/register`. Checks (`auth_modal_check.py`): focus stays in the dialog for 20 Tabs,
  Esc closes + removes `?auth=` + returns focus (Log in ≥ 640, menu button < 640), `?auth=` deep link opens on load,
  bottom sheet at 390 flush (x 0, width 390, bottom 844). Modal text contrast 0 failures (worst 5.86 light / 6.59
  dark). Shots `after/auth-modal-{login,register}-{light,dark}-{1440,390}.png`.
  G addendum: expired-modal sign-in returns to `/resume/targets` (deep link kept). Re-run after F: all G cases green.
  Note for successors: the API's auth limiter is 10 req/min/IP (`AUTH_RATE_LIMIT_PER_MINUTE`); my private :8099 runs
  with 1000 and Redis db 15 flushed, otherwise Playwright suites trip it (shows up as a /login flash or a stuck login).
- ✅ F choose-role v2: `pages/ChooseRole.tsx` on the shared `AuthLayout` (new `heroTitle`: "Choose how you want to work
  today."), glass card, account strip, role options as `role="radiogroup"` / `role="radio"` cards (icon chip, name,
  one-line description, gradient border + gradient check when selected, roving tabindex; arrows/Home/End move, Enter
  continues), preselects the remembered role, "Remember my choice on this device", gradient "Continue as <role>"
  (48 px, `loading`), quiet "Not you? Sign out" (→ `logout('user')` → `/`). Geometry shared through new
  `components/layout/authShell.ts` (grid, hero, card, copy); `AuthSkeleton` rebuilt on it with `variant="roles"`
  (one 72 px row per pending role) for the /choose-role Suspense fallback + bootstrap. Measured (auth chunk held):
  card / role list / hero headline deltas 0 px at 1440 and 390, light and dark. Keyboard: ArrowDown moves
  aria-checked Admin → User with focus, Enter lands on /home. Shots `after/choose-role-{light,dark}-{1440,390}.png`,
  `after/choose-role-{one-role,three-role}-light-1440.png`.
- ✅ E image/text collisions. `overlap_check.py`: image box vs the client rects of every text node in the composition
  (+ the featured tile's sub-cards/chips as blocks), 9 widths (360–1920) × light/dark, 9 compositions (landing hero,
  featured bento tile, other bento tiles, auth hero, choose-role hero, launcher hero, module tiles, Resume Dashboard
  start card, EmptyState). Before: featured tile art over the "Version history" card at 1366/1440/1920 (10 328 /
  13 404 px²) and the auth / choose-role 3D box over the headline at 1366×768 (329 / 1 879 px²); everything else 0.
  Fixes: featured tile → copy | art grid tracks (`sm:[1fr_11rem]`, `lg:[1fr_14rem]`, art `object-contain`, hidden
  < 640), sub-cards and chips below; AuthLayout art → its own flex-1 row between brand and copy
  (`AUTH_HERO_ART` / `AUTH_HERO_ART_BOX` in authShell, skeleton mirrors it; body lost `pt-[min(40vh,24rem)]`).
  After: 0 overlaps everywhere. Shots `after/overlap-<place>-<w>-<theme>.png`. Choose-role skeleton deltas re-measured: 0.

### P0 (coordinator, 2026-10-24) — launcher "Resume Studio" tile did nothing — ✅ FIXED (live on :5173 via HMR)
- Root cause (reproduced on :5221 as admin, dark, 1440: click in the tile body hit `<span>Unsaved drafts</span>`, URL
  stayed `/home`, no console error): NOT the stopped agent's prefetch code. The v2 tile redesign (ModuleArt) made the
  tile's header row `relative` (and the stats + footer rows too, to sit above the 3D art). The title link's stretched
  overlay (`after:absolute after:inset-0`) therefore resolved against the header row instead of the `<li>`: only the
  title strip was clickable; the stats area, the "Open →" pill (a `<span>`) and the rest of the card swallowed clicks.
- Fix (`pages/Home.tsx`): header row no longer `relative` (overlay resolves against the card), overlay `after:z-[1]`
  above the stats/footer rows, pin / admin Enable / admin link stay `relative z-10` above it; Space activates the tile
  link like Enter.
- Proof (`p0_check.py`, 16/16, no console/page errors): tile body click → `/resume` + Resume Dashboard heading;
  "Open" pill → `/resume`; Enter and Space on the focused tile → `/resume`; pin toggles aria-pressed and stays on
  `/home`; Job Apply "Enable" (admin) → `/settings?section=admin`; module switcher → Resume Studio and → All modules;
  every sidebar link (8) lands on its href. Topbar / Sidebar / AppShell edits by the stopped agent: navigation intact.

### Modal form scale (coordinator, owner screenshot) — ✅
- One scale for both modals and the `/login` `/register` pages (`features/auth/components/authFormStyles.ts`):
  48 px fields, 16 px text, 16 px side padding (rounded-xl), 14 px semibold labels 8 px above, 20 px between
  fields, 48 px full-width gradient submit. PasswordInput toggle spans the field height (pr kept after caller px).
- Header: new `components/layout/AuthBrand.tsx` (28 px logo mark + wordmark) in the modal and the page card (skeleton
  mirrors it); title 28 px → 30 px sm+; 15 px helper line (`AUTH_DESCRIPTION`). Dialog close button via new optional
  `closeClassName` on `DialogContent`: 20 px from the visible corner, 36 px target.
- Register: first + last name (last optional, joined into `full_name`) side by side on md+, email / password /
  confirm full width, strength meter (4 segments, `role="meter"`, Weak/Fair/Good/Strong from the backend policy +
  12 chars or mixed case & symbol) and the policy checklist (8 chars, a letter, a digit), terms line, 48 px button.
- Checks (`auth_scale_check.py`, 16 states = 2 modes × modal/page × light/dark × 1440/390): all PASS — inputs 48/16/16,
  labels 14/600, gaps 20, submit 48 = form width, no visible element outside the form column, no horizontal
  overflow, close 20/20/36, title 28–30, helper 15. Register-modal contrast sweep 0 failures (worst 5.86 / 6.58).
  Shots `after/auth-modal-{login,register}-{light,dark}-{1440,390}.png`, `after/auth-page-{login,register}-{light,dark}-{1440,390}.png`.

### Rename "Resume Dashboard" → "Dashboard" (coordinator) — ✅
- `components/layout/navigation.ts` (Resume Studio sidebar item; the topbar breadcrumb reads the nav label →
  "Resume Studio › Dashboard"), `pages/resume/ResumeDashboard.tsx` page title + document title ("Dashboard · JobPilot AI").
  Route `/resume`, component / file names unchanged; the Settings › Workspace picker and launcher list modules, not
  this page (nothing to rename); no `frontend/tests`. Remaining hits are code comments only. Verified: sidebar active
  item "Dashboard", breadcrumb "Resume Studio Dashboard", h1 "Dashboard"; P0 suite re-run 16/16.
  Shot `after/rename-dashboard-light-1440.png`.

### Register modal fit (coordinator review) — ✅
- Short-viewport tiers (`authFormStyles.ts`, AuthDialog, RegisterForm, StaySignedInField): 801–900 px tall → 16 px
  field gaps, 28 px card padding, 16 px dialog gaps, tighter strength block; ≤ 800 px → 12 px gaps, 24 px padding,
  44 px fields/submit, "Stay signed in" helper hidden; terms line shortened to one line. `max-h-[92svh]` kept as last
  resort. Measured (`register_fit.py`): 1440×900 scrollHeight 791 = clientHeight 791 (footer bottom 817 < dialog 846),
  1366×768 705 = 705. Scale check re-run 16/16 (gap expectation 20 / 16 / 12 by viewport height).
  Shots `after/auth-modal-register-{light,dark}-1440.png`, `after/auth-modal-register-light-1366x768.png`.

- ✅ D React performance (closing). Render counts (renders.py, dev build, same scripted interactions as the stopped
  agent's baseline): landing 808→545, home 306→86, Resume Dashboard 530→141, Job targets 1069→427, My Resumes
  7612→1094 (new scenario, 9 resumes), editor 10711→3414. Added here: My Resumes ref-stable actions + memo
  `ResumeCardItem` + memo `ResumeFilters` + `useDeferredValue` filter; landing skeleton paints the preloaded poster
  (LCP no longer waits for the Landing chunk). Vitals (preview, 4× CPU): same-session pair `/` before 2492 ms LCP /
  4549 ms TBT vs after 992 / 131 (after3) — the 5-run before-build re-measure did not complete (watchdog), so the
  baseline is the stopped agent's 12:38 run + the one same-session "before-now" run. Chunks: index 347.0 kB, Landing
  30.9 kB. Gates: tsc 0, build green, contrast 0 failures. Users soft-deleted; :5221/:4201/:8099 stopped.
