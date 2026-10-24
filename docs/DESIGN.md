# JobPilot design system — v2 "Indigo Pulse"

v2 keeps the v1 "Calm Indigo" token system (calm neutrals, one indigo root, AA everywhere) and
adds identity on top: a vivid **indigo → violet → fuchsia** gradient used with discipline, a
display face with personality (**Bricolage Grotesque**) over **Inter**, larger friendly radii,
glass on floating chrome only, spring micro-interactions, a dark indigo navigation rail, CC0 3D
illustrations, one interactive 3D scene, and shimmer skeletons for every loading state.
Data views (tables, charts, scores) stay calm and legible — the energy lives in surfaces, type,
motion and illustration.

The theme is a token system. Pages never pick colours, sizes or shadows of their own: they use
the semantic tokens below (through Tailwind classes) and the shared primitives in
`frontend/src/components/ui` and `frontend/src/components/common`. Change the look in one place,
every page follows.

* Why, references and ratings: [`notes/theme-research.md`](../notes/theme-research.md) §1–3 (v1)
  and §5 (v2 "Modern / Gen-Z direction").
* Contrast matrix (every text/background pair, both themes, WCAG 2.2 + APCA):
  [`notes/theme-contrast.py`](../notes/theme-contrast.py) — `backend/.venv/Scripts/python.exe -I
  notes/theme-contrast.py matrix` exits 1 on any failing pair (it reports `failures: 0`, plus the
  worst rail pairs); `… css` prints the token blocks for `index.css`.
* Source files: `frontend/src/index.css` (token values — `:root` light, `.dark` dark — base
  styles, `.bg-hero`, `.glass`, `.border-gradient*`, `.text-gradient-brand`, `.tilt`, `.shimmer`),
  `frontend/tailwind.config.ts` (token → class mapping, type scale, radii, shadows, motion),
  `frontend/index.html` (font preloads), `frontend/public/fonts/` (Inter + Bricolage, SIL OFL),
  `frontend/public/3d/` (illustrations + `LICENSES.md`), `frontend/src/lib/score.ts`,
  `frontend/src/features/dashboard/chart-theme.ts`, `frontend/src/features/brand-3d/`.

**Token names are a contract.** Never rename or remove one (pages use them directly); change
values, or add a new token.

## 1. Colour

All values are HSL triplets (`--primary: 234 65.1% 54.9%`) so Tailwind opacity modifiers work
(`bg-primary/10`). Designed in OKLCH, converted, and checked on the rounded values the browser
paints (the hex in the `index.css` comment).

### 1a. Surfaces and text (unchanged from v1)

| Token (class) | Use | Light | Dark |
|---|---|---|---|
| `background` | Page canvas, one step darker than cards | `#f6f7fa` | `#11141a` |
| `card` / `surface-1` | Cards, panels, inputs | `#ffffff` | `#181b22` |
| `popover` | Menus, dialogs | `#ffffff` | `#1e2129` |
| `surface-2` | Inset wells: table header, empty states, board columns | `#f4f6f8` | `#15181e` |
| `surface-3` | Pressed / selected fill, meter tracks | `#eaedf2` | `#272b33` |
| `muted` / `accent` / `secondary` | Neutral fills / hover fill / secondary button | — | — |
| `foreground` / `muted-foreground` | Primary / secondary text | `#121721` / `#5f6571` | `#eef0f4` / `#b5bbc5` |
| `border` / `input` / `ring` | Hairline (decorative) / control boundary ≥ 3:1 / focus ≥ 3:1 | `#e2e4e9` / `#888c95` / `#5d74f6` | `#2e323a` / `#717681` / `#8097fe` |
| `overlay` | Dialog / sheet scrim (35 % / 55 % + blur) | `#121721` | `#010203` |

### 1b. Brand

