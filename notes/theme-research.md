# Theme research — what the best-rated job-search and SaaS interfaces share

Stream **theme**, 2026-10-24. Collected with WebSearch / WebFetch and a headless browser
reading public Dribbble search pages (likes / views as displayed on the cards; dates from
the shot pages). Ratings are the figures the cited page showed on the day; aggregator
figures are marked as such. Where a date is marked **≈** it was not printed on the page and
is interpolated from Dribbble's sequential shot ids (ids 24.32M = Jun 2024, 26.53M = Sep
2025, 27.33M = Apr 2026).

## 1. References

### 1a. Dribbble / Behance — most-liked shots for the product category

Behance search results did not surface resume/job-tracker projects with meaningful
appreciation counts (only generic dashboards with 2–11 appreciations), so the visual
references come from Dribbble, where the counts are public.

| # | Name | URL | Likes / views | Date | What it does well | What we take |
|---|---|---|---|---|---|---|
| D1 | Pedamelan — Job Finder Platform Dashboard (Vektora) | https://dribbble.com/shots/17804172 | **806** / 288k | Mar 23 2022 | Most-liked "job search dashboard": white cards on a pale-grey canvas, one blue accent, big readable job cards | Canvas one step darker than cards; accent reserved for the primary action |
| D2 | Resume Builder (Dstudio) | https://dribbble.com/shots/20728028 | **702** / 285k | Feb 22 2023 | Most-liked "resume builder": editor chrome is pure neutral so the document is the hero; one saturated blue for Share | Editor/preview pages: neutral chrome, tabular inspector rows, one accent |
| D3 | Recruiting Dashboard ATS (Amsterdam Standard) | https://dribbble.com/shots/15273882 | **531** / 148k | Mar 11 2021 | Most-liked "ATS dashboard": hairline-separated panels, small uppercase section labels, muted skill chips, soft status dots | Uppercase micro-labels, neutral chips, status as dot + text |
| D4 | HR Management Dashboard (Nixtio) | https://dribbble.com/shots/25442919 | **524** / 95.3k | ≈ Jan 2025 | Most-liked "HR SaaS dashboard" of the last two years: calm neutrals, rounded 12 px cards, restrained data colour | 12 px card radius, data colour only in charts |
| D5 | WerkLinker — Job Finder Dashboard (Pixelz) | https://dribbble.com/shots/22771729 | **265** / 84.9k | Oct 8 2023 | Dense job grid that stays legible: 8-pt rhythm, 1 px borders, tinted secondary buttons, tabular salary figures | Soft (tinted) secondary actions next to a solid primary |
| D6 | Talent Hiring Dashboard (Awsmd) | https://dribbble.com/shots/27328820 | **239** / 22.1k | Apr 29 2026 | Top 2026 career/hiring dashboard: near-monochrome UI, black primary, big tabular KPI numerals, hairline grid | KPI numerals large + tabular; grids recessive |
| D7 | SaaS HR Dashboard — Ocupite (Ali Husni) | https://dribbble.com/shots/24323648 | **203** / 55.6k | Jun 10 2024 | Textbook shadcn-style SaaS: grey canvas, white bordered cards, one violet CTA, outlined status pills (green / amber), dense table with tabular ids | Outlined soft status pills, dense table, violet-indigo single accent |
| D8 | User profile page in dark theme (Virgil Pana) | https://dribbble.com/shots/26528410 | **148** / 68k | Sep 15 2025 | Candidate profile + score gauge in a **tinted** dark (blue-grey, not black); surfaces step up in lightness, no shadows | Dark mode = lightness-stepped tinted greys; borders not shadows |
| D9 | Talboost — Job Application Tracker Dashboard (Roobinium) | https://dribbble.com/shots/27369370 | 76 / 14.7k | ≈ May 2026 | Most-liked shot titled "job application tracker" in 2026: pipeline columns, soft status chips | Pipeline stage chips use the soft status variants |

### 1b. Shipped products people rate highly

