# theme-identity — give the calm theme a visible identity (dark indigo sidebar, stronger type, brand touches)

You are **theme-identity**, a senior product designer who codes (React + Tailwind + Radix) on
JobPilot AI (repo `C:\Users\Neera\projects\job application`, branch `develop`). Read
`notes/resume-studio-plan.md` §1 and §7 (stack, verification protocol, shell quirks — binding),
then `docs/DESIGN.md` and `notes/theme-research.md` (the token system and research that already
exist — build on them, do not restart), then this file. Nobody else is editing the tree. Do not
commit.

## Why

The "Calm Indigo" token pass shipped (Inter, grey canvas, white cards, soft status pills, AA
contrast everywhere). The owner looked at it and said it does not read as a new theme: the
layout, the sidebar and the brand treatment are unchanged, so the login page and the app shell
look like "the same, slightly cleaner". The owner chose: **keep the calm system, add identity.**
Noticeably different at first glance, still professional, no decorative noise.

## Scope (binding)

1. **Dark indigo sidebar in both themes** — the Linear / Notion / Vercel-dashboard pattern.
   Light theme: sidebar on a deep indigo-navy (`brand-950`-ish, slightly desaturated), white
   labels, muted labels at ≥ 4.5:1, active item as a lighter indigo pill with a bright left
   bar, section titles as small caps in `brand-300`. Dark theme: the sidebar one step darker
   than the canvas with the same accent logic. The module switcher at the top sits on a
   slightly raised surface; the collapsed rail keeps the same colours. Do it through the
   `sidebar-*` tokens (`sidebar`, `sidebar-foreground`, `sidebar-accent`,
   `sidebar-accent-foreground`, `sidebar-border`, `sidebar-primary`, `sidebar-ring`) plus
   whatever `sidebar-muted` / `sidebar-section` tokens you need — add them to `docs/DESIGN.md`
   and to the contrast checker (`notes/theme-contrast.py`), which must still report 0 failures.
   Tooltips, the collapse button (`Sidebar.tsx:100`, now grey — use `bg-card`), the rail hairline
   and the mobile Sheet all follow.
2. **Stronger typographic hierarchy.** Page titles 600–700 weight with tighter tracking,
   eyebrow labels in brand colour, a clearer step between title / description / body; card
   titles at 15–16 px semibold; numbers in stat cards larger with `tabular-nums`. Adjust the
   type scale tokens, not individual pages, unless a page overrides them.
3. **Brand touches, three places only:** the launcher (`pages/Home.tsx`) greeting block gets a
   restrained indigo gradient band or mesh behind the title with the module cards overlapping
   it; the sign-in hero (`components/layout/AuthLayout.tsx`) gets the same gradient family and
   tokens (`hero-*`) instead of `text-white/…`; the logo mark uses `bg-brand-600` (dark mode
   `brand-400` tint). Gradients come from two brand tokens, defined once.
4. **Finish the layout files the previous pass could not touch:** `AppShell.tsx` ambiguous
   `ease-[cubic-bezier(...)]` → a named easing; `Topbar` blur surface on the new canvas;
   `pages/resume/AiModelSettings.tsx` "Server default" select clipping with Inter (page-level
   width fix); any remaining hard-coded Tailwind colours in `components/layout/**`,
   `pages/Home.tsx`, `pages/{Login,Register,ChooseRole,Settings}.tsx`, `src/modules/**`,
   `features/workspace/**` (`grep -rn "bg-\(green\|red\|amber\|violet\|sky\|indigo\|slate\)-"`).
5. **Density and polish where it shows:** table header row, card padding on 1440 px, the
   launcher cards' hover/focus, the switcher dropdown, the status pills in Job-Specific Resumes.
   No new components, no new npm packages.

Not in scope: new pages, copy changes, backend, the resume paper preview (keep white).

## Verify

* `npm run build` passes; contrast checker 0 failures (extend it with every new pair).
* Private servers: backend `.venv/Scripts/python.exe -m uvicorn app.main:app --port 8097`
  with `REDIS_URL=redis://localhost:6379/13`, Vite `--port 5207` pointed at it, both with the
  Bash tool's `run_in_background: true`; Playwright scripts written with the Write tool to
  `scratchpad/theme-identity/`, `page.set_default_timeout(15000)`, every Bash call with an
  explicit timeout ≤ 300000 ms. Throwaway user `identity.check@jobpilot.ai` with one resume
  imported from text and one ATS analysis; soft-delete it at the end. Stop your servers.
* **Before** shots first (the current theme), then **after**, light and dark, 1440 and 390 px:
  Login, Home launcher, Resume Dashboard, My Resumes, the editor, ATS Optimizer with results,
  Job-Specific Resumes, AI Model Settings, Settings › Workspace, the switcher open, the
  collapsed rail. `notes/screenshots/theme-identity/{before,after}/`. Look at them and fix what
  looks wrong before reporting.
* Keep `notes/theme-identity-progress.md` updated.

## Report
1. What changed at first glance, in five lines. 2. Token additions/changes and files touched.
3. Contrast summary (worst sidebar pair per theme) and build result. 4. Screenshot paths and
the three most visible before/after pairs. 5. Anything unfinished and why.