| Token | Use |
|---|---|
| `primary` / `primary-foreground` | Links, selected states, focus, soft buttons. Light `#4150d7` + white, dark `#92a8ff` + navy. |
| `brand-50 … brand-950` | Raw indigo scale (illustration, the logo tile: `bg-brand-600` light / `bg-brand-400` dark). |
| **`gradient-from` / `-via` / `-to`** | The brand gradient `#4150d7 → #7335d0 → #ae1599`, identical in both themes, **text-safe**: white (`gradient-foreground`) is ≥ 6.2:1 on every stop and midpoint. Class `bg-gradient-brand`. Used by the primary button, the launcher's featured border, the active-rail bar, the refresh bar. |
| `gradient-text-from/-via/-to` | Gradient glyphs (`.text-gradient-brand`): light = the stops above (≥ 5.8:1 on canvas/card); dark = `#a9bcff → #c3a5f9 → #f1a1ce` (≥ 8.2:1). |
| `gradient-soft-from` / `-to` | Soft gradient panel (`bg-gradient-brand-soft`, `.border-gradient-soft`) for AI content and tips; foreground, muted and primary text pass on both ends. |
| `glow-brand` | Glow colour, only at low alpha (`shadow-glow`, blurred blobs behind heroes, the field focus halo). Light `#5d74f6`, dark `#8f6ffb`. |
| `glass` / `glass-border` | Translucent surface for `.glass` (90 % + 16 px blur — the lowest opacity at which muted text and the focus ring pass over the dark hero). Text on glass is measured on its real backdrops (canvas and a card under it). |
| `hero-from` / `hero-to` / `hero-foreground` / `hero-muted` | `.bg-hero`: the deep indigo mesh behind the launcher hero tile, the auth hero and the landing hero; identical in both themes; copy ≥ 10:1 / ≥ 7:1. |

### 1c. Navigation rail (dark indigo in both themes)

| Token | Light | Dark | Use |
|---|---|---|---|
| `sidebar` | `#161d3b` | `#0b0e17` | Rail surface (dark: one step under the canvas) |
| `sidebar-foreground` | `#d9ddec` | `#cdd0db` | Inactive labels |
| `sidebar-muted` | `#a8b0cb` | `#9ea4b8` | Icons, captions ("Module") |
| `sidebar-section` | `#a9bcff` | `#a9bcff` | Section titles (small caps) |
| `sidebar-accent` / `-foreground` | `#2a3565` / `#f9fafe` | `#212a53` / `#f5f7fc` | Active pill (hover = `/60`) |
| `sidebar-primary` → `sidebar-glow` | `#8097fe` → `#f1a1ce` | same | Active icon; the active bar is a gradient between them |
| `sidebar-raised` | `#20284b` | `#141927` | Module switcher trigger, rail tooltips (`RAIL_TOOLTIP`) |
| `sidebar-border` / `sidebar-ring` | `#2a3250` / `#a9bcff` | `#1e2231` / `#8097fe` | Hairlines / focus on the rail (`RAIL_FOCUS`) |

Worst rail pairs: text `sidebar-muted` on `sidebar-accent` 5.43:1 (light) / 5.53:1 (dark);
UI `sidebar-primary` on `sidebar-accent` 4.32:1 / 5.09:1. Everything on the rail uses only
these tokens (`components/layout/navigation.ts` exports `RAIL_TOOLTIP` / `RAIL_FOCUS`).

### 1d. Status, AI, charts, scores, skeleton

* **Status** `success` / `warning` / `destructive` / `info` — solid `x` + `x-foreground`, soft
  `x-soft` + `x-soft-foreground` (pills, alerts, toasts). Status colour always travels with a
  label or icon. `ai` / `ai-soft` marks AI-made content (not a status).
* **Charts** `chart-1 … chart-6`: fixed order, legends + direct labels, never status colours.
* **Scores** only through `lib/score.ts` (`scoreTone`, `SCORE_TEXT`, …). The ATS ring paints its
  tone as a gradient of itself (tone → tone/55 %) — meaning stays semantic.
* **Skeleton** `skeleton` (base) / `skeleton-highlight` (the shimmer band): light `#e8ebf1` /
  `#f9fafd`, dark `#24282f` / `#323740`.

## 2. Typography