| # | Product | URL | Rating | Date seen | Colour / type / density / shape (observed on public product pages and screenshots) | What we take |
|---|---|---|---|---|---|---|
| P1 | Teal (job tracker + resume builder) | https://www.trustpilot.com/review/tealhq.com | Trustpilot **4.0**; Chrome extension 4.9 from ~2.6k ratings (per ResumeGenius, unverified) | Oct 2026 | White surfaces, one teal accent, table + kanban tracker, generous whitespace; reviewers praise the tracker, complain about reliability | Tracker tables must stay calm and scannable; trust > flair |
| P2 | Huntr (job tracker) | https://chrome.google.com/webstore/detail/mihdfbecejheednfigjpdacgeilhlmnf | Chrome **4.8** (ExtScope aggregator) | Oct 2026 | Kanban board per stage, colour per board, light UI | Stage colour is a *label*, never the only cue |
| P3 | Simplify Copilot (autofill) | https://addons.mozilla.org/addon/simplify-jobs/ | Firefox **4.2** (142 reviews) | Oct 2026 | Card-based job list, blue accent, match % pill on each job | Match-score pill as the one coloured element on a job row |
| P4 | Careerflow | https://www.stork.ai/en/careerflow | Chrome **4.4** (266, via stork.ai) | Oct 2026 | CRM-style tracker board, purple accent | Same; nothing new |
| P5 | Enhancv (resume builder) | https://fi.trustpilot.com/review/enhancv.com | Trustpilot **4.7** (941, Jun 2026 via stork.ai) | Oct 2026 | Neutral editor chrome, document-first, accent only on the CTA | Editor: neutral chrome, document is the hero |
| P6 | Rezi (ATS resume builder) | https://kimola.com/reports/unlock-job-seeking-success-exclusive-rezi-report-insights-trustpilot-en-us-157180 | Trustpilot **4.4** (aggregator, undated) | Oct 2026 | Score-first UI: one big ATS score with green/amber/red bands | One score-band helper for every score in the app |
| P7 | Greenhouse (ATS) | https://www.g2.com/compare/greenhouse-vs-workable | G2 **4.4** (~3,950 reviews), #1 ATS in G2 Spring 2026 | Jul 2026 | Dense tables, green brand used sparingly, neutral greys, clear status text | Dense-but-legible tables (36–40 px rows, tabular numerals) |
| P8 | Ashby (ATS) | https://www.g2.com/compare/ashby-ashby-vs-loxo | G2 **4.7** (~105 reviews) | 2026 | Very neutral grey UI, small type, analytics everywhere, violet accent | Neutral greys + one violet-indigo accent; chart chrome recessive |
| P9 | Attio (CRM, the design benchmark of the category) | https://g2.com/products/attio/reviews?page=9 | G2 **4.3** (531 reviews) | Jul 2026 | Near-monochrome, Inter, hairline 1 px borders, almost no shadows, coloured tags used sparingly, 8 px radii | Hairlines over shadows; tags tinted not saturated |

### 1c. Design-system benchmarks and guidance

