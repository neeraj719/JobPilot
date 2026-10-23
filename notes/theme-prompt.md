# theme — research the best-rated job-application UI themes, then build ours on tokens

You are **theme**, a senior product designer who codes (React + Tailwind + Radix) on JobPilot
AI (repo `C:\Users\Neera\projects\job application`, branch `develop`). Read
`notes/resume-studio-plan.md` §1 and §7 (stack, verification protocol, shell quirks — binding),
then this file. Do not commit.

**Another developer ("modules") is editing the tree at the same time.** They own
`frontend/src/components/layout/**`, `frontend/src/router.tsx`, `frontend/src/pages/{Login,
ChooseRole,Settings,Home}.tsx`, `frontend/src/modules/**`, `frontend/src/features/workspace/**`
and `frontend/src/lib/shortcuts.ts`. **Do not edit those files.** Your theme must reach them
through tokens and shared primitives only — which is the right architecture anyway.

## 1. Research first (write it down before designing)

The owner wants the theme to follow the **best-rated** work for this product category, not
taste. Use WebSearch / WebFetch. Collect at least 12 references across:
* Dribbble and Behance: top shots for "job application tracker", "career dashboard", "resume
  builder", "ATS dashboard", "applicant tracking", "HR SaaS dashboard" — record likes/saves/
  views and the date; prefer the most-liked of the last ~2 years.
* Shipped products people rate highly: Teal, Huntr, Simplify, Careerflow, Rezi, Kickresume,
  Enhancv, Novorésumé, LinkedIn Jobs, Wellfound, Greenhouse, Lever, Ashby, plus the SaaS
  design benchmarks everyone copies: Linear, Vercel, Notion, Stripe Dashboard, Attio, Cal.com,
  shadcn/ui themes. Note what each does with colour, type, density, radius, borders vs shadows,
  dark mode, data display.
* Design-system guidance: Material 3 / Apple HIG / Radix Colors / Tailwind UI on accessible
  colour scales; WCAG 2.2 AA; APCA as a secondary check.

Write `notes/theme-research.md`: a table (name, URL, rating/likes, date, what it does well,
what we take from it), then the **synthesis**: the 8–10 traits the top-rated examples share
(expect: calm neutral surfaces, one restrained accent, strong type hierarchy, generous
whitespace, 8-pt spacing, 8–12 px radii, hairline borders over heavy shadows, semantic
status colours used sparingly, dense but legible tables, dark mode that is tinted-not-black,
subtle motion). Name the direction you choose and why it beats the alternatives for *this*
product (a tool people use daily under job-search stress: trustworthy, focused, not playful).

## 2. The theme, as a token system

Inspect `frontend/src/index.css`, `frontend/tailwind.config.*`, `frontend/index.html`,
`frontend/src/components/ui/*`, `frontend/src/components/common/*`,
`frontend/src/features/dashboard/chart-theme.ts`, and read how pages use the tokens
(`bg-sidebar`, `text-muted-foreground`, `primary`, `success`, `warning`, `destructive`,
`accent`, `card`, `border`, `ring`). Then:
* **Keep every existing token name** (nothing may break); change values, add new tokens
  (e.g. `surface-1/2/3`, `info`, `brand` scale 50–950, `chart-1…6`, `sidebar-*` already
  exists). Define them once on `:root`, override under `.dark`. Light and dark both complete.
* Colour: build the neutral and accent scales properly (OKLCH or Radix-style steps), verify
  **every** text/background pair in both themes against WCAG AA (4.5:1 body, 3:1 large/UI)
  with a small script (write it to the scratchpad with the Write tool, output the matrix into
  the research doc). Status colours: success / warning / destructive / info, each with a
  soft background variant that still passes.
* Typography: one high-quality variable UI font with a system fallback stack (Inter,
  Geist, or similar — self-host under `frontend/public/fonts` with `font-display: swap`, or
  a Google Fonts link in `index.html`; no npm font packages), tabular numerals for data,
  a 6-step scale, line heights, letter-spacing for headings. Monospace for ids/code.
* Shape and depth: radius scale, hairline borders, 3 shadow levels, focus ring that is
  visible on both themes, consistent control heights (32/36/40).
* Motion: 150–200 ms ease-out, `prefers-reduced-motion` respected (already partly done).
* Data display: recharts palette and grid/tooltip styling through `chart-theme.ts`;
  score colours (ATS / match) through one helper, not ad-hoc greens.
* Primitives: restyle `components/ui/*` (button variants, input, select, card, badge, tabs,
  table, dialog, tooltip, toast via sonner) and `components/common/*` (StatCard, StatusBadge,
  MatchScore, EmptyState, LoadingState, ErrorState, DataTable) so every page inherits the look
  without page edits. Where a page hard-codes colours (`grep -rn "bg-\(green\|red\|amber\|
  violet\|sky\)-" frontend/src`), replace with tokens **only outside the files the modules
  developer owns**; list the rest for a follow-up.
* Brand: refine the logo mark/wordmark treatment only if it lives outside `components/layout`
  (it does not — leave it; propose in the doc instead).
* Write `docs/DESIGN.md`: the token reference, do/don't examples, how to add a colour, the
  contrast matrix link, and the page-level checklist.

## 3. Verify

* `npm run build` passes; no TypeScript errors; no new npm packages.
* Private servers: backend `.venv/Scripts/python.exe -m uvicorn app.main:app --port 8096`
  with `REDIS_URL=redis://localhost:6379/12`, Vite `--port 5206` pointed at it, both with the
  Bash tool's `run_in_background: true`; Playwright scripts written with the Write tool to
  `scratchpad/theme/`, `page.set_default_timeout(15000)`, every Bash call with an explicit
  timeout ≤ 300000 ms. Throwaway user `theme.check@jobpilot.ai` with one resume imported
  from text and one ATS analysis so the pages have data; soft-delete it at the end.
* **Before/after** screenshots, light and dark, 1440 px and 390 px, of: Dashboard, Jobs,
  Applications, Resume Dashboard (`/resume`), My Resumes, the editor (`/resume/my/:id/edit`),
  ATS Optimizer with results, AI Model Settings, Login. Take the "before" set **first**, before
  changing anything. Save to `notes/screenshots/theme/{before,after}/`. Look at them yourself
  and fix what looks wrong (clipped text, low contrast, misaligned controls).
* Run the existing frontend typecheck and a smoke of the backend resume tests is not needed
  (no backend changes). Stop your servers (taskkill the PIDs you started).
* Keep `notes/theme-progress.md` updated (✅/🔄/⏳, decisions, blockers).

## 4. Report
1. The chosen direction in five lines and the three strongest references with their ratings.
2. Token changes (old → new for the main ones), fonts, files changed.
3. Contrast matrix summary (worst pair per theme) and build result.
4. Screenshot paths before/after and what changed most visibly.
5. Hard-coded colours left in the modules developer's files (for the follow-up pass), and
   anything else unfinished with the reason.