| Role | Face | Class | Size / line | Tracking | Weight |
|---|---|---|---|---|---|
| Display (auth/landing hero, launcher greeting) | Bricolage | `font-display text-4xl…5xl` | 36–48 | −0.03em | 600–650 |
| Page title (`PageHeader`, every `h1`) | Bricolage | `text-2xl sm:text-3xl font-heading` | 26 → 30 | −0.025 / −0.028em | 650 |
| Card title (`CardTitle`), empty-state title, module names | Bricolage | `font-display text-base…lg` | 16–18 | tight | 600 |
| Eyebrow (string `PageHeader eyebrow`) | Inter | `text-2xs uppercase tracking-[0.08em] text-primary` | 11 / 16 | +0.08em | 600 |
| Section / dialog title | Inter | `text-lg`, `text-xl` | 18, 20 | −0.013, −0.017em | 600 |
| Body / UI | Inter | `text-sm` | 14 / 20 | −0.003em | 400–500 |
| Caption, table header | Inter | `text-xs`, `text-2xs` | 12, 11 | +0.005, +0.06em | 500–600 |
| KPI figures | Inter | `text-3xl font-heading tabular-nums` | 30 | −0.028em | 650 |

Data (tables, scores, money, dates) stays in Inter with `tabular-nums`. Fonts are self-hosted,
preloaded, `font-display: swap`, with size-adjusted local fallbacks (`InterFallback`,
`BricolageFallback`) so the swap causes no layout shift.

## 3. Shape, depth, glass

* **Radius** (`--radius` 12 px): `rounded-3xl` 24 hero surfaces (launcher hero, auth card) ·
  `rounded-2xl` 20 bento tiles, dialogs, empty states · `rounded-xl` 16 cards, menus, popovers ·
  `rounded-lg` 12 buttons, inputs, selects · `rounded-md` 10 small controls · `rounded-full`
  pills, tabs, avatars.
* **Depth:** hairline borders first; `shadow-xs` cards, `shadow-sm` raised, `shadow-lg` menus /
  floating panels, `shadow-xl` dialogs. Dark surfaces add `shadow-highlight` (1 px inner top
  highlight). `shadow-glow` = brand glow for the primary button hover and the featured tile.
* **Glass (`.glass`) is for floating chrome only:** the topbar, dropdown menus and popovers, the
  auth form card, `Card variant="glass"` over imagery. Never for content cards or tables.
* **Card variants:** `default` · `glass` · `gradient` (1 px brand-gradient border — the featured /
  active item) · `soft` (soft gradient panel + soft gradient border — AI content).
* **Focus:** 2 px `ring` everywhere; fields add a soft `glow-brand` halo (6 px at 16 %). On the
  rail the ring is `sidebar-ring` with its gap in the rail colour.

## 4. Motion

* Durations: 150 ms hover, 180–200 ms open/close and route change, 420 ms enter.
* Curves: `--ease-out` (default), `--ease-spring` `cubic-bezier(.34,1.36,.64,1)` for things that
  arrive, `--ease-drawer` for the rail.
* Classes: `animate-page-in` (route change, keyed on the path in `AppShell`), `animate-rise-in`
  + `.stagger` with `style={{'--i': n}}` (≤ 50 ms per step, capped at 10), `animate-float`
  (illustrations), `.tilt` (CSS 3D tilt; JS sets `--tilt-x/-y/--lift` from the pointer — launcher
  tiles), `progress-bar-indeterminate` (refresh bar).
* `framer-motion` 11.18.2 (own `motion` chunk, lazy pages only): spring fill + count-up of the
  ATS ring, animated stat counters. Never in the main chunk.
* Transform/opacity only (60 fps). `prefers-reduced-motion: reduce` collapses every transition
  and animation (global rule), turns skeleton shimmer into a slow pulse, stops tilt and float,
  and swaps the 3D scene for its poster.

## 5. 3D

* **Illustrations** (`public/3d/*.webp`, 480 px + `-240` variant, 6–18 kB each, CC0 3dicons
  "gradient / dynamic" + our own hero still; sources and licences in `public/3d/LICENSES.md`):
  `module-resume|apply|insights|default` (launcher tiles), `empty-<kind>` (`document, folder,
  search, target, calendar, mail, bell, ai, rocket, lock, clock, settings, profile, trophy, chart,
  send, briefcase, star`). Always `srcset`, explicit size, `loading="lazy"`, `alt=""` +
  `aria-hidden` (decorative; the text beside carries the meaning).