| # | Source | URL | Standing | Date | What it says | What we take |
|---|---|---|---|---|---|---|
| S1 | Linear — "How we redesigned the Linear UI" | https://linear.app/now/how-we-redesigned-the-linear-ui | The most-copied SaaS UI | Mar 28 2024 | Themes generated in **LCH** from 3 inputs (base, accent, contrast) instead of 98 hand-picked variables; reduced the blue in neutrals for a calmer look; **Inter Display** for headings, Inter for text; dark mode from the same generator | Perceptual colour space as the source; neutrals only faintly tinted; Inter |
| S2 | Stripe — "Designing accessible color systems" | https://stripe.com/blog/accessible-color-systems | Reference article | Oct 15 2019 | Built in CIELAB so every hue has the same contrast at the same level; text/icon colours pass 4.5:1 on white *and* on the lightest tint; rule "5 levels apart = small text OK" | Status text tones chosen so they pass on white **and** on their own 10–15 % tint |
| S3 | Vercel Geist colours | https://vercel.com/geist/colors | Vercel design system | 2026 | 10 scales × 10 steps: 100–300 component bg, 400–600 borders, 700–800 solid, 900–1000 text | Role-based steps; borders are their own steps |
| S4 | Radix Colors — understanding the scale | https://www.radix-ui.com/colors/docs/palette-composition/understanding-the-scale | De-facto scale for Radix apps | 2026 | 12 steps: 1–2 app bg, 3–5 component bg, 6–8 borders (7 interactive, 8 focus), 9–10 solid, 11–12 text; 11/12 guarantee APCA Lc 60/90 on step 2 | Hairline (decorative) vs interactive border are different tokens |
| S5 | shadcn/ui theming | https://ui.shadcn.com/docs/theming | Most-used React component baseline | 2026 | Semantic pairs (`x` / `x-foreground`), `sidebar-*`, `chart-1..5`, `.dark` overrides, OKLCH values, `--radius` 0.625rem | Keep the shadcn token names (our pages already use them) and add to them |
| S6 | WCAG 2.2 — 1.4.3 / 1.4.11 / 2.4.13 | https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html | W3C | 2023 | 4.5:1 text, 3:1 UI component boundaries; focus indicator ≥ 2 px perimeter with 3:1 change | 2 px ring + 2 px offset, ring colour ≥ 3:1 on every surface; input borders ≥ 3:1 |
| S7 | APCA in a nutshell | https://git.apcacontrast.com/documentation/APCA_in_a_Nutshell.html | WCAG 3 candidate | 2026 | Lc 75 body minimum, Lc 60 content text, Lc 45 headlines, Lc 30 placeholder/disabled, Lc 15 dividers | Secondary check: every body pair ≥ Lc 60, primary text ≥ Lc 90 |
| S8 | Material 3 colour roles | https://m3.material.io/styles/color/system/how-the-system-works | Google | 2026 | (Page is JS-only; known from the spec) tonal palettes 0–100, `on-*` pairs, surface-container levels for elevation in dark mode | Elevation in dark mode by surface lightness (surface-1/2/3), not shadow |
| S9 | dataviz reference palette (bundled skill) | local skill `dataviz/references/palette.md` | Validated with its CVD validator | Jul–Aug 2026 | Fixed-order categorical slots, separate dark steps, status colours never reused as series | Our `chart-theme.ts` already uses slots 1–5; add slot 6, re-validate on our new surfaces |

## 2. Synthesis — what the top-rated examples share

1. **Calm neutral surfaces in two or three steps.** Page canvas one step darker than the
   cards (D1, D4, D7); the sidebar matches the cards. Neutrals carry a faint cool tint
   (Linear reduced it on purpose; S1), never pure grey and never saturated.
2. **One restrained accent.** Every top shot uses a single brand hue for the primary action,
   links, the selected nav item and focus — nothing else (D1, D2, D7, P8). Indigo-violet is
   the category norm for trust/tech products (Ashby, Linear, Ocupite).
3. **Strong type hierarchy from one family.** Inter (or a near-twin) everywhere; headings
   get weight 600 and negative tracking, labels get small uppercase with positive tracking
   (D3, D7, S1). Numbers are large and tabular in KPI tiles (D6) and tables (P7).
4. **8-pt spacing, generous whitespace** around dense content (D5, D7).
5. **8–12 px radii.** 12 px for cards / panels, 8 px for controls, full pills only for
   status and tags (D4, D7, S5 = 10 px base).
6. **Hairline borders over shadows.** 1 px low-contrast borders define cards; shadows are
   reserved for things that float (menus, dialogs, toasts) (P9 Attio, D7, D8).
7. **Semantic status colour used sparingly and softly.** Soft tinted pill + darker text in
   the same hue + a label (D3, D7, S2); the solid status colour is reserved for a few
   strong actions or meters.
8. **Dense but legible tables.** 36–44 px rows, muted uppercase headers, tabular figures,
   hover tint, no zebra (P7, D7).
9. **Dark mode tinted, not black.** Blue-grey surfaces that step *up* in lightness for
   elevation, softer accent, borders still visible (D8, S1, S8).
10. **Subtle motion.** 150–200 ms ease-out on hover / open; nothing bounces; respects
    reduced-motion.

## 3. The direction: **"Calm Indigo"**

