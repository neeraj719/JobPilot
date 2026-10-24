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

## 5. Modern / Gen-Z direction (theme-identity, 2026-10-24)

Stream **theme-identity**, 2026-10-24. The owner's new brief: modern, Gen-Z energy and 3D
elements while staying professional ("Duolingo energy with Stripe discipline"); brand root stays
indigo. Collected the same way as §1: public Dribbble search pages read with a headless browser
(likes / views as displayed on the cards, sorted by likes, only shots from the last two years
kept; dates are the "posted" date on the shot page), Product Hunt / G2 / App Store / Trustpilot
pages read with WebFetch, and the live marketing pages of the shipped products opened in a
headless Chromium at 1440 × 900, where the computed styles were measured (h1 family / size /
weight / tracking, the most frequent border-radius of elements ≥ 240 × 160 px, count of elements
with `backdrop-filter`, count of gradient backgrounds, `<canvas>` / Spline / video elements).
Package versions, peer ranges and publish dates come from the npm registry; sizes from
bundlephobia (min + gzip of the whole package, before tree-shaking) unless stated.

### 5a. References

#### 5a-1. Dribbble — most-liked shots, Oct 2024 – Oct 2026

Queries: "gen z dashboard", "3D dashboard", "glassmorphism SaaS", "bento grid dashboard", "job
board 3D illustration", "resume builder landing 3D", "career app dark mode", "AI SaaS dashboard".
For "job board 3D illustration" and "career app dark mode" the most-liked cards are 2020–2023
(Jobly 628 / 188k, Paradigm "Hiring" 425 / 174k, One Week Wonders 429 / 113k) and fall outside
the window; the in-window leaders for those queries are listed instead. Behance search pages
returned HTTP 403 to the fetcher this time, so no Behance counts.

| # | Name | URL | Likes / views | Date | What it does well | What we take |
|---|---|---|---|---|---|---|
| M1 | LoopAI — CRM Dashboard for B2B SaaS (Phenomenon Studio) | https://dribbble.com/shots/25961490 | **1.6k** (1,671) / 1.1m | Apr 29 2025 | By far the most-liked "AI SaaS dashboard" of the period (3× the next shot in any query); light lavender canvas, the app framed in a translucent glass outer shell, white bordered cards, segmented pill tabs, a dot-matrix bar chart in mint with one violet "AI Projected" column, a violet→blue gradient "Run Analysis" button and an AI-assistant panel ("How can I help you?") of soft tinted quick-action tiles | AI = violet gradient, used on exactly one button and one highlighted data point; the AI panel is a tinted tile inside the grid; glass only on the outer frame |
| M2 | Smart Home Control Dashboard — 3D Interface (Nixtio) | https://dribbble.com/shots/26678790 | **525** / 109k | Oct 22 2025 | A rendered 3D object is the hero tile of a dark dashboard; the UI around it stays flat: dark cards with ~20 px radii, one mint accent on toggles, pill controls, avatars as round chips | One 3D render per view, as the hero tile; chrome around it stays flat and quiet |
| M3 | Creatorland — Gen Z Influencer App Design (Phenomenon Studio) | https://dribbble.com/shots/25659780 | **389** / 198k | Feb 20 2025 | Most-liked shot for "gen z dashboard" in the window; the brand frame is loud (lime and magenta colour blocks, a heavy display wordmark, sticker-like star bursts) while the product UI inside the devices is plain white with small type and a lime accent | Gen-Z energy lives in the frame (hero, empty states, stickers/3D, display type); the working UI stays plain — "Duolingo energy, Stripe discipline" in one shot |
| M4 | Bento grid & dashboard for revops startup (Robin Holesinsky) | https://dribbble.com/shots/25765472 | **380** / 184k | Mar 17 2025 | Most-liked "bento grid dashboard": indigo-violet + lavender tiles on a deep navy canvas, ~24 px tile radius, huge KPI numerals (78K, $230,545), one glossy 3D violet asterisk as the only illustration | Bento tiles for the launcher / dashboard, big tabular KPIs, one 3D object per grid; indigo→violet is already "our" colour story |
| M5 | Objectra Dashboard — 3D Printer Workspace (RonDesignLab) | https://dribbble.com/shots/27153858 | **323** / 167k | Mar 6 2026 | "Soft plastic" material language: white panels floating in perspective with depth-of-field blur, a single orange swatch, generous spacing | Soft, matte-glossy 3D reads premium when the palette is tiny |
| M6 | Mobile Network Monitoring — data-heavy dashboard (George Railean) | https://dribbble.com/shots/27577230 | **343** / 87.5k | Jul 21 2026 | Dense KPI ring row and incident table under a 3D city render on a tablet; red used only for alarms | 3D can sit next to dense data if the data layer stays 2D and tabular |
| M7 | HR Management Dashboard (Paperpillar) | https://dribbble.com/shots/26001298 | **283** / 114k | May 9 2025 | Top "glassmorphism SaaS": one frosted panel over a warm blurred gradient backdrop; inner cards are opaque white, one black "Upcoming meeting" card as contrast | Glass only for the outer shell / one floating layer; content cards stay opaque for legibility |
| M8 | Retainable bento grid animation (Robin Holesinsky, rh.design) | https://dribbble.com/shots/27376443 | **223** / 61.6k | May 15 2026 | Light bento feature section, pastel tinted tiles, product screenshots cropped inside tiles, animated in sequence | Feature/launcher tiles show a cropped real UI, not abstract art; stagger-in motion |
| M9 | AI SaaS Resume Builder Website (Wonklab) | https://dribbble.com/shots/26961234 | **261** / 39.9k | Jan 8 2026 | Most-liked in-window "resume builder landing": serif display headline, warm photography, bento of feature cards each with a UI crop, ATS score gauge | Resume features presented as a bento of real UI crops + one score gauge (we already have the gauge) |
| M10 | CV/Resume Builder Website — AI Powered (Shakib) | https://dribbble.com/shots/27024495 | **140** / 18.4k | Jan 27 2026 | Clean white landing, serif headline, editor screenshot with a floating "96 %" resume-score ring and AI chat bubble | Floating score chip over the product shot = the "3D-ish" depth without 3D |
| M11 | MockQuest — AI-Powered Mock Interview App (Usarion) | https://dribbble.com/shots/26788740 | **157** / 17.8k | Nov 19 2025 | Top in-window "career app dark mode": dark plum UI, ~20 px radii, ring % per job, a single pink→orange gradient pill reserved for the "Generate interview" AI action with a sparkle icon | Gradient reserved for the one AI / primary action; everything else tinted neutral |
| M12 | Health Tracker — Dashboard UI (Sigma Software Design) | https://dribbble.com/shots/25000785 | **302** / 177k | Oct 9 2024 | Light frosted cards with 3D organ renders as tile illustrations, big numerals, a gauge | 3D renders work as tile icons at small size too |
| M13 | Forj — AI-Native Management Platform 3D Animation (Dipa Inhouse) | https://dribbble.com/shots/27490965 | **99** / 10k | Jun 22 2026 | In-window leader for "job board 3D illustration" (a weak query: no job-board shot in the window passes 100 likes) | Confirms the 3D-for-AI-SaaS hero trend; nothing job-specific to copy |
| M14 | 3D illustrations for everyone (Samuel Briskar, ThreeDee) | https://dribbble.com/shots/27349413 | 50 / 7.4k | May 6 2026 | Clay-style 3D character with a serif headline | Character 3D is a different (consumer) register; we keep to objects |
| M15 | Task Management App — Glassmorphism SaaS UI (Outcrowd) | https://dribbble.com/shots/27820094 | 57 / 6.2k | Oct 21 2026 | Newest glass reference: one frosted blue card lit by a spotlight glow on deep navy, thin progress bars, small type | Dark mode "glow" = a soft radial light behind one hero card, not glow on every element |

