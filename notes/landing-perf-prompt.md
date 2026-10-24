# landing-perf — reload skeleton, light-mode bento, wider auth modals, React performance pass

You are the landing/auth agent (keep `notes/theme-identity-progress.md` as the progress file, add a
"landing-perf" entry). Read `notes/resume-studio-plan.md` §1 and §7 (verification protocol, shell
quirks), `docs/DESIGN.md` v2, then this file. No other agent is editing the tree now, so you own all
of `frontend/`. Do not commit. Owner feedback from 2026-10-24, with screenshots reviewed by the designer.

## A. Reload of `/` shows a "blue screen" instead of the shimmer (bug)

Diagnosis from the designer: `src/features/landing/LandingSkeleton.tsx` still renders the hero
region with `bg-hero` (the deep indigo band) and `HeroBar` at `bg-hero-foreground/10`, which is
the pre-amendment-3 design. In light mode the real hero is now the light mesh, so a reload paints a
large dark blue block with almost invisible bars, then snaps to the light hero. Fix:
1. Rebuild `LandingSkeleton` to mirror the current hero exactly per theme: same container, same
   mesh background (light) / band (dark), same nav height, same two-column grid, same 3D box size
   (the square poster box) as a shimmering block, same headline/paragraph/CTA bar sizes, and the
   "Built for" strip. Use the shared shimmer `Skeleton` on the light mesh and the hero-tinted bar
   only in dark mode. Zero layout shift between skeleton and real hero (measure the bounding boxes
   of nav, headline block, 3D box and strip: skeleton vs loaded, both themes, 1440 and 390).
2. Check what paints BEFORE React: `index.html` body has no background colour, so the very first
   frame is white in dark mode / canvas in light mode until CSS loads. Add an inline, theme-aware
   `<style>` for `html { background: #f6f7fa }` / dark `#11141a` (match the tokens; follow the
   same theme resolution the app uses: stored preference → `prefers-color-scheme`) so there is no
   flash. If the app resolves the theme in JS, add a tiny inline script in `<head>` that sets
   `data-theme` / `class="dark"` before first paint (standard no-flash pattern).
3. Make sure the landing route does not wait for the auth bootstrap when there is no token: with
   no refresh cookie / remembered device, render the landing immediately (skeleton only while the
   `Landing` chunk loads). Prefetch the `Landing` chunk from the skeleton (`modulepreload` or an
   `import()` on mount) so the skeleton is short. Record frames with Playwright (throttled network,
   a screenshot every 100 ms for 1.5 s) and keep them as `after/reload-frames-{light,dark}-N.png`.

## B. Light theme: bento tile is dark-on-dark (bug, owner screenshot)

The large "Write it once, in a real editor" tile in `LandingSections.tsx` keeps the deep indigo
gradient in light mode while its title, paragraph, three sub-cards and the four chips render in
dark text — unreadable. Apply the same rule as the hero: in LIGHT mode the featured tile sits on
the light surface with the soft brand mesh / `gradient-brand-soft` and `text-foreground`; or, if
you keep it dark on purpose, every text, sub-card border and chip must use `hero-foreground` /
`hero-muted` tokens and pass 4.5:1 measured against the rendered pixels. Audit EVERY landing
section and the final CTA for the same mistake (any `bg-hero`, `bg-gradient-brand` or dark surface
whose children use `text-foreground` / `text-muted-foreground` / `border-border`). Add a Playwright
contrast sweep that samples each text element on the landing page against its backdrop in both
themes and fails below 4.5:1; print the table in the report. Add the new pairs to
`notes/theme-contrast.py` as well (the hero mesh pairs from your previous report are still missing).

## C. Login / Create account modals

1. Wider: `AuthDialog.tsx` is `sm:max-w-md` (448 px). Make it `sm:max-w-lg` on ≥ 640 and
   `md:max-w-xl` (~576 px) on ≥ 768, inputs full width, 32 px padding; the mobile bottom sheet
   stays full width. Register (more fields) may use a two-column grid for first/last name on md+.
