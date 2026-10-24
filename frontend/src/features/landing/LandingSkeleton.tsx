import * as React from 'react'

import { LogoMark } from '@/components/layout/Sidebar'
import { SkeletonRegion } from '@/components/common/skeletons'
import { Skeleton } from '@/components/ui/skeleton'
import {
  BUILT_FOR_LABELS,
  HERO_BODY,
  HERO_COPY,
  HERO_CTAS,
  HERO_FACTS,
  HERO_GRID,
  HERO_H1,
  HERO_PILL,
  HERO_POSTER_SIZES,
  HERO_POSTER_SRC,
  HERO_POSTER_SRCSET,
  HERO_SCENE_BOX,
  HERO_SCENE_COL,
  HERO_SECTION,
  HERO_TEXT_COL,
  HeroBackdrop,
  STRIP_PILL,
  STRIP_ROW,
} from '@/features/landing/heroShared'
import { LANDING_CONTAINER } from '@/features/landing/layout'
import { loadLanding } from '@/features/landing/loadLanding'
import { cn } from '@/lib/utils'

/**
 * Text-shaped shimmer: the real copy, in transparent ink, on a skeleton band that wraps line by
 * line — so every bar has exactly the width and line height the loaded text will have. The band
 * covers the middle 64 % of each line's box (a hard-stop gradient), so tightly set headline
 * lines (leading 1.02) never overlap. Light: the `--skeleton` token on the mesh; dark (on the
 * hero band): the hero-tinted bar. (`bg-skeleton` is not a Tailwind colour — the token is
 * read directly.)
 */
const TEXT_BAR = [
  'text-transparent [box-decoration-break:clone] [-webkit-box-decoration-break:clone] motion-safe:animate-pulse',
  '[background-image:linear-gradient(to_bottom,transparent_18%,hsl(var(--skeleton))_18%,hsl(var(--skeleton))_82%,transparent_82%)]',
  'dark:[background-image:linear-gradient(to_bottom,transparent_18%,hsl(var(--hero-foreground)/0.12)_18%,hsl(var(--hero-foreground)/0.12)_82%,transparent_82%)]',
].join(' ')

/**
 * `/` while the session bootstraps or the landing chunk loads. Mirrors the current landing
 * hero per theme from the same constants (`heroShared.tsx`): navbar height and container,
 * the light mesh / dark band, the two-column grid, headline / paragraph / CTA / facts boxes,
 * the square poster box and the "Built for" strip — zero layout shift when the page arrives.
 * It also starts downloading the landing chunk, so it is on screen as briefly as possible.
 */
export function LandingSkeleton() {
  React.useEffect(() => {
    void loadLanding()
  }, [])

  return (
    <SkeletonRegion label="Loading JobPilot AI" className="min-h-svh bg-background" style={{ '--nav-h': '4rem' } as React.CSSProperties}>
      {/* Navbar: same glass bar, height, container and right-hand controls. */}
      <div className="glass sticky top-0 z-40 w-full border-b border-border/70 pt-[env(safe-area-inset-top)] dark:border-glass-border/40" aria-hidden data-skeleton-nav="">
        <div className={cn(LANDING_CONTAINER, 'flex h-16 items-center gap-1 sm:gap-2')}>
          <span className="-ml-1 flex items-center gap-2 p-1 pr-2">
            <LogoMark />
            <Skeleton className="hidden h-4 w-[5.5rem] min-[420px]:block" />
          </span>
          <span className="ml-10 hidden items-center gap-4 lg:flex">
            {[56, 88, 44, 32].map((w) => (
              <Skeleton key={w} className="h-4" style={{ width: w }} />
            ))}
          </span>
          <span className="ml-auto flex items-center gap-1 sm:gap-1.5">
            <Skeleton className="size-11 rounded-lg lg:size-9" />
            <Skeleton className="hidden h-11 w-16 rounded-lg sm:block lg:h-9" />
            <Skeleton className="h-11 w-[8.25rem] rounded-lg lg:h-9" />
            <Skeleton className="size-11 rounded-lg lg:hidden" />
          </span>
        </div>
      </div>

      {/* Hero: identical section, backdrop and grid; text replaced by text-shaped bars. */}
      <div className={HERO_SECTION} aria-hidden data-skeleton-hero="">
        <HeroBackdrop />
        <div className={cn(LANDING_CONTAINER, HERO_GRID)}>
          <div className={HERO_TEXT_COL} data-skeleton-text="">
            <p className={cn(HERO_PILL, 'ring-1 ring-inset ring-border dark:ring-hero-foreground/20')}>
              <span className="size-3.5" />
              <span className={TEXT_BAR}>{HERO_COPY.pill}</span>
            </p>
            <div className={HERO_H1}>
              <span className={TEXT_BAR}>
                {HERO_COPY.title}
                {HERO_COPY.highlight}
              </span>
            </div>
            <p className={HERO_BODY}>
              <span className={TEXT_BAR}>{HERO_COPY.body}</span>
            </p>
            <div className={HERO_CTAS}>
              <Skeleton className="h-11 w-full rounded-xl min-[480px]:w-[11.5rem] dark:bg-hero-foreground/10" />
              <Skeleton className="h-11 w-full rounded-xl min-[480px]:w-[12.25rem] dark:bg-hero-foreground/10" />
            </div>
            <ul className={HERO_FACTS}>
              {HERO_COPY.facts.map((fact) => (
                <li key={fact} className="flex items-center gap-1.5">
                  <span className="size-4" />
                  <span className={TEXT_BAR}>{fact}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className={HERO_SCENE_COL}>
            <div className={HERO_SCENE_BOX} data-skeleton-box="">
              <Skeleton className="absolute inset-[6%] rounded-3xl opacity-70 dark:bg-hero-foreground/10" />
              {/* The hero poster (preloaded by index.html with high priority) paints over the
                  shimmer as soon as it is decoded, at the hero's exact box — the page's LCP no
                  longer waits for the Landing chunk (landing-perf D). */}
              <div className="absolute inset-0 overflow-hidden rounded-3xl">
                <img
                  src={HERO_POSTER_SRC}
                  srcSet={HERO_POSTER_SRCSET}
                  sizes={HERO_POSTER_SIZES}
                  alt=""
                  width={1120}
                  height={1120}
                  decoding="async"
                  {...{ fetchpriority: 'high' }}
                  className="absolute inset-0 size-full object-contain"
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* "Built for" strip. */}
      <div className="relative w-full" aria-hidden data-skeleton-strip="">
        <div className={cn(LANDING_CONTAINER, STRIP_ROW)}>
          <span className="eyebrow">
            <span className={TEXT_BAR}>Built for</span>
          </span>
          <ul className="flex flex-wrap items-center justify-center gap-2 sm:gap-3">
            {BUILT_FOR_LABELS.map((label) => (
              <li key={label} className={STRIP_PILL}>
                <span className="size-4" />
                <span className={TEXT_BAR}>{label}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </SkeletonRegion>
  )
}