#### 5a-2. Shipped products rated highly for modern UI

Measured columns are from the live page on 2026-10-24 (see method above). Vercel, Notion,
Cal.com, Superhuman and Clay timed out in the headless browser (bot protection / long-polling),
so their visual notes come from their own design-system docs or are marked "not measured".

| # | Product | URL | Rating | Date seen | Type / radius / gradients / glass / motion / 3D (measured unless noted) | What we take |
|---|---|---|---|---|---|---|
| P10 | Linear | https://www.producthunt.com/products/linear/reviews | Product Hunt **4.9** (460 reviews); G2 4.5 (67) | Oct 2026 | Near-black canvas `rgb(8,9,10)`; h1 Inter Variable 64 px / 510 / −1.41 px (−0.022 em); cards 12 px (most frequent), 16–22 px on large panels; pill buttons; 3 blurred elements (nav); feature row illustrated with **line-art isometric 3D**, not renders | Inter for UI, medium-weight big headlines with tight tracking; 12 px in the product, larger radii only on marketing-size tiles |
| P11 | Raycast | https://www.producthunt.com/products/raycast/reviews | Product Hunt **4.9** (162) | Oct 2026 | `rgb(7,8,10)` canvas; h1 Inter 64 px / 600; **20 px** card radius (35 elements), 12 px inner; 16 `backdrop-filter` elements; 235 gradient backgrounds (mostly subtle edge/glow fills); 1 WebGL `<canvas>` hero; bento feature tiles ("Fast / Ergonomic / Personal / Reliable") | Bento tiles with 20 px radius, gradient as light/edge, not as fill; glass on floating layers |
| P12 | Arc (The Browser Company) | https://www.producthunt.com/products/arc-browser/reviews | Product Hunt **4.8** (237) | Oct 2026 | arc.net now shows "A farewell to Arc" (the product is no longer developed); h1 is a serif (Exposure VAR 76 px / 600); no glass, few gradients | Reference only: the playful-but-crafted tone came from type and copy, not effects |
| P13 | Vercel | https://www.producthunt.com/products/vercel/reviews | Product Hunt **5.0** (1,100) | Oct 2026 | Not measured (timeout). Geist materials doc: radius 6 px base/small/tooltip, 12 px medium/large/menu/modal, 16 px fullscreen; Geist Sans/Mono (OFL) | The dashboard keeps 6–12 px; 16 px+ only for the largest surfaces |
| P14 | Notion | https://www.producthunt.com/products/notion/reviews | Product Hunt **4.8** (1,413); G2 4.6 (~10.9k) | Oct 2026 | Not measured (timeout) | — (rating only) |
| P15 | Cal.com | https://www.producthunt.com/products/cal/reviews | Product Hunt **4.8** (86); G2 4.6 (150) | Oct 2026 | Not measured (timeout) | — (rating only) |
| P16 | Superhuman | https://www.producthunt.com/products/superhuman/reviews | Product Hunt **4.8** (91) | Oct 2026 | Not measured (timeout) | — (rating only) |
| P17 | Clay (clay.com) | https://www.g2.com/products/clay-com-clay/reviews | G2 **4.7** (192, via search snippet) | Oct 2026 | Not measured (timeout); a claymation brand style could not be verified from a primary source | — (rating only) |
| P18 | Framer | https://www.producthunt.com/products/framer/reviews | Product Hunt **4.8** (262) | Oct 2026 | Black canvas; h1 GT Walsheim 54 px / 500 / −2.16 px (−0.04 em); radii 15–25 px (15, 18, 25, 20 most frequent); 4 glass elements; 1 gradient-text element; the AI prompt box carries a **neon indigo-blue glow outline**; 4 videos | Glow outline reserved for the AI input; display face distinct from body |
| P19 | Spline | https://www.producthunt.com/products/spline/reviews | Product Hunt **4.6** (32) | Oct 2026 | Black canvas; h1 Geist 48 px / 450 / −2.88 px (−0.06 em); 16 px cards; pill buttons; 4 `<canvas>` + 7 Spline embeds (live 3D) | Live 3D is the product here — and costs a 0.5 MB+ runtime (see L5); not for an app shell |
| P20 | Duolingo | https://apps.apple.com/us/app/duolingo-language-lessons/id570060128 | App Store **4.7** (5.5M ratings), #2 Education, Editors' Choice | Oct 2026 | White canvas; h1 `duolingo-sans` 32 px / **700**; 12 px buttons (50 px tall); no glass, no gradients; illustrated characters carry the energy. Third-party breakdowns (unverified) describe a solid 3–4 px darker bottom "ledge" on buttons instead of blurred shadows | Energy from colour, characters and chunky pressable buttons — not from gradients or glass |
| P21 | Revolut | https://www.trustpilot.com/review/revolut.com | Trustpilot **4.7** (478,334) | Oct 2026 | White canvas; h1 Aeonik Pro 88 px / 500 / −2.08 px; cards 20–22.5 px; 6 glass elements (frosted balance card over a photo); pill + 12 px buttons; 5 videos | Very large display type, 20 px+ cards, one frosted card over imagery |
| P22 | Monzo | https://apps.apple.com/gb/app/monzo-bank-mobile-banking/id1052238659 | App Store UK **4.9** (365k ratings) | Oct 2026 | White canvas; h1 MonzoSansDisplay 49 px / **800**; card radii **32 px** (31 elements) and 64 px; fully rounded buttons; 27 videos | Biggest radii of the set — consumer banking; too soft for a dense tool |
| P23 | Teal (re-measured, see P1) | https://www.tealhq.com | Trustpilot 4.0 (P1) | Oct 2026 | White; h1 Roobert 64 px / 600 / −2 px; 16 px cards; pill CTAs (yellow); 18 gradient backgrounds; product UI crops with a floating "32 % score" chip | Direct competitor already uses 16 px cards + floating score chips; we need more identity than that |