2. Highlight the primary action per theme: "Sign in" and "Create account" buttons use the gradient
   primary variant (`bg-gradient-brand`, white text, `shadow-glow` in dark, hover lift), full width,
   44–48 px tall, with the `loading` spinner state; secondary links ("Create an account" / "Log in
   instead") in brand colour. Same on the full `/login` `/register` pages since they share the forms.
3. Verify focus trap, Esc, `?auth=` deep link and the bottom sheet still work; shots
   `after/auth-modal-{login,register}-{light,dark}-{1440,390}.png`.

## D. React performance pass (measure first, then optimise — industry practice)

Goal: the landing and the app feel instant; no blind memoisation. Use the React `<Profiler>` API
(dev build) or render-count instrumentation in a scratch script to find components that re-render
on unrelated state, then apply the right tool:
1. **Zustand selectors**: every store call selects only what it needs (no whole-store
   subscriptions); `useShallow` where several fields are read. Topbar, Sidebar, AppShell and the
   module switcher must not re-render on form typing or query refetches.
2. **react-query**: sensible `staleTime` per query family (catalog/workspace/modules 5 min,
   summaries 30 s), `placeholderData: keepPreviousData` for paginated lists, prefetch on hover /
   focus for module cards and sidebar links (`queryClient.prefetchQuery`), `select` to narrow data
   so consumers re-render only when their slice changes.
3. **Code splitting & prefetch**: keep route chunks; add idle-time prefetch of the next likely
   chunk (launcher → resume pages after first paint via `requestIdleCallback`; landing → auth
   chunk on hover of Log in / Create account). Lazy-load below-the-fold landing sections with an
   IntersectionObserver wrapper plus `content-visibility: auto` and `contain-intrinsic-size`;
   lazy-mount `HeroScene` only when the hero box is visible AND after first paint (fix the 8 ms
   before-paint gap you reported); `loading="lazy" decoding="async"` on all non-hero images;
   `fetchpriority="high"` on the hero poster only.
4. **Memoisation where profiling shows it pays**: `React.memo` on list rows (resume cards, target
   cards, version rows, suggestion cards, FAQ items) with stable callbacks (`useCallback`) and
   derived data in `useMemo`; `useDeferredValue` on search/filter inputs (Job targets, My Resumes,
   Version History filters, module search) and `startTransition` for tab/filter switches so typing
   never stalls. Do NOT wrap everything; each memo must be justified by a before/after render count.
5. **Expensive work off the render path**: the ATS score ring and animated counters use rAF or
   framer-motion values, not state per frame; the editor's live preview is debounced and rendered
   from a deferred value; lists over ~50 rows (version history, job targets table) get simple
   windowing only if such lists exist (`@tanstack/react-virtual` allowed, pinned).
6. **Error boundaries** per route chunk and per heavy widget (3D scene, charts) with a styled
   fallback (no blank screens). Keep Suspense boundaries aligned with skeletons (no nested double
   shimmer).
7. **Budgets**: main chunk ≤ 352 kB raw; Landing chunk ≤ 40 kB; no new runtime dependency except
   an optional pinned `@tanstack/react-virtual`. `npm run build` green; tsc clean.

Report the profiler numbers: for Landing, Home, Resume Dashboard, Job targets and the Editor, the
render count of the five hottest components before/after for a scripted interaction (type 10
chars in a filter, toggle a tab, trigger a background refetch), plus LCP / CLS / TBT on the
production preview for `/` and `/home` (headless Chromium, 1440, 4× CPU throttle) before/after.

## Verify
Own servers (not :8000 / :5173; fresh ports and a fresh Redis db index), `run_in_background`,
Write-tool Playwright scripts under `scratchpad/theme-identity/landing-perf/`, explicit timeouts,
throwaway user `perf.check@jobpilot.ai` soft-deleted at the end, servers stopped. Screenshots in
`notes/screenshots/theme-identity/after/` with the names above. Contrast checker 0 failures.

## Report
1. Root cause and fix for the reload blue screen, with frame paths. 2. The light-mode audit table
(section × text element × ratio, both themes). 3. Modal before/after shots. 4. Performance table
(render counts, LCP / CLS / TBT before/after, chunk table). 5. What you deliberately did not
memoise and why. 6. Anything unfinished.
