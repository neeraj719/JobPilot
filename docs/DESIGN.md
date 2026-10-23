# JobPilot design system — "Calm Indigo"

The theme is a token system. Pages never pick colours, sizes or shadows of their own:
they use the semantic tokens below (through Tailwind classes) and the shared primitives in
`frontend/src/components/ui` and `frontend/src/components/common`. Change the look in one
place, every page follows.

* Why this direction, the references it is based on and their ratings:
  [`notes/theme-research.md`](../notes/theme-research.md) §1–3.
* Contrast matrix (every text/background pair, both themes, WCAG 2.2 + APCA):
  [`notes/theme-research.md` §4](../notes/theme-research.md#4-contrast-matrix).
* The generator / checker that produced the values: [`notes/theme-contrast.py`](../notes/theme-contrast.py)
  (`python notes/theme-contrast.py matrix` exits 1 on any failing pair; `… css` prints the token blocks).

Source files: `frontend/src/index.css` (token values, `:root` = light, `.dark` = dark, base
styles), `frontend/tailwind.config.ts` (token → class mapping, type scale, radii, shadows,
motion), `frontend/index.html` (font preload, `theme-color`), `frontend/public/fonts/`
(self-hosted Inter, SIL OFL), `frontend/src/lib/score.ts` (score colours),
`frontend/src/features/dashboard/chart-theme.ts` (charts).

## 1. Colour tokens

All values are HSL triplets (`--primary: 234 65.1% 54.9%`) so Tailwind opacity modifiers work
(`bg-primary/10`). They are designed in OKLCH (perceptually even lightness), converted, and
checked on the rounded values the browser actually paints. The hex in the comment next to each
value in `index.css` is the rendered colour.

**Token names are a contract.** Never rename or remove one (pages use them directly); change
values, or add a new token.

### Surfaces and text

| Token (class) | Use | Light | Dark |
|---|---|---|---|
| `background` (`bg-background`) | Page canvas, one step darker than cards | `#f6f7fa` | `#11141a` |
| `card` / `surface-1` | Cards, panels, inputs, the sidebar's peers | `#ffffff` | `#181b22` |
| `popover` | Menus, popovers, dialogs (floats above cards) | `#ffffff` | `#1e2129` |
| `surface-2` | Inset wells: table header row, empty states, row hover | `#f4f6f8` | `#15181e` |
| `surface-3` | Pressed / selected fill, meter tracks | `#eaedf2` | `#272b33` |
| `muted` | Neutral fills (chips, skeletons, tab list) | `#f1f2f6` | `#23272e` |
| `accent` | Hover fill of ghost/outline controls and menu items | `#edf0f5` | `#282d35` |
| `secondary` | Secondary button fill | `#eff1f5` | `#272b33` |
| `foreground` | Primary text | `#121721` | `#eef0f4` |
| `muted-foreground` | Secondary text, labels, placeholders, icons | `#5f6571` | `#b5bbc5` |
| `border` | Hairline borders and dividers (decorative) | `#e2e4e9` | `#2e323a` |
| `input` | Form-control boundaries (≥ 3:1, WCAG 1.4.11) | `#888c95` | `#717681` |
| `ring` | Focus ring (≥ 3:1 on every surface) | `#5d74f6` | `#8097fe` |
| `overlay` | Dialog / sheet scrim (used at 40 % / 60 %) | `#121721` | `#010203` |
| `sidebar`, `sidebar-foreground`, `sidebar-primary(-foreground)`, `sidebar-accent(-foreground)`, `sidebar-border`, `sidebar-ring` | Navigation rail | white / `#505561` / `#f2f5ff` | `#14171d` / `#b5bbc5` / `#262f52` |

Every `x` that text sits on has an `x-foreground`; use the pair together.

### Brand and actions

| Token | Use |
|---|---|
| `primary` / `primary-foreground` | The one accent: primary button, links, selected nav, active step, focus. Light `#4150d7` + white, dark `#92a8ff` + navy `#141c46`. |
| `brand-50 … brand-950` | Raw indigo scale, identical in both themes. For illustration, gradients and identity marks only — UI uses `primary`. |
| `hero-from` / `hero-to` | Sign-in marketing panel (identical in both themes, white copy ≥ 9:1). |

### Status (semantic — never decoration)

Each status has four tokens: **solid** `x` (meters, solid buttons, the score figure, icons),
`x-foreground` (text on solid), and a **soft** pair `x-soft` / `x-soft-foreground` (pills,
alerts, toasts). The solid tone also passes 4.5:1 as *text* on `background`, `card`, `muted`
and on its own `x/10` and `x/15` tints, so the older `bg-success/10 text-success` pattern in
pages stays legible.

| Status | Means | Solid light / dark | Soft light / dark |
|---|---|---|---|
| `success` | offer, interview, strong score, done | `#1f6f3d` / `#66d288` | `#eaf9ee`+`#175a31` / `#192e1f`+`#9fe4b1` |
| `warning` | assessment, needs work, waiting on you | `#925203` / `#f2b44a` | `#fff5e1`+`#7f400a` / `#382814`+`#fad185` |
| `destructive` | rejected, failed, delete, weak score | `#ba1d28` / `#fd847b` | `#fef1f0`+`#9b171e` / `#3e1e1c`+`#febab3` |
| `info` | queued, received, neutral news | `#026796` / `#6fc2f5` | `#ebf6fe`+`#03557b` / `#142c3a`+`#a3d9fd` |
| `ai` | content made by AI (suggestions, AI versions) — not a status | `#743bc3` / `#c4aafe` | violet soft pair |

Status colour always travels with a **label or icon** — never colour alone.

### Charts

`chart-1 … chart-6` are the categorical series slots (blue, orange, aqua, yellow, magenta,
green), with separate dark steps. They are validated as a set (adjacent CVD ΔE ≥ 8, normal
vision ΔE ≥ 15) on `#ffffff` and `#181b22`. Rules: assign in fixed order, never cycle — a 7th
category folds into the neutral "Other"; three light slots are below 3:1 on white, so every
chart keeps its legend and direct labels; status colours are never used as series. Recharts
gets concrete colours through `useChartTheme()`, which reads these CSS variables (plus
`gridProps`, `axisProps`, `cursorProps`, `statusChartColor`, `matchBucketColor`).

### Scores

All scores use `lib/score.ts`:

```ts
scoreTone(score, 'match')   // job fit:   85+ success · 70+ warning · else muted
scoreTone(score, 'quality') // ATS/health: 80+ success · 60+ warning · else destructive
SCORE_TEXT[tone] SCORE_BAR[tone] SCORE_PILL[tone] SCORE_STROKE[tone]  scoreLabel(score, scale)
```

`MatchScore`, `matchScoreColor`, the ATS `scoreTone`/`TONE_TEXT`/`TONE_BAR`, `healthColor`
and the match-distribution chart all delegate to it. Do not write `score >= 80 ? 'text-success'`
in a component.

## 2. Typography

Inter variable (self-hosted, `font-display: swap`, preloaded), fallback
`ui-sans-serif, system-ui, Segoe UI, Roboto, …`. Monospace: `ui-monospace, SF Mono, Cascadia
Code, Consolas` for ids, hashes, code (`font-mono`).

| Role | Class | Size / line | Tracking | Weight |
|---|---|---|---|---|
| Micro label (eyebrow, table header) | `text-2xs` / `.eyebrow` | 11 / 16 | +0.06em uppercase | 600 |
| Caption, meta | `text-xs` | 12 / 16 | +0.005em | 400–500 |
| Body (UI default) | `text-sm` | 14 / 20 | -0.003em | 400–500 |
| Body large, card titles | `text-base` | 16 / 24 | -0.006em | 600 for titles |
| Section / dialog title | `text-lg`, `text-xl` | 18 / 26, 20 / 28 | -0.011, -0.014em | 600 |
| Page title | `text-2xl` | 24 / 32 | -0.019em | 600 |
| Display / KPI hero | `text-3xl` | 30 / 36 | -0.021em | 600 |

Numbers that line up — tables, KPI tiles, scores, money, dates in columns — use
`tabular-nums` (tables get it automatically from `<Table>`; `.numeric` also exists).

## 3. Shape, depth, spacing

* **Radius** (`--radius` = 10 px): `rounded-xl` 12 px cards, panels, dialogs, alerts, empty
  states · `rounded-lg` 10 px menus, popovers, tab lists, icon chips · `rounded-md` 8 px
  buttons, inputs, selects, menu items · `rounded-full` status pills, avatars, switches only.
* **Borders over shadows.** Cards are defined by a 1 px `border` hairline. Shadows, tinted with
  the neutral hue and ×2.4 stronger on dark surfaces:
  `shadow-xs` cards and controls (barely there) · `shadow-sm` hover / raised · `shadow-md`
  menus, popovers, select lists, tooltips · `shadow-lg` toasts · `shadow-xl` dialogs, sheets.
* **Control heights:** 32 (`size="sm"`, `icon-sm`) · 36 (default buttons, inputs, selects,
  tab list) · 40 (`size="lg"`, `icon-lg`).
* **Spacing:** 8-pt grid (Tailwind 2 / 4 / 6 / 8 …); card padding 24 (`p-6`) or 20 (`p-5`
  for KPI tiles); table rows ≈ 40 px (`py-2.5`), header 36 px.
* **Focus:** 2 px `ring` + 2 px gap in the surface colour, on every focusable element
  (global `:focus-visible` rule + primitives). Overlay containers suppress it (their items
  show focus instead).

## 4. Motion

150 ms default (`transition`, `transition-colors`), 200 ms for open/close, curve
`--ease-out` = `cubic-bezier(0.22, 1, 0.36, 1)` (also the Tailwind default timing function).
Nothing bounces or slides more than a few pixels. `prefers-reduced-motion: reduce` collapses
every transition and animation to an instant state change (global rule in `index.css`).

## 5. Primitives — what to reach for

| Need | Use |
|---|---|
| Main action | `<Button>` (one per view) |
| Second action beside it | `<Button variant="soft">` or `variant="outline"` |
| Quiet / toolbar action | `variant="ghost"`, `size="icon-sm"` |
| Dangerous action | `variant="destructive"` inside `ConfirmDialog` |
| Status pill | `StatusBadge`, `MatchScore`, `PriorityBadge`, or `<Badge variant="success|warning|destructive|info|primary|muted">` (soft); `*-solid` only for the rare strongest emphasis |
| AI-made marker | `ai` tokens (`bg-ai-soft text-ai-soft-foreground border-ai/30`, `text-ai` icon) |
| Inline message | `<Alert variant=…>` (soft) |
| Toast | `toast.success(…)` — styled from the same soft tokens |
| KPI | `StatCard` |
| Lists / tables | `DataTable` (or `<Table>`), `LoadingState`, `EmptyState`, `ErrorState` |

## 6. Do / don't

| Do | Don't |
|---|---|
| `bg-success-soft text-success-soft-foreground` for a "Interview" pill | `bg-green-100 text-green-700` |
| `text-muted-foreground` for secondary text | `text-gray-500`, `opacity-60` on body text |
| `border-border` hairline for a card, `shadow-xs` at most | `shadow-lg` on a card that does not float |
| `bg-card` for a control or panel that must be white in light mode | `bg-background` (it is the grey canvas now) or `bg-white` |
| One `primary` button per view | Two solid primaries side by side |
| `SCORE_TEXT[scoreTone(score, 'quality')]` | `score > 80 ? 'text-green-600' : …` |
| Status colour + label/icon | Colour as the only signal |
| `theme.series[i]` / `bg-chart-N` for categories | Re-using `success`/`destructive` as "series 3" |
| Add a token when a new meaning appears | Hard-code a hex in a component |

Allowed exceptions (documented on purpose): the resume **paper preview**
(`ResumePreview.tsx`: white page, black text, template accent colours — it simulates print)
and the sign-in hero (`AuthLayout.tsx`: white copy on `hero-from/to`).

## 7. How to add (or change) a colour

1. Decide the *meaning* first. If an existing token means it, use that token.
2. In `notes/theme-contrast.py`, add the token to `LIGHT` and `DARK` as OKLCH
   (`hue(L, C, h)` / `n(L, C)` for neutrals) — dark is its own step, never an automatic flip.
   For a text-bearing colour add its `-foreground` and, for statuses, the `-soft` pair.
3. Add the pairs it will be used in to `pairs()` and run
   `backend/.venv/Scripts/python.exe -I notes/theme-contrast.py matrix` — it must print
   `failures: 0` (text 4.5:1, UI boundaries and focus 3:1). Aim for APCA Lc ≥ 60 on body text.
4. `… theme-contrast.py css` prints the triplets; paste the new lines into `:root` and `.dark`
   in `frontend/src/index.css` (keep the hex comment).
5. Map it in `frontend/tailwind.config.ts` (`token('name')`, or `status('name')` for a
   four-token status).
6. **Restart the Vite dev server** — a running server keeps the Tailwind config it started with
   (Tailwind 3.4 + Node 22.18 caches the `.ts` config). Never `@apply` a class that only exists
   in the new config inside `index.css`: an unknown `@apply` breaks the whole stylesheet on
   servers that have not restarted.
7. Paste the new matrix into `notes/theme-research.md` §4 and add the token to §1 above.

## 8. Page-level checklist

- [ ] Uses `PageContainer` + `PageHeader`; one primary action.
- [ ] No raw colours: `grep -nE "(bg|text|border)-(red|green|amber|violet|sky|gray|slate|white|black)-?[0-9]*|#[0-9a-f]{6}" <file>` is empty (or an allowed exception).
- [ ] Statuses through `StatusBadge` / `Badge` soft variants / helpers in `lib/utils.ts`; scores through `lib/score.ts`.
- [ ] Panels that must read as white use `bg-card`, not `bg-background`.
- [ ] Loading → `LoadingState`/`Skeleton`, empty → `EmptyState`, failure → `ErrorState` with retry.
- [ ] Numbers in columns are `tabular-nums`; ids/hashes are `font-mono`.
- [ ] Every interactive element shows the focus ring; tab order follows the visual order.
- [ ] Destructive actions go through `ConfirmDialog`.
- [ ] Checked at 1440 px and 390 px, light and dark: no clipped labels, no horizontal scroll.
- [ ] Charts: legend + direct labels, fixed slot order, a table view or tooltip for values.