#### 5a-3. 3D asset sources with a shippable licence

| # | Source | URL | Standing | Date | Exact licence terms | What we take |
|---|---|---|---|---|---|---|
| A1 | **3dicons** v1 (Vijay Verma / realvjy) | https://3dicons.co/collection/b68cf8-v1 | 122 icons, 1,464 renders, 49.4 M downloads (collection API) | captured Oct 24 2026 | **CC0 1.0** — collection API `"license":"CC0"`; each icon page "LICENSE CC0"; About: "free to use for personal and commercial projects … copying, editing, remixing, sharing, and redrawing". No attribution required. 4 colour styles (color, clay, gradient, premium) × 3 angles (dynamic, iso, front); PNG at 100/200/400/500/2400 px; the site's own download endpoint `/api/icon/download/<uuid>?type=<angle>-<style>&size=<px>` returns a signed URL. No public GitHub repo found (Figma file, plugin and a Gumroad bulk zip exist). 3dicons **Pro** is a separate paid editor — not used | **Chosen.** 19 "dynamic / gradient" renders downloaded (orange → magenta → indigo glossy plastic), see the manifest in `scratchpad/theme-identity/3d-raw/` |
| A2 | Shapefest | https://www.shapefest.com/license-agreement | "Over 100,000 3D renders" | Oct 2026 | One "Commercial+ License" covers free and paid items: "Personal or commercial use permitted", web / mobile / print, unlimited projects, may be part of a product for sale; "Assets cannot be sub-licensed, resold, shared, transferred, or otherwise redistributed on its own (even for free)"; may not edit and sell as your own. Free packs at 512 × 512 px, paid 3000 px. Attribution not mentioned | Usable fallback for abstract shapes; not CC0 (no redistribution of the files themselves, e.g. in an open repo) |
| A3 | Spline community | https://docs.spline.design/basics/community-platform | Spline's own docs | Oct 2026 | Docs page: "All the community files are licensed under **CC BY 4.0**" — attribution required (a search-engine snippet of an older page said CC0; the live page says CC BY 4.0, so treat as CC BY). Shipping a scene also needs `@splinetool/runtime` (L5) | Not CC0 and heavy at runtime; use only to *render* stills, with credit |
| A4 | Icons8 3D (3D Fluency, Clay, etc.) | https://community.icons8.com/t/free-license-attribution-requirements/1708 | Large commercial library | licence text quoted Apr 2020; Oct 2026 search | Free account: "Free Account Holders must provide two hyperlinks … One link shall be to the Icons8 website, and a secondary link to the location of the downloaded work"; free downloads are size-limited; a paid plan removes the link; prohibited on any plan: logos/trademarks, NFTs, AI/ML training (pricing page, via search) | Avoid: link-back on every page that shows an asset is not acceptable in an app shell |
| A5 | Figma Community packs | https://help.figma.com/hc/en-us/articles/360042296374 | Figma help centre | Oct 2026 | "Free files are published under an Attribution 4.0 International (CC BY 4.0) license … This isn't a public domain license." Creators *may* add other licences (e.g. CC0) on top; paid files use the Community Paid Resource License | Only packs whose page explicitly states CC0 are CC0; default is CC BY 4.0 (credit needed) |

#### 5a-4. Motion and 3D libraries (React 18)

The frontend already pins the React-18 line of each: `framer-motion 11.18.2`, `three 0.171.0`,
`@react-three/fiber 8.18.0`, `@react-three/drei 9.122.0` (`frontend/package.json`; the r3f code is
lazy-loaded from `features/brand-3d/HeroScene.tsx`).

| # | Library | URL | Version for React 18 (publish date) | Size | Notes |
|---|---|---|---|---|---|
| L1 | framer-motion (= `motion`) | https://motion.dev/docs/react-reduce-bundle-size | **11.18.2** (Jan 20 2025, pinned); 12.43.0 (Jul 28 2026) also peers `react ^18 \|\| ^19` | bundlephobia 141.9 kB min / **47.1 kB gzip** whole package; motion.dev: full `motion` component 43 kB, `m` + `LazyMotion` "just over 5 kB" initial, `domAnimation` +24 kB, `domMax` +38 kB | Use `LazyMotion` + `m` with async `domAnimation`; springs, layout, `useReducedMotion` |
| L2 | three | https://www.npmjs.com/package/three | **0.171.0** (pinned; current 0.186.1, Sep 24 2026) | 679.7 kB min / **170.1 kB gzip** (whole, tree-shaking reduces it with r3f) | Only inside the lazy hero chunk |
| L3 | @react-three/fiber | https://www.npmjs.com/package/@react-three/fiber | **8.18.0** (Feb 19 2025) — last v8, peers `react >=18 <19`. v9 (9.0.0 Feb 19 2025 → 9.8.2 Oct 14 2026) peers `react >=19 <19.4`, so **not** usable on React 18 | 131.8 kB min / **42.5 kB gzip** | Keep v8 until the app moves to React 19 |
| L4 | @react-three/drei | https://www.npmjs.com/package/@react-three/drei | **9.122.0** (Feb 19 2025) — last v9, peers `@react-three/fiber ^8`, `react ^18`. v10 peers fiber ^9 / react ^19 | whole package 1.64 MB min / 511 kB gzip — import individual helpers only (`Float`, `RoundedBox`, `Environment`) | Tree-shaken per import; never `import * from` |
| L5 | @splinetool/runtime (+ react-spline) | https://www.npmjs.com/package/@splinetool/runtime | 1.12.95 (May 22 2026); current 2.0.111 | bundlephobia: main **561 kB gzip** + a 723 kB-gzip lazy chunk | Too heavy for an app; Spline is only useful for rendering stills |
| L6 | lottie-react | https://www.npmjs.com/package/lottie-react | **2.4.1** (Jan 22 2025), peers React 16.8–19; 2.4.2 (Aug 16 2026) | 314.8 kB min / **79.8 kB gzip** (bundles lottie-web 5.13.0, 76.8 kB gzip) | Heavier than our whole motion need; only if a designer supplies Lottie files |
| L7 | Pure CSS 3D | https://developer.mozilla.org/en-US/docs/Web/CSS/perspective | — | **0 kB JS** | `perspective` + `rotateX/Y` tilt on hover, `transform-style: preserve-3d`, layered `drop-shadow` on PNG renders; enough for "3D" cards and floating illustrations |

