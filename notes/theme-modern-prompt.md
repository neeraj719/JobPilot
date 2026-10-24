# theme-modern — full redesign: modern, Gen-Z energy, 3D accents, still professional

This brief **supersedes** `notes/theme-identity-prompt.md`. You are **theme-identity** (keep the
name and the progress file, add a "pivot" entry). Read `notes/resume-studio-plan.md` §1 and §7,
`docs/DESIGN.md`, `notes/theme-research.md`, then this file. Nobody else edits the tree. Do not
commit.

## Why the pivot

The owner saw the calm token pass and said it does not look like a new theme. They now want the
**whole website** to feel modern with a Gen-Z vibe and 3D elements, while staying professional —
a product their friends would screenshot, not a bank. Think Linear's launch pages, Arc, Raycast,
Vercel's dashboard, Notion's marketing, Duolingo's energy with Stripe's discipline. Data views
stay legible; the energy goes into surfaces, type, motion and illustration, never into charts
and tables.

## 1. Research again, for this direction (write before you design)

Collect at least 15 references with ratings/likes/dates (WebSearch/WebFetch), covering:
* Dribbble / Behance top shots (last 2 years, most liked): "gen z dashboard", "3D dashboard",
  "glassmorphism SaaS", "bento grid dashboard", "job board 3D illustration", "resume builder
  landing 3D", "career app dark mode", "AI SaaS dashboard".
* Shipped products rated highly for modern UI: Linear, Arc, Raycast, Vercel, Notion, Cal.com,
  Superhuman, Clay, Framer, Spline's own site, Duolingo, Revolut/Monzo (fintech Gen-Z), Teal.
* 3D sources with a licence we can ship: **3dicons.co (CC0)**, **Shapefest (free licence)**,
  Spline community scenes (check licence per scene), Icons8 3D (link-back licence),
  Figma Community 3D packs with CC0. Record the licence of every asset you take and store the
  texts under `frontend/public/3d/LICENSES.md`.
* Motion/3D libraries: `framer-motion` (micro-interactions), `three` + `@react-three/fiber`
  + `@react-three/drei` (one interactive hero), Lottie (`lottie-react`) as a lighter option,
  pure CSS 3D (perspective tilt, layered shadows). Decide with a performance budget in mind.

Append to `notes/theme-research.md` a new section "Modern / Gen-Z direction": the table, the
8–10 shared traits of the top-rated work (expect: bento grids, large friendly radii 16–24 px,
bold display type with a humanist body font, vivid gradient accents on a calm base, glass
surfaces used sparingly, dark mode as a first-class citizen with glows, 3D illustrations on
empty states and heroes, spring micro-interactions, generous whitespace, high contrast), and
the direction you choose with reasons.

## 2. Design system v2 (tokens first, then surfaces)

Keep `docs/DESIGN.md` as the single source and rewrite it for v2. Keep every existing token
name working (pages depend on them); change values and add:
* **Palette:** keep indigo as the brand root but add a vivid accent gradient family
  (indigo → violet → cyan, or indigo → fuchsia — choose from the research) as `gradient-brand`,
  `gradient-brand-soft`, plus `glow-brand` for dark mode. Neutrals stay calm. Every text pair
  still passes WCAG AA — extend `notes/theme-contrast.py`, 0 failures in both themes.
* **Type:** a display font for headings with personality (Space Grotesk, Sora, Plus Jakarta
  Sans, Manrope, Bricolage Grotesque — pick from the research; self-host the variable file
  under `frontend/public/fonts` with its licence) and Inter for body/data. Bigger, bolder
  titles; tabular numerals in data.
* **Shape:** radius scale up (cards 16 px, hero surfaces 24 px, pills full), layered soft
  shadows, optional 1 px inner highlight on dark surfaces, glass (`backdrop-blur` + translucent
  surface) for the topbar, the module switcher and floating panels only.
* **Motion:** `framer-motion` allowed (pin it). Spring enter transitions for cards and lists
  (stagger ≤ 60 ms), hover lift + tilt on launcher cards (CSS `perspective`), page transitions
  ≤ 200 ms, animated number counters on stat cards, all behind `prefers-reduced-motion`.