A quiet slate-tinted neutral system with a single indigo accent, Inter typography with
tabular figures, hairline borders, three restrained elevation levels and soft status
pills — generated from OKLCH and contrast-checked, light and dark.

**Why this one, for this product.** JobPilot is opened every day by someone under
job-search stress, it automates applications on their behalf, and it shows them scores
about themselves. The interface must read as *trustworthy and in control*:

* **vs. "vibrant / playful"** (gradients, multicolour cards, illustration-heavy — e.g. the
  most-liked job-finder *mobile* shots): delightful in a shot, tiring as a daily tool, and
  colour stops meaning anything when everything is coloured. Status colours (offer,
  rejection, match) must stay meaningful, so the chrome has to be quiet.
* **vs. "monochrome black-primary"** (D6, Attio, Vercel): very premium, but a black primary
  button is visually identical to body text, and a job seeker benefits from one clear,
  friendly accent that says "this is the next step". It also loses the brand continuity of
  the existing indigo logo mark (which lives in the modules developer's layout files).
* **vs. "the current theme"**: same family, but the current values were hand-picked HSL:
  status text fails AA in light mode (warning text on its tint 2.30:1, success 3.14:1, info
  3.36:1, white on amber 2.56:1), input borders are 1.24:1 (invisible boundary), and the
  chart CSS tokens do not match the validated chart palette. Calm Indigo keeps every token
  name and fixes the values.

## 4. Contrast matrix

Generated by `scratchpad/theme/tokens.py matrix` (WCAG 2.x relative-luminance ratio and
APCA-W3 0.0.98G Lc, absolute value). Composite rows (`x/10 on card`) are the exact
alpha-blended colour that `bg-x/10` paints over that surface, because pages use that
pattern for soft pills. Values are measured on the **rounded HSL triplets** that ship in
`index.css`, i.e. what the browser paints.

Before (old values, same method): worst light pair `text-warning` on `warning/15` **2.30:1**,
white on `warning` 2.56:1, `text-success` on `success/10` 3.14:1, `text-info` on card
3.36:1, light input border on card 1.24:1; dark: white on `destructive` 4.25:1, input
border 1.44:1.

#### Light theme

| Text / element | Background | WCAG ratio | Needed | APCA Lc | Result |
|---|---|---:|---:|---:|---|
| `foreground` | `background` | 16.79 | 4.5 | 100 | pass |
| `foreground` | `card` | 17.94 | 4.5 | 105 | pass |
| `foreground` | `popover` | 17.94 | 4.5 | 105 | pass |
| `foreground` | `muted` | 16.06 | 4.5 | 97 | pass |
| `foreground` | `accent` | 15.66 | 4.5 | 95 | pass |
| `foreground` | `secondary` | 15.89 | 4.5 | 96 | pass |
| `foreground` | `surface-2` | 16.53 | 4.5 | 99 | pass |
| `foreground` | `surface-3` | 15.26 | 4.5 | 94 | pass |
| `muted-foreground` | `background` | 5.49 | 4.5 | 75 | pass |
| `muted-foreground` | `card` | 5.87 | 4.5 | 79 | pass |
| `muted-foreground` | `popover` | 5.87 | 4.5 | 79 | pass |
| `muted-foreground` | `muted` | 5.25 | 4.5 | 72 | pass |
| `muted-foreground` | `accent` | 5.12 | 4.5 | 70 | pass |
| `muted-foreground` | `surface-2` | 5.41 | 4.5 | 74 | pass |
| `muted-foreground` | `surface-3` | 4.99 | 4.5 | 68 | pass |
| `muted-foreground` | `muted/60 on card` | 5.49 | 4.5 | 75 | pass |
| `muted-foreground` | `muted/40 on background` | 5.39 | 4.5 | 74 | pass |
| `card-foreground` | `card` | 17.94 | 4.5 | 105 | pass |
| `popover-foreground` | `popover` | 17.94 | 4.5 | 105 | pass |
| `primary-foreground` | `primary` | 6.26 | 4.5 | 86 | pass |
| `secondary-foreground` | `secondary` | 13.98 | 4.5 | 94 | pass |
| `accent-foreground` | `accent` | 15.66 | 4.5 | 95 | pass |
| `destructive-foreground` | `destructive` | 6.35 | 4.5 | 85 | pass |
| `success-foreground` | `success` | 6.21 | 4.5 | 86 | pass |
| `warning-foreground` | `warning` | 6.15 | 4.5 | 85 | pass |
| `info-foreground` | `info` | 6.20 | 4.5 | 86 | pass |
| `ai-foreground` | `ai` | 6.64 | 4.5 | 87 | pass |
| `sidebar-foreground` | `sidebar` | 7.44 | 4.5 | 86 | pass |
| `sidebar-accent-foreground` | `sidebar-accent` | 6.88 | 4.5 | 79 | pass |
| `sidebar-primary-foreground` | `sidebar-primary` | 6.26 | 4.5 | 86 | pass |
| `primary` | `background` | 5.86 | 4.5 | 76 | pass |
| `primary` | `card` | 6.26 | 4.5 | 81 | pass |
| `primary` | `muted` | 5.60 | 4.5 | 73 | pass |
| `primary` | `primary/10 on card` | 5.40 | 4.5 | 71 | pass |
| `primary` | `primary/15 on background` | 4.71 | 4.5 | 62 | pass |
| `destructive` | `background` | 5.94 | 4.5 | 75 | pass |
| `destructive` | `card` | 6.35 | 4.5 | 80 | pass |
| `destructive` | `muted` | 5.69 | 4.5 | 72 | pass |
| `destructive` | `destructive/10 on card` | 5.37 | 4.5 | 68 | pass |
| `destructive` | `destructive/15 on background` | 4.63 | 4.5 | 59 | pass |
| `destructive-soft-foreground` | `destructive-soft` | 7.54 | 4.5 | 80 | pass |
| `success` | `background` | 5.82 | 4.5 | 76 | pass |
| `success` | `card` | 6.21 | 4.5 | 81 | pass |
| `success` | `muted` | 5.57 | 4.5 | 73 | pass |
| `success` | `success/10 on card` | 5.38 | 4.5 | 71 | pass |
| `success` | `success/15 on background` | 4.70 | 4.5 | 62 | pass |
| `success-soft-foreground` | `success-soft` | 7.60 | 4.5 | 82 | pass |
| `warning` | `background` | 5.76 | 4.5 | 76 | pass |
| `warning` | `card` | 6.15 | 4.5 | 80 | pass |
| `warning` | `muted` | 5.51 | 4.5 | 73 | pass |
| `warning` | `warning/10 on card` | 5.32 | 4.5 | 70 | pass |
| `warning` | `warning/15 on background` | 4.65 | 4.5 | 62 | pass |
| `warning-soft-foreground` | `warning-soft` | 7.33 | 4.5 | 81 | pass |
| `info` | `background` | 5.80 | 4.5 | 76 | pass |
| `info` | `card` | 6.20 | 4.5 | 80 | pass |
| `info` | `muted` | 5.55 | 4.5 | 73 | pass |
| `info` | `info/10 on card` | 5.34 | 4.5 | 70 | pass |
| `info` | `info/15 on background` | 4.66 | 4.5 | 62 | pass |
| `info-soft-foreground` | `info-soft` | 7.40 | 4.5 | 81 | pass |
| `ai` | `background` | 6.22 | 4.5 | 78 | pass |
| `ai` | `card` | 6.64 | 4.5 | 82 | pass |
| `ai` | `muted` | 5.95 | 4.5 | 75 | pass |
| `ai` | `ai/10 on card` | 5.71 | 4.5 | 72 | pass |
| `ai` | `ai/15 on background` | 4.96 | 4.5 | 63 | pass |
| `ai-soft-foreground` | `ai-soft` | 7.57 | 4.5 | 81 | pass |
| `input` | `background` | 3.14 | 3.0 | 56 | pass (UI 3:1) |
| `ring` | `background` | 3.71 | 3.0 | 62 | pass (UI 3:1) |
| `input` | `card` | 3.36 | 3.0 | 61 | pass (UI 3:1) |
| `ring` | `card` | 3.96 | 3.0 | 67 | pass (UI 3:1) |
| `input` | `popover` | 3.36 | 3.0 | 61 | pass (UI 3:1) |
| `ring` | `popover` | 3.96 | 3.0 | 67 | pass (UI 3:1) |
| `primary` | `background` | 5.86 | 3.0 | 76 | pass (UI 3:1) |
| `sidebar-ring` | `sidebar` | 3.96 | 3.0 | 67 | pass (UI 3:1) |
| `border` | `card` | 1.27 | - | 13 | decorative (exempt) |
| `border` | `background` | 1.19 | - | 9 | decorative (exempt) |

Worst gated pair (light): input on background at 3.14:1


#### Dark theme

| Text / element | Background | WCAG ratio | Needed | APCA Lc | Result |
|---|---|---:|---:|---:|---|
| `foreground` | `background` | 16.17 | 4.5 | 97 | pass |
| `foreground` | `card` | 15.05 | 4.5 | 97 | pass |
| `foreground` | `popover` | 14.12 | 4.5 | 96 | pass |
| `foreground` | `muted` | 13.21 | 4.5 | 95 | pass |
| `foreground` | `accent` | 12.18 | 4.5 | 94 | pass |
| `foreground` | `secondary` | 12.46 | 4.5 | 94 | pass |
| `foreground` | `surface-2` | 15.62 | 4.5 | 97 | pass |
| `foreground` | `surface-3` | 12.50 | 4.5 | 94 | pass |
| `muted-foreground` | `background` | 9.52 | 4.5 | 65 | pass |
| `muted-foreground` | `card` | 8.86 | 4.5 | 64 | pass |
| `muted-foreground` | `popover` | 8.31 | 4.5 | 63 | pass |
| `muted-foreground` | `muted` | 7.78 | 4.5 | 62 | pass |
| `muted-foreground` | `accent` | 7.17 | 4.5 | 61 | pass |
| `muted-foreground` | `surface-2` | 9.20 | 4.5 | 64 | pass |
| `muted-foreground` | `surface-3` | 7.36 | 4.5 | 61 | pass |
| `muted-foreground` | `muted/60 on card` | 8.22 | 4.5 | 63 | pass |
| `muted-foreground` | `muted/40 on background` | 8.87 | 4.5 | 64 | pass |
| `card-foreground` | `card` | 15.05 | 4.5 | 97 | pass |
| `popover-foreground` | `popover` | 14.12 | 4.5 | 96 | pass |
| `primary-foreground` | `primary` | 7.23 | 4.5 | 56 | pass |
| `secondary-foreground` | `secondary` | 12.46 | 4.5 | 94 | pass |
| `accent-foreground` | `accent` | 12.18 | 4.5 | 94 | pass |
| `destructive-foreground` | `destructive` | 7.67 | 4.5 | 56 | pass |
| `success-foreground` | `success` | 9.48 | 4.5 | 67 | pass |
| `warning-foreground` | `warning` | 9.29 | 4.5 | 67 | pass |
| `info-foreground` | `info` | 9.02 | 4.5 | 64 | pass |
| `ai-foreground` | `ai` | 9.02 | 4.5 | 64 | pass |
| `sidebar-foreground` | `sidebar` | 9.26 | 4.5 | 64 | pass |
| `sidebar-accent-foreground` | `sidebar-accent` | 10.56 | 4.5 | 87 | pass |
| `sidebar-primary-foreground` | `sidebar-primary` | 7.23 | 4.5 | 56 | pass |
| `primary` | `background` | 8.11 | 4.5 | 57 | pass |
| `primary` | `card` | 7.55 | 4.5 | 56 | pass |
| `primary` | `muted` | 6.63 | 4.5 | 54 | pass |
| `primary` | `primary/10 on card` | 6.34 | 4.5 | 54 | pass |
| `primary` | `primary/15 on background` | 6.26 | 4.5 | 53 | pass |
| `destructive` | `background` | 7.69 | 4.5 | 55 | pass |
| `destructive` | `card` | 7.16 | 4.5 | 54 | pass |
| `destructive` | `muted` | 6.29 | 4.5 | 52 | pass |
| `destructive` | `destructive/10 on card` | 6.11 | 4.5 | 52 | pass |
| `destructive` | `destructive/15 on background` | 6.07 | 4.5 | 52 | pass |
| `destructive-soft-foreground` | `destructive-soft` | 9.11 | 4.5 | 71 | pass |
| `success` | `background` | 9.74 | 4.5 | 66 | pass |
| `success` | `card` | 9.06 | 4.5 | 65 | pass |
| `success` | `muted` | 7.96 | 4.5 | 64 | pass |
| `success` | `success/10 on card` | 7.47 | 4.5 | 63 | pass |
| `success` | `success/15 on background` | 7.30 | 4.5 | 62 | pass |
| `success-soft-foreground` | `success-soft` | 9.76 | 4.5 | 77 | pass |
| `warning` | `background` | 10.03 | 4.5 | 68 | pass |
| `warning` | `card` | 9.34 | 4.5 | 67 | pass |
| `warning` | `muted` | 8.20 | 4.5 | 65 | pass |
| `warning` | `warning/10 on card` | 7.69 | 4.5 | 64 | pass |
| `warning` | `warning/15 on background` | 7.50 | 4.5 | 64 | pass |
| `warning-soft-foreground` | `warning-soft` | 9.81 | 4.5 | 78 | pass |
| `info` | `background` | 9.38 | 4.5 | 64 | pass |
| `info` | `card` | 8.73 | 4.5 | 63 | pass |
| `info` | `muted` | 7.66 | 4.5 | 62 | pass |
| `info` | `info/10 on card` | 7.21 | 4.5 | 61 | pass |
| `info` | `info/15 on background` | 7.06 | 4.5 | 60 | pass |
| `info-soft-foreground` | `info-soft` | 9.59 | 4.5 | 76 | pass |
| `ai` | `background` | 9.22 | 4.5 | 63 | pass |
| `ai` | `card` | 8.58 | 4.5 | 62 | pass |
| `ai` | `muted` | 7.53 | 4.5 | 61 | pass |
| `ai` | `ai/10 on card` | 7.09 | 4.5 | 60 | pass |
| `ai` | `ai/15 on background` | 6.95 | 4.5 | 59 | pass |
| `ai-soft-foreground` | `ai-soft` | 9.50 | 4.5 | 76 | pass |
| `input` | `background` | 4.05 | 3.0 | 29 | pass (UI 3:1) |
| `ring` | `background` | 6.81 | 3.0 | 49 | pass (UI 3:1) |
| `input` | `card` | 3.77 | 3.0 | 29 | pass (UI 3:1) |
| `ring` | `card` | 6.34 | 3.0 | 48 | pass (UI 3:1) |
| `input` | `popover` | 3.54 | 3.0 | 28 | pass (UI 3:1) |
| `ring` | `popover` | 5.94 | 3.0 | 47 | pass (UI 3:1) |
| `primary` | `background` | 8.11 | 3.0 | 57 | pass (UI 3:1) |
| `sidebar-ring` | `sidebar` | 6.62 | 3.0 | 49 | pass (UI 3:1) |
| `border` | `card` | 1.34 | - | 0 | decorative (exempt) |
| `border` | `background` | 1.44 | - | 0 | decorative (exempt) |

Worst gated pair (dark): input on popover at 3.54:1


#### Chart slots against the card surface (relief rule: legend + labels always shown)

| Slot | Light | ratio on card | Dark | ratio on card |
|---|---|---:|---|---:|
| chart-1 | `#2a78d6` | 4.42 | `#3987e5` | 4.71 |
| chart-2 | `#eb6834` | 3.20 | `#d95926` | 4.42 |
| chart-3 | `#1baf7a` | 2.82 | `#199e70` | 5.04 |
| chart-4 | `#eda100` | 2.17 | `#c98500` | 5.58 |
| chart-5 | `#e87ba4` | 2.69 | `#d55181` | 4.35 |
| chart-6 | `#008300` | 4.95 | `#008300` | 3.47 |

Hero `hero-from` with white copy: 11.44:1

Hero `hero-to` with white copy: 9.07:1

failures: 0