#### 5a-5. Display fonts for headings

All five are on Google Fonts under the **SIL Open Font License 1.1** (`license: "OFL"` in each
family's `METADATA.pb` in github.com/google/fonts). Sizes are Fontsource's Latin variable
`woff2` (`cdn.jsdelivr.net/fontsource/fonts/<id>:vf@latest/latin-wght-normal.woff2`).

| # | Font | URL | Licence / axes | Latin woff2 | Character and pairing with Inter |
|---|---|---|---|---|---|
| F1 | Space Grotesk (Florian Karsten, 2020) | https://fonts.google.com/specimen/Space+Grotesk | OFL; `wght` 300–700 | 22.3 kB | Techy, derived from Space Mono; quirky `a`/`G`; max weight 700, no opsz; reads "crypto / dev-tool 2020", contrast with Inter is good but tone is dated |
| F2 | Sora (Barnbrook / Moncada, 2020) | https://fonts.google.com/specimen/Sora | OFL; `wght` 100–800 | 33.7 kB | Wide geometric, built for a crypto brand; wide set width fights Inter's narrower rhythm in mixed lines |
| F3 | Plus Jakarta Sans (Tokotype, 2022) | https://fonts.google.com/specimen/Plus+Jakarta+Sans | OFL; `wght` 200–800 (+ italic) | 27.3 kB | Friendly geometric-humanist; very close to Inter, so the pairing adds little personality |
| F4 | Manrope (Mikhail Sharanda, 2019) | https://fonts.google.com/specimen/Manrope | OFL; `wght` 200–800 | 24.8 kB | Semi-condensed modern grotesk; also close to Inter; calm, not Gen-Z |
| F5 | **Bricolage Grotesque** (Mathieu Triay, 2023) | https://fonts.google.com/specimen/Bricolage+Grotesque | OFL; `opsz` 12–96, `wdth` 75–100, `wght` 200–800 | 41.3 kB (`wght` only) | Ink-trap, slightly condensed grotesque whose display optical size is expressive and editorial, while small sizes stay sober; the most distinct from Inter of the five, and the newest. Already self-hosted (`frontend/public/fonts/BricolageGrotesque-Variable.woff2`, 41,344 bytes) |
| — | Inter (body, for reference) | https://fonts.google.com/specimen/Inter | OFL; `opsz` 14–32, `wght` 100–900 | 48.3 kB Latin (the repo currently ships the full 352 kB `InterVariable.woff2`) | Body / UI |

**Font recommendation: Bricolage Grotesque** for display only (page titles, launcher greeting,
hero, KPI numerals ≥ 24 px), weight 600–700, tracking −0.02 to −0.03 em; Inter for everything
else. It is the only candidate with an optical-size axis and the clearest contrast with Inter,
matching the shipped pattern of "distinct display face + neutral body" (Framer, Revolut, Monzo,
Teal — P18, P21–P23). Space Grotesk / Sora read 2020-crypto; Plus Jakarta / Manrope are too close
to Inter to be worth a second font request.

### 5b. What the top-rated modern work shares (checked against 5a)

1. **Bento grids — confirmed.** The most-liked bento shot (M4, 380 / 184k) and its 2026 follow-up
   (M8), the resume landings (M9, M10) and shipped marketing (Raycast tiles P11, Linear feature
   row P10) group features into tiles of unequal size, each with one idea and often a cropped
   real UI.
2. **Large radii — confirmed with a split.** Marketing tiles and hero cards sit at **16–24 px**
   (Raycast 20, Framer 15–25, Spline 16, Revolut 20–22.5, Teal 16; Monzo goes to 32–64), but
   product UI stays at **12 px** (Linear app, Vercel Geist medium/large 12, fullscreen 16). Pills
   for buttons are common (Linear, Spline, Revolut, Monzo, Teal).
3. **Display type — corrected: big and tight rather than bold.** Headlines are 48–88 px with
   −0.02 to −0.06 em tracking, but mostly **medium weight 450–600** (Linear 510, Spline 450,
   Framer 500, Revolut 500, Raycast 600); only the consumer brands go 700–800 (Duolingo,
   Monzo). Half use a distinct display face; Linear and Raycast use Inter.
4. **Vivid gradient on a calm base — confirmed, but narrow.** Gradient *text* is rare (1 element
   on Framer, 0 elsewhere). Gradients appear as light: glows, edge strokes, one CTA (M11's single
   AI pill, Framer's glowing AI input, Raycast's subtle fills), or as the material of a 3D object
   (M4, A1).
5. **Glass — confirmed as sparing.** `backdrop-filter` counts: Raycast 16, Revolut 6, Framer 4,
   Linear 3, Spline 2, Monzo 1, Duolingo / Teal / Arc 0 — nav bars and one floating card. The
   glass Dribbble shots (M7, M15) keep content cards opaque.
6. **Dark mode with glows — confirmed for tools, not universal.** The dev/creator tools lead
   dark (Linear `rgb(8,9,10)`, Raycast `rgb(7,8,10)`, Framer, Spline black) with a soft radial
   light behind one hero element (M15, P18); consumer/finance/career products lead light
   (Duolingo, Revolut, Monzo, Teal). A job-search tool needs both to be first-class.
7. **3D on heroes, empty states and tiles — confirmed, one object per view.** M2, M4, M5, M6, M12
   use exactly one rendered object (or set) per screen; shipped products mostly use video or
   line-art (Linear) — live WebGL appears only where 3D is the product (Spline, Raycast's one
   canvas).
8. **Spring micro-interactions — not measurable from stills.** Animated shots (M8 stagger-in,
   M13) and the motion libraries' defaults suggest springy enter/hover; treat as a design choice,
   not evidence. Must respect `prefers-reduced-motion`.
9. **Generous whitespace and very high contrast — confirmed.** Near-black or pure-white canvases
   with white / near-black text; one accent; dense data only inside tiles (M6, M1).
10. **Energy from colour and characters, not effects (added).** The highest-rated consumer app
    (Duolingo 4.7 from 5.5M) has no glass and no gradients; its energy is saturated colour,
    chunky pressable buttons and illustration — the "Duolingo energy, Stripe discipline" brief
    maps to: playful objects + disciplined chrome.

### 5c. Recommended direction

Keep the Calm Indigo token system (§3–4) as the disciplined base and add a thin "modern" layer:
**gradient family indigo → violet → fuchsia** (`#4150d7 → #7335d0 → #ae1599`, the tokens the
stream already has), not indigo → cyan, because (a) the chosen CC0 3D renders (A1 "gradient"
style) are lit orange → magenta → indigo, so a fuchsia end makes illustrations and UI one colour
story while cyan would clash; (b) the most-liked bento reference (M4) is indigo-violet-lavender;
(c) every stop holds white text at ≥ 6.2:1 (6.26 / 6.67 / 6.24), so the gradient can carry a
label in both themes; a cyan end light enough to read as cyan would not. Use it the
way the evidence does — the primary/AI CTA, focus/AI glow, hero and one tile per grid — never as
text fill on body copy. **Display font: Bricolage Grotesque** (F5) at medium-to-semibold weights
with tight tracking, Inter for UI. **3D style: pre-rendered glossy "soft plastic" objects** from
one pack (3dicons v1, gradient style, dynamic angle, CC0), one per view on heroes, empty states,
launcher tiles and the dashboard start card, with a gentle CSS float/tilt (L7); the existing r3f
scene stays a single lazy hero on the auth routes with a static PNG fallback. Radii: 12 px in the
product, 16–20 px for bento tiles / hero cards, pills for primary buttons. **Performance budget:**
no 3D or Lottie code in the main chunk (today 454 kB / 134 kB gzip); framer-motion through
`LazyMotion` + `m` (~5 kB initial, `domAnimation` loaded async); the r3f chunk (three + fiber + a
few drei helpers; whole-package gzip 170 + 42.5 kB before tree-shaking) loads only on auth routes
after first paint and never under `prefers-reduced-motion`; no Spline runtime (561 kB gzip); 3D
images as WebP at 2× display size — the 500 px renders average 97.9 kB as PNG but **15.6 kB** as
WebP q85 (9.9 kB at 320 px), always `loading="lazy"` with explicit width/height; one display font
request (41 kB). Subsetting Inter to Latin (48 kB vs the 352 kB file shipped now) would pay for
all of the above.

## 6. v2 contrast matrix (theme-identity, 2026-10-24)

Generated by `notes/theme-contrast.py matrix` after the v2 tokens: dark indigo rail, brand gradient (white copy), gradient text, soft gradient, glass at 90 % on its real backdrops (canvas, card, both hero stops), hero copy and washes, logo tile, skeleton, landing page pairs. Same method as §4; v1 rows unchanged.

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
| `sidebar-foreground` | `sidebar` | 12.26 | 4.5 | 84 | pass |
| `sidebar-accent-foreground` | `sidebar-accent` | 11.19 | 4.5 | 97 | pass |
| `sidebar-primary-foreground` | `sidebar-primary` | 6.07 | 4.5 | 49 | pass |
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
| `sidebar-ring` | `sidebar` | 8.91 | 3.0 | 66 | pass (UI 3:1) |
| `sidebar-foreground` | `sidebar` | 12.26 | 4.5 | 84 | pass |
| `sidebar-accent-foreground` | `sidebar` | 15.85 | 4.5 | 103 | pass |
| `sidebar-muted` | `sidebar` | 7.69 | 4.5 | 58 | pass |
| `sidebar-foreground` | `sidebar-raised` | 10.58 | 4.5 | 82 | pass |
| `sidebar-accent-foreground` | `sidebar-raised` | 13.68 | 4.5 | 101 | pass |
| `sidebar-muted` | `sidebar-raised` | 6.64 | 4.5 | 56 | pass |
| `sidebar-foreground` | `sidebar-accent` | 8.65 | 4.5 | 79 | pass |
| `sidebar-accent-foreground` | `sidebar-accent` | 11.19 | 4.5 | 97 | pass |
| `sidebar-muted` | `sidebar-accent` | 5.43 | 4.5 | 52 | pass |
| `sidebar-foreground` | `sidebar-accent/60 on sidebar` | 10.06 | 4.5 | 82 | pass |
| `sidebar-accent-foreground` | `sidebar-accent/60 on sidebar` | 13.00 | 4.5 | 100 | pass |
| `sidebar-muted` | `sidebar-accent/60 on sidebar` | 6.31 | 4.5 | 55 | pass |
| `sidebar-section` | `sidebar` | 8.91 | 4.5 | 66 | pass |
| `sidebar-primary` | `sidebar` | 6.12 | 3.0 | 48 | pass (UI 3:1) |
| `sidebar-primary` | `sidebar-accent` | 4.32 | 3.0 | 42 | pass (UI 3:1) |
| `sidebar-glow` | `sidebar` | 8.43 | 3.0 | 63 | pass (UI 3:1) |
| `sidebar-glow` | `sidebar-accent` | 5.95 | 3.0 | 57 | pass (UI 3:1) |
| `sidebar-ring` | `sidebar-raised` | 7.69 | 3.0 | 64 | pass (UI 3:1) |
| `sidebar-ring` | `sidebar-accent` | 6.29 | 3.0 | 60 | pass (UI 3:1) |
| `primary-foreground` | `primary` | 6.26 | 4.5 | 86 | pass |
| `info-foreground` | `info` | 6.20 | 4.5 | 86 | pass |
| `warning-foreground` | `warning` | 6.15 | 4.5 | 85 | pass |
| `success-foreground` | `success` | 6.21 | 4.5 | 86 | pass |
| `brand-50` | `brand-600` | 5.74 | 4.5 | 79 | pass |
| `hero-foreground` | `hero-from` | 10.02 | 4.5 | 94 | pass |
| `hero-muted` | `hero-from` | 7.04 | 4.5 | 70 | pass |
| `hero-foreground` | `hero-to` | 15.29 | 4.5 | 102 | pass |
| `hero-muted` | `hero-to` | 10.75 | 4.5 | 78 | pass |
| `hero-foreground` | `hero-from/50 on hero-to` | 12.57 | 4.5 | 99 | pass |
| `hero-muted` | `hero-from/50 on hero-to` | 8.84 | 4.5 | 75 | pass |
| `gradient-foreground` | `gradient-from` | 6.26 | 4.5 | 86 | pass |
| `gradient-foreground` | `gradient-via` | 6.68 | 4.5 | 87 | pass |
| `gradient-foreground` | `gradient-to` | 6.24 | 4.5 | 84 | pass |
| `gradient-foreground` | `gradient-from/50 on gradient-via` | 6.63 | 4.5 | 87 | pass |
| `gradient-foreground` | `gradient-via/50 on gradient-to` | 6.73 | 4.5 | 87 | pass |
| `gradient-text-from` | `background` | 5.86 | 4.5 | 76 | pass |
| `gradient-text-from` | `card` | 6.26 | 4.5 | 81 | pass |
| `gradient-text-via` | `background` | 6.25 | 4.5 | 77 | pass |
| `gradient-text-via` | `card` | 6.68 | 4.5 | 82 | pass |
| `gradient-text-to` | `background` | 5.84 | 4.5 | 75 | pass |
| `gradient-text-to` | `card` | 6.24 | 4.5 | 79 | pass |
| `foreground` | `gradient-soft-from` | 16.06 | 4.5 | 97 | pass |
| `muted-foreground` | `gradient-soft-from` | 5.25 | 4.5 | 72 | pass |
| `primary` | `gradient-soft-from` | 5.60 | 4.5 | 73 | pass |
| `foreground` | `gradient-soft-to` | 15.92 | 4.5 | 96 | pass |
| `muted-foreground` | `gradient-soft-to` | 5.20 | 4.5 | 71 | pass |
| `primary` | `gradient-soft-to` | 5.55 | 4.5 | 72 | pass |
| `foreground` | `glass/90 on background` | 17.82 | 4.5 | 104 | pass |
| `muted-foreground` | `glass/90 on background` | 5.83 | 4.5 | 79 | pass |
| `ring` | `glass/90 on background` | 3.93 | 3.0 | 66 | pass (UI 3:1) |
| `foreground` | `glass/90 on card` | 17.94 | 4.5 | 105 | pass |
| `muted-foreground` | `glass/90 on card` | 5.87 | 4.5 | 79 | pass |
| `ring` | `glass/90 on card` | 3.96 | 3.0 | 67 | pass (UI 3:1) |
| `hero-foreground` | `hero-foreground/10 on hero-from` | 7.68 | 4.5 | 89 | pass |
| `hero-muted` | `hero-foreground/10 on hero-from` | 5.40 | 4.5 | 65 | pass |
| `foreground` | `glass/90 on hero-from` | 15.07 | 4.5 | 93 | pass |
| `muted-foreground` | `glass/90 on hero-from` | 4.93 | 4.5 | 68 | pass |
| `ring` | `glass/90 on hero-from` | 3.33 | 3.0 | 55 | pass (UI 3:1) |
| `hero-foreground` | `hero-foreground/10 on hero-to` | 11.56 | 4.5 | 98 | pass |
| `hero-muted` | `hero-foreground/10 on hero-to` | 8.12 | 4.5 | 73 | pass |
| `foreground` | `glass/90 on hero-to` | 14.71 | 4.5 | 91 | pass |
| `muted-foreground` | `glass/90 on hero-to` | 4.81 | 4.5 | 66 | pass |
| `ring` | `glass/90 on hero-to` | 3.25 | 3.0 | 53 | pass (UI 3:1) |
| `foreground` | `background/60 on card` | 17.24 | 4.5 | 102 | pass |
| `muted-foreground` | `background/60 on card` | 5.64 | 4.5 | 77 | pass |
| `muted-foreground` | `card/50 on background` | 5.68 | 4.5 | 77 | pass |
| `gradient-text-from` | `card/50 on background` | 6.06 | 4.5 | 78 | pass |
| `gradient-text-to` | `card/50 on background` | 6.04 | 4.5 | 77 | pass |
| `foreground` | `accent/60 on card` | 16.55 | 4.5 | 99 | pass |
| `gradient-text-from` | `gradient-soft-from` | 5.60 | 4.5 | 73 | pass |
| `gradient-text-via` | `gradient-soft-from` | 5.98 | 4.5 | 74 | pass |
| `gradient-text-to` | `gradient-soft-from` | 5.59 | 4.5 | 72 | pass |
| `gradient-text-from` | `gradient-soft-to` | 5.55 | 4.5 | 72 | pass |
| `gradient-text-via` | `gradient-soft-to` | 5.93 | 4.5 | 74 | pass |
| `gradient-text-to` | `gradient-soft-to` | 5.54 | 4.5 | 71 | pass |
| `gradient-text-from` | `popover` | 6.26 | 4.5 | 81 | pass |
| `gradient-text-via` | `popover` | 6.68 | 4.5 | 82 | pass |
| `gradient-text-to` | `popover` | 6.24 | 4.5 | 79 | pass |
| `skeleton` | `background` | 1.12 | - | 0 | decorative (exempt) |
| `skeleton` | `card` | 1.20 | - | 10 | decorative (exempt) |
| `skeleton-highlight` | `skeleton` | 1.15 | - | 8 | decorative (exempt) |
| `sidebar-border` | `sidebar` | 1.31 | - | 0 | decorative (exempt) |
| `border` | `card` | 1.27 | - | 13 | decorative (exempt) |
| `border` | `background` | 1.19 | - | 9 | decorative (exempt) |

Worst gated pair (light): input on background at 3.14:1

Worst sidebar text pair (light): sidebar-muted on sidebar-accent at 5.43:1 (needs 4.5)

Worst sidebar UI pair (light): sidebar-primary on sidebar-accent at 4.32:1 (needs 3.0)


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
| `sidebar-foreground` | `sidebar` | 12.58 | 4.5 | 78 | pass |
| `sidebar-accent-foreground` | `sidebar-accent` | 12.81 | 4.5 | 98 | pass |
| `sidebar-primary-foreground` | `sidebar-primary` | 6.07 | 4.5 | 49 | pass |
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
| `sidebar-ring` | `sidebar` | 7.13 | 3.0 | 49 | pass (UI 3:1) |
| `sidebar-foreground` | `sidebar` | 12.58 | 4.5 | 78 | pass |
| `sidebar-accent-foreground` | `sidebar` | 17.96 | 4.5 | 102 | pass |
| `sidebar-muted` | `sidebar` | 7.75 | 4.5 | 53 | pass |
| `sidebar-foreground` | `sidebar-raised` | 11.46 | 4.5 | 77 | pass |
| `sidebar-accent-foreground` | `sidebar-raised` | 16.35 | 4.5 | 101 | pass |
| `sidebar-muted` | `sidebar-raised` | 7.06 | 4.5 | 52 | pass |
| `sidebar-foreground` | `sidebar-accent` | 8.98 | 4.5 | 74 | pass |
| `sidebar-accent-foreground` | `sidebar-accent` | 12.81 | 4.5 | 98 | pass |
| `sidebar-muted` | `sidebar-accent` | 5.53 | 4.5 | 48 | pass |
| `sidebar-foreground` | `sidebar-accent/60 on sidebar` | 10.55 | 4.5 | 76 | pass |
| `sidebar-accent-foreground` | `sidebar-accent/60 on sidebar` | 15.06 | 4.5 | 100 | pass |
| `sidebar-muted` | `sidebar-accent/60 on sidebar` | 6.50 | 4.5 | 51 | pass |
| `sidebar-section` | `sidebar` | 10.38 | 4.5 | 67 | pass |
| `sidebar-primary` | `sidebar` | 7.13 | 3.0 | 49 | pass (UI 3:1) |
| `sidebar-primary` | `sidebar-accent` | 5.09 | 3.0 | 45 | pass (UI 3:1) |
| `sidebar-glow` | `sidebar` | 9.83 | 3.0 | 64 | pass (UI 3:1) |
| `sidebar-glow` | `sidebar-accent` | 7.01 | 3.0 | 60 | pass (UI 3:1) |
| `sidebar-ring` | `sidebar-raised` | 6.49 | 3.0 | 48 | pass (UI 3:1) |
| `sidebar-ring` | `sidebar-accent` | 5.09 | 3.0 | 45 | pass (UI 3:1) |
| `primary-foreground` | `primary` | 7.23 | 4.5 | 56 | pass |
| `info-foreground` | `info` | 9.02 | 4.5 | 64 | pass |
| `warning-foreground` | `warning` | 9.29 | 4.5 | 67 | pass |
| `success-foreground` | `success` | 9.48 | 4.5 | 67 | pass |
| `brand-950` | `brand-400` | 6.07 | 4.5 | 49 | pass |
| `hero-foreground` | `hero-from` | 10.02 | 4.5 | 94 | pass |
| `hero-muted` | `hero-from` | 7.04 | 4.5 | 70 | pass |
| `hero-foreground` | `hero-to` | 15.29 | 4.5 | 102 | pass |
| `hero-muted` | `hero-to` | 10.75 | 4.5 | 78 | pass |
| `hero-foreground` | `hero-from/50 on hero-to` | 12.57 | 4.5 | 99 | pass |
| `hero-muted` | `hero-from/50 on hero-to` | 8.84 | 4.5 | 75 | pass |
| `gradient-foreground` | `gradient-from` | 6.26 | 4.5 | 86 | pass |
| `gradient-foreground` | `gradient-via` | 6.68 | 4.5 | 87 | pass |
| `gradient-foreground` | `gradient-to` | 6.24 | 4.5 | 84 | pass |
| `gradient-foreground` | `gradient-from/50 on gradient-via` | 6.63 | 4.5 | 87 | pass |
| `gradient-foreground` | `gradient-via/50 on gradient-to` | 6.73 | 4.5 | 87 | pass |
| `gradient-text-from` | `background` | 9.92 | 4.5 | 67 | pass |
| `gradient-text-from` | `card` | 9.23 | 4.5 | 66 | pass |
| `gradient-text-via` | `background` | 8.84 | 4.5 | 61 | pass |
| `gradient-text-via` | `card` | 8.23 | 4.5 | 60 | pass |
| `gradient-text-to` | `background` | 9.38 | 4.5 | 64 | pass |
| `gradient-text-to` | `card` | 8.73 | 4.5 | 63 | pass |
| `foreground` | `gradient-soft-from` | 13.63 | 4.5 | 95 | pass |
| `muted-foreground` | `gradient-soft-from` | 8.03 | 4.5 | 63 | pass |
| `primary` | `gradient-soft-from` | 6.84 | 4.5 | 55 | pass |
| `foreground` | `gradient-soft-to` | 13.95 | 4.5 | 96 | pass |
| `muted-foreground` | `gradient-soft-to` | 8.21 | 4.5 | 63 | pass |
| `primary` | `gradient-soft-to` | 7.00 | 4.5 | 55 | pass |
| `foreground` | `glass/90 on background` | 15.17 | 4.5 | 97 | pass |
| `muted-foreground` | `glass/90 on background` | 8.93 | 4.5 | 64 | pass |
| `ring` | `glass/90 on background` | 6.39 | 3.0 | 48 | pass (UI 3:1) |
| `foreground` | `glass/90 on card` | 15.05 | 4.5 | 97 | pass |
| `muted-foreground` | `glass/90 on card` | 8.86 | 4.5 | 64 | pass |
| `ring` | `glass/90 on card` | 6.34 | 3.0 | 48 | pass (UI 3:1) |
| `hero-foreground` | `hero-foreground/10 on hero-from` | 7.68 | 4.5 | 89 | pass |
| `hero-muted` | `hero-foreground/10 on hero-from` | 5.40 | 4.5 | 65 | pass |
| `foreground` | `glass/90 on hero-from` | 14.53 | 4.5 | 96 | pass |
| `muted-foreground` | `glass/90 on hero-from` | 8.56 | 4.5 | 63 | pass |
| `ring` | `glass/90 on hero-from` | 6.12 | 3.0 | 48 | pass (UI 3:1) |
| `hero-foreground` | `hero-foreground/10 on hero-to` | 11.56 | 4.5 | 98 | pass |
| `hero-muted` | `hero-foreground/10 on hero-to` | 8.12 | 4.5 | 73 | pass |
| `foreground` | `glass/90 on hero-to` | 14.98 | 4.5 | 96 | pass |
| `muted-foreground` | `glass/90 on hero-to` | 8.82 | 4.5 | 64 | pass |
| `ring` | `glass/90 on hero-to` | 6.31 | 3.0 | 48 | pass (UI 3:1) |
| `foreground` | `background/60 on card` | 15.74 | 4.5 | 97 | pass |
| `muted-foreground` | `background/60 on card` | 9.27 | 4.5 | 64 | pass |
| `muted-foreground` | `card/50 on background` | 9.20 | 4.5 | 64 | pass |
| `gradient-text-from` | `card/50 on background` | 9.58 | 4.5 | 66 | pass |
| `gradient-text-to` | `card/50 on background` | 9.07 | 4.5 | 64 | pass |
| `foreground` | `accent/60 on card` | 13.35 | 4.5 | 95 | pass |
| `gradient-text-from` | `gradient-soft-from` | 8.36 | 4.5 | 65 | pass |
| `gradient-text-via` | `gradient-soft-from` | 7.46 | 4.5 | 59 | pass |
| `gradient-text-to` | `gradient-soft-from` | 7.91 | 4.5 | 62 | pass |
| `gradient-text-from` | `gradient-soft-to` | 8.55 | 4.5 | 65 | pass |
| `gradient-text-via` | `gradient-soft-to` | 7.63 | 4.5 | 59 | pass |
| `gradient-text-to` | `gradient-soft-to` | 8.09 | 4.5 | 62 | pass |
| `gradient-text-from` | `popover` | 8.66 | 4.5 | 65 | pass |
| `gradient-text-via` | `popover` | 7.72 | 4.5 | 59 | pass |
| `gradient-text-to` | `popover` | 8.19 | 4.5 | 62 | pass |
| `skeleton` | `background` | 1.24 | - | 0 | decorative (exempt) |
| `skeleton` | `card` | 1.15 | - | 0 | decorative (exempt) |
| `skeleton-highlight` | `skeleton` | 1.24 | - | 0 | decorative (exempt) |
| `sidebar-border` | `sidebar` | 1.22 | - | 0 | decorative (exempt) |
| `border` | `card` | 1.34 | - | 0 | decorative (exempt) |
| `border` | `background` | 1.44 | - | 0 | decorative (exempt) |

Worst gated pair (dark): input on popover at 3.54:1

Worst sidebar text pair (dark): sidebar-muted on sidebar-accent at 5.53:1 (needs 4.5)

Worst sidebar UI pair (dark): sidebar-primary on sidebar-accent at 5.09:1 (needs 3.0)


#### Chart slots against the card surface (relief rule: legend + labels always shown)

| Slot | Light | ratio on card | Dark | ratio on card |
|---|---|---:|---|---:|
| chart-1 | `#2a78d6` | 4.42 | `#3987e5` | 4.71 |
| chart-2 | `#eb6834` | 3.20 | `#d95926` | 4.42 |
| chart-3 | `#1baf7a` | 2.82 | `#199e70` | 5.04 |
| chart-4 | `#eda100` | 2.17 | `#c98500` | 5.58 |
| chart-5 | `#e87ba4` | 2.69 | `#d55181` | 4.35 |
| chart-6 | `#008300` | 4.95 | `#008300` | 3.47 |

Hero `hero-from` with white copy: 10.46:1

Hero `hero-to` with white copy: 15.97:1

failures: 0

## Landing hero — light mode references (amendment 3, 2026-10-24)

Collected for the landing hero rebuild (light mode looked broken: a dark band with dark copy).
Web search returned profile/tag pages rather than rated shots (Dribbble/Behance like counts were
not retrievable in this pass), so the list leans on shipped sites the owner can open today; the
Dribbble/Behance pattern is recorded as a trend, not a rated shot.

| # | Reference | Hero background | How the hero ends | 3D / illustration | One viewport? |
|---|---|---|---|---|---|
| 1 | stripe.com | light canvas + animated aurora mesh (violet/orange/cyan) clipped by a slanted edge | angled cut that is part of the gradient, product cards overlap it | none; product UI cards | yes |
| 2 | vercel.com | near-white with a radial glow + fine grid fading out | grid mask fades into the canvas | geometric prism (render) | yes |
| 3 | linear.app (light pages, e.g. /method) | off-white canvas, very soft radial tint | fades into canvas; a product screenshot rises out of the hero | product screenshot in perspective | yes |
| 4 | notion.so | white canvas, no mesh | flat; content continues | hand-drawn illustrations | yes |
| 5 | framer.com | light/dark per page, soft blurred blobs | blobs fade, next section on same canvas | 3D renders + UI collage | yes |
| 6 | cal.com | light grey canvas, subtle radial tint | product card floats over the hero edge | product UI card | yes |
| 7 | spline.design | light canvas with a live 3D scene | scene fades into canvas | real-time 3D, soft materials, contact shadows | yes |
| 8 | tealhq.com | light canvas, soft brand tint blocks | flat; logo strip directly below | product screenshots | mostly |
| 9 | rezi.ai | white canvas | flat; trust strip | product screenshot | yes |
| 10 | kickresume.com | light canvas, pastel shapes | flat | resume template renders | yes |
| 11 | canva.com/ai-resume-builder | white canvas | flat | resume preview image | yes |
| 12 | Dribbble "SaaS landing 3D" trend (Floeb/Axeta-style shots) | light canvas + aurora gradient + glass chips | gradient mask fade | glossy 3D object + floating glass chips | yes |

Shared traits: light canvas (never a dark band in light mode); 1–3 radial brand tints at low
alpha, sometimes a fine grid that fades radially; near-black display headline with ONE highlighted
phrase; muted body copy; gradient primary + outline secondary CTA; hero ends by fading into the
canvas or by a product card overlapping the edge — never a hard horizontal cut; 3D objects are few,
soft (PBR, matte whites, one accent colour, contact shadows); dark mode keeps a deep tinted surface
with glows.

Direction chosen: light = canvas + soft indigo/violet/fuchsia mesh (10–24 %) + 56 px grid with a
radial mask, foreground headline with "never invents a fact." in the per-theme gradient text,
muted-foreground body; dark = the existing deep `.bg-hero` band + glows. Both fade into the canvas
through a `mask-image` (option i), so the "Built for" strip rises out of the hero. The 3D scene was
rebuilt in react-three-fiber (physical materials, procedural Lightformer environment, contact
shadow, Float idle, spring entrance, ±6° parallax): resume card + match chip + check badge.