* **3D:** 
  - Pre-rendered 3D illustrations (CC0 / free-licensed PNG/WebP, ≤ 150 kB each, with
    `srcset` and `loading="lazy"`) on: the launcher module cards (one per module), the sign-in
    hero, the Resume Dashboard "start" card, and every `EmptyState` (map a small set of 3D
    icons to empty-state kinds).
  - **One** interactive 3D scene, lazy-loaded with `React.lazy` + `Suspense` and never in the
    main chunk: the sign-in hero (a floating document / paper-plane / abstract shape in brand
    colours, slow idle rotation, mouse parallax) built with `@react-three/fiber` + `drei`, with
    a static image fallback for reduced-motion, low-end devices (`navigator.hardwareConcurrency
    < 4`) and WebGL failures. Budget: the three chunk ≤ 600 kB gzip, loaded only on `/login`,
    `/register`, `/choose-role`.
  - CSS 3D tilt on launcher cards and the resume template picker.
* **Dark mode first-class:** tinted dark surfaces, brand glow behind heroes, gradient borders
  on the active module card; light mode equally finished.

## 3. Apply to the whole product

* **Sign-in / Register / Choose role (`components/layout/AuthLayout.tsx`, pages):** split hero
  with the interactive 3D scene, display headline, gradient wordmark, glass form card.
* **Launcher (`pages/Home.tsx`):** bento layout — a hero tile with greeting + gradient + 3D
  illustration, module tiles with their 3D icons, live numbers, pinned state, "coming soon"
  and "switched off" states still clearly distinct, keyboard navigation preserved.
* **App shell (`components/layout/**`):** dark indigo sidebar (from the previous brief) with
  gradient active indicator; glass topbar; module switcher as a floating glass panel; the
  collapsed rail; the mobile sheet.
* **Resume Studio pages** (`pages/resume/**`, `features/resume*/**`, `features/ats/**`,
  `features/ai-providers/**`): new card/surface styles, display headings, 3D empty states,
  animated stat counters, template picker with tilt, the ATS score ring with a gradient stroke
  and a spring fill, suggestion cards with soft gradient borders for AI content. The resume
  **paper preview stays white and print-like.**
* **Job Apply pages** (switched off today, but style them: Dashboard, Jobs, Queue,
  Applications, Interviews, Companies, Automation, Emails), **Profile, Settings, Not found**.
* **Shared primitives** (`components/ui/**`, `components/common/**`): button (gradient
  primary variant, soft, ghost, icon), input/select/textarea (rounded, focus glow), card
  (default, glass, gradient-border), badge, tabs (pill style), table (legible, zebra off, sticky
  header), dialog/sheet (glass scrim), tooltip, toast, StatCard (counter), EmptyState (3D
  illustration slot), skeletons with shimmer.
* Grep and replace remaining hard-coded colours everywhere
  (`grep -rn "bg-\(green\|red\|amber\|violet\|sky\|indigo\|slate\|gray\)-" frontend/src`).

Performance and quality gates: Lighthouse-style sanity — main chunk not larger than today
(≈450 kB), fonts preloaded, images lazy, no layout shift from fonts (`font-display: swap`
plus size-adjust fallbacks), 60 fps hover/tilt (transform/opacity only), reduced motion
respected everywhere, keyboard focus visible on glass, AA contrast on glass surfaces
(measure against the real backdrop). No decorative charts. Accessibility of the 3D canvas:
`aria-hidden`, text alternative beside it.

## 4. Verify

* `npm run build` passes; print the chunk table before/after; contrast checker 0 failures.
* Private servers: backend `.venv/Scripts/python.exe -m uvicorn app.main:app --port 8097`
  with `REDIS_URL=redis://localhost:6379/13`, Vite `--port 5207`, both with the Bash tool's
  `run_in_background: true`; Playwright scripts written with the Write tool to
  `scratchpad/theme-identity/`, `page.set_default_timeout(15000)`, every Bash call with an
  explicit timeout ≤ 300000 ms. Throwaway user `identity.check@jobpilot.ai` with one resume
  from text and one ATS analysis; soft-delete at the end; stop your servers.
* **Before** shots first (the current calm theme), then **after**, light and dark, 1440 and
  390 px: Login, Register, Home launcher, Resume Dashboard, My Resumes, editor, ATS Optimizer
  with results, Job-Specific Resumes, AI Model Settings, Settings › Workspace, switcher open,
  collapsed rail, an empty state, Profile. `notes/screenshots/theme-identity/{before,after}/`.
  Also a 3-second screen recording or 6 frames of the login hero to prove the 3D scene moves,
  and one shot with reduced motion showing the static fallback. Review every shot and fix
  what looks wrong before reporting.
* Keep `notes/theme-identity-progress.md` updated.

## 5. Report
1. The direction in five lines and the three strongest references with ratings.
2. Fonts, 3D assets (source + licence), npm packages added (pinned), token changes.
3. Chunk table before/after, contrast summary, reduced-motion behaviour, build result.
4. Screenshot paths and the five most visible before/after pairs.
5. Anything unfinished and why; pages you consider still too plain.
