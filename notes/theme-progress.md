# theme — progress

Stream: **theme** (design tokens, primitives, chart theme). Brief: `notes/theme-prompt.md`.
Private servers: API :8096 (live DB, `REDIS_URL=…/12`, `LLM_PROVIDER=mock`, rate limits raised
for the screenshot run only), Vite :5206. Throwaway user `theme.check@jobpilot.ai`.

## Checklist
- ✅ Read plan §1/§7 and brief
- ✅ Private servers up; throwaway user + text-imported resume + one ATS analysis (89/100)
- ✅ "Before" screenshots (9 pages × light/dark × 1440/390 = 36) → `notes/screenshots/theme/before/`
- ✅ Research (`notes/theme-research.md`) — 9 Dribbble + 9 products + 9 design-system refs
- ✅ Token system (`index.css` generated from OKLCH, `tailwind.config.ts`, `index.html` preload, Inter self-hosted)
- ✅ Contrast script + matrix (0 failures, both themes)
- ✅ Primitives (`components/ui/*`, `components/common/*`), `chart-theme.ts`, `lib/score.ts`
- ✅ Hard-coded colours outside the modules developer's files (violet -> `ai` token, sky -> `info`)
- ✅ `npm run build` (tsc + vite) passes
- ✅ "After" screenshots + visual review (28 core + 12 extras: overlays, version history, job targets, create resume) → `notes/screenshots/theme/after/`
- ✅ `docs/DESIGN.md`; checker copied to `notes/theme-contrast.py`
- ✅ Cleanup: `theme.check@jobpilot.ai` soft-deleted (master.users.deleted_at set); :8096 / :5206 stopped

## Decisions
- Screenshot script: `scratchpad/theme/shots.py before|after`. Auth/global rate limits raised via env on
  the private :8096 server only — the global limiter's Redis key gets `EXPIRE` refreshed on every
  hit (`app/core/rate_limit.py` `RedisBackend.hit`), so under steady traffic the "fixed window"
  never resets and a page-heavy Playwright run gets 429 on login. Not in my scope; noted as a follow-up.

- Input borders are deliberately 3:1 (`--input`, WCAG 1.4.11): visibly stronger than the old 1.24:1
  hairline. If the owner prefers calmer fields, that is a one-value change (documented trade-off).
- Dashboard / Jobs / Applications "after" shots redirect to the Home launcher: the modules stream's
  migration `f6b8d0c2e4a7` seeds the Job Apply module **off** platform-wide (landed mid-run, after
  my "before" set). Saved as `home-launcher-*`; not toggled by me (live DB, their decision).
- Violet "AI" colour became a token (`ai` / `ai-soft`), sky "applied" became `info-soft`.

## Blockers
- none. **Heads-up:** a *running* Vite server keeps the Tailwind config it started with (Tailwind
  3.4.19 + Node 22.18 `require` of a `.ts` config is cached, the mtime check does not evict it).
  The owner's :5173 compiles fine (no `@apply` of new utilities in `index.css`) and already shows
  the new colour values, but the new classes (`bg-success-soft`, `bg-ai-soft`, `shadow-xs`,
  `rounded-xl` radius change, `text-2xs` …) only appear after that server is restarted.