* **`EmptyState`** picks the illustration from its lucide `icon` (`ART_FOR_ICON`) or an explicit
  `art` prop; `art="none"` keeps the plain icon chip.
* **One interactive scene** (`features/brand-3d/HeroScene.tsx`, three 0.171 + @react-three/fiber
  8.18 + drei 9.122): a floating resume, a paper plane and glossy brand shapes, idle float + pointer
  parallax, colours read from the CSS tokens. Mounted only through `AuthHero3D` (`React.lazy`) on
  the landing page and the auth pages; the poster (`/3d/hero-scene*.webp`, rendered from the scene
  itself) shows first and stays for reduced motion, < 4 cores and WebGL failures. The canvas is
  `aria-hidden` with a text alternative beside it.

## 6. Loading — skeletons, never spinners (owner's rule)

Everywhere, loading is a **shimmer skeleton shaped like the content**: same paddings, line
heights, grid and radii as the loaded UI, so nothing moves when data arrives.

* `components/ui/skeleton.tsx`: `Skeleton` (shimmer on `transform`; reduced motion → opacity
  pulse), `SkeletonText`.
* `components/common/skeletons.tsx`: `SkeletonRegion` (one `role="status"` + sr-only label),
  `PageHeaderSkeleton`, `StatCardSkeleton`, `StatRowSkeleton`, `CardSkeleton`, `CardGridSkeleton`,
  `TableSkeleton`, `ListSkeleton`, `FormSkeleton`, `DetailSkeleton`, `ChartSkeleton`,
  `PageSkeleton` (lazy-route Suspense fallback), `AppShellSkeleton` (session bootstrap),
  `AuthSkeleton`, `TopProgressBar`. Feature folders add their own for distinctive layouts
  (launcher tiles, resume grid, editor columns, ATS results, version timeline, provider cards,
  targets board).
* `LoadingState` keeps its API but renders only skeletons (`list | table | cards | stats | form |
  detail | chart`).
* Background refreshes (`isFetching`) keep the content; the topbar shows a thin gradient
  `TopProgressBar` (`useIsFetching`).
* Allowed spinners, only: inside a `Button` while its mutation runs (`loading` prop), inside an
  icon-only action. Upload progress stays a progress bar.

## 7. Primitives — what to reach for

| Need | Use |
|---|---|
| Main action | `<Button>` (gradient; one per view) — `variant="solid"` for a flat indigo in dense toolbars |
| Second action | `variant="soft"` or `variant="outline"`; quiet: `variant="ghost"` |
| Dangerous action | `variant="destructive"` inside `ConfirmDialog` |
| Status pill | `StatusBadge`, `MatchScore`, `Badge variant="success|warning|…"` (soft) |
| AI-made content | `ai` tokens, or `Card variant="soft"` for an AI suggestion block |
| Featured / active item | `Card variant="gradient"` or `.border-gradient` |
| KPI | `StatCard` |
| Lists / tables | `DataTable` / `<Table>` (inset header row, no zebra, 16 px edge padding) + the matching skeleton |
| Empty | `EmptyState` (3D illustration) |
| Tabs | `Tabs` (pill style) |

## 8. Do / don't

| Do | Don't |
|---|---|
| `bg-gradient-brand` for the one primary action | Gradients on tables, charts, body text or more than one button per view |
| `.glass` on the topbar, menus, popovers, the auth card | Glass on content cards (text over unknown backdrops) |
| `bg-success-soft text-success-soft-foreground` pills | `bg-green-100 text-green-700` |
| Skeleton shaped like the content | `Spinner`, "Loading…" text, a generic grey block |
| `font-display` for titles, Inter + `tabular-nums` for numbers in data | Bricolage in tables or form fields |
| 3D art beside text that says the same thing | 3D art as the only carrier of meaning |
| Add a token when a new meaning appears | Hard-code a hex in a component |

Allowed exceptions (on purpose): the resume **paper preview** (`ResumePreview.tsx`: white page,
print colours) and the 3D scene's materials (read from tokens at mount).

## 9. How to add (or change) a colour

1. Decide the meaning; reuse a token if one means it.
2. Add it to `LIGHT` and `DARK` in `notes/theme-contrast.py` (OKLCH via `hue()` / `n()` /
   `brand()`; dark is its own step) and the pairs it will be used in to `pairs()` (glass and
   gradients: add the composite / midpoint pairs too).
3. `backend/.venv/Scripts/python.exe -I notes/theme-contrast.py matrix` → `failures: 0`.
4. `… css` prints the triplets; paste into `:root` and `.dark` in `index.css` (keep the hex comment).
5. Map it in `tailwind.config.ts`.
6. **Restart the Vite dev server** (Tailwind 3.4 caches the `.ts` config). Never `@apply` a class
   that only exists in the new config inside `index.css`.
7. Update the matrix in `notes/theme-research.md` (§6 holds the v2 matrix) and this file.

## 10. Page checklist

- [ ] `PageContainer` + `PageHeader` (string eyebrow = brand small caps); one gradient primary.
- [ ] No raw colours (`grep -nE "(bg|text|border)-(red|green|amber|violet|sky|indigo|slate|gray|white|black)-?[0-9]*|#[0-9a-f]{6}" <file>` empty).
- [ ] Loading = the matching skeleton; refresh keeps content; no spinners outside buttons.
- [ ] Empty = `EmptyState` (illustration matches the meaning); failure = `ErrorState` with retry.
- [ ] Numbers in columns `tabular-nums`; ids `font-mono`.
- [ ] Focus ring visible on every surface (rail, glass, gradient).
- [ ] Destructive actions through `ConfirmDialog`.
- [ ] 1440 and 390 px, light and dark: no clipped labels, no horizontal page scroll.
- [ ] Reduced motion: nothing travels; 3D → poster.
- [ ] Heroes fit the visible UI: full content width, height clamped to the viewport (`min-h-[clamp()]`, ≤ 45 vh, bottom ≤ 50 % on 1366×768), text + illustration grid on lg, stacked below; decorations inside the rounded `overflow-hidden` surface via `inset` (no negative offsets, no `100vw`), `min-w-0` on grid children, `max-w-full` images; `html`/`main` never scroll sideways.

## 11. Performance gates

| Chunk | v1 (HEAD) raw / gzip | v2 raw / gzip |
|---|---:|---:|
| `index` (main) | 452.9 / 133.6 kB | **351.9 / 105.0 kB** (auth pages + zod moved to lazy chunks) |
| `HeroScene` (three + fiber + drei) | — | 822.4 / 219.5 kB (≤ 600 kB gzip budget; only from the landing + auth chunk) |
| `motion` (framer-motion) | — | 117.0 / 38.7 kB (lazy pages only) |
| `Landing` / auth forms / auth pages | — | 33.6 / 10.0 · 9.6 / 3.7 · 8.2 / 3.2 kB |
| CSS | 71.5 / 13.1 kB | 96.6 / 17.9 kB |

The main chunk statically imports only `react` and `ui`. Fonts: Inter Latin subset (108 kB,
all axes/features, full 352 kB file only via `unicode-range` for other scripts) + Bricolage
(41 kB), both preloaded. Images lazy except the hero poster (preloaded on `/` for anonymous
visitors); explicit sizes everywhere; transform/opacity animations only.

## 12. Landing page and auth

* `/` for anonymous visitors renders `pages/Landing.tsx` (lazy, no app shell; `LandingSkeleton`
  while the session bootstraps); signed-in visitors get the launcher. Sections: glass sticky nav,
  hero on `.bg-hero` with the interactive scene (poster first; live only ≥ 768 px, motion allowed,
  ≥ 4 cores, WebGL), "built for" strip, feature bento with the 3D illustrations, How it works
  (real product screenshots `public/landing/step-*-{light,dark}.webp`), safety, FAQ (`<details>`),
  final CTA, footer. SEO via `hooks/useDocumentMeta.ts` + `index.html` (OG image
  `public/landing/og.png`).
* Log in / Create account open a Radix `Dialog` (bottom sheet under 640 px) driven by
  `?auth=login|register`. `/login`, `/register`, `/choose-role` remain full pages (AuthLayout:
  3D hero + glass form card) and share one implementation:
  `features/auth/components/{LoginForm,RegisterForm,PasswordInput,StaySignedInField,AuthDialog}.tsx`
  + `features/auth/usePostAuthRedirect.ts`.
