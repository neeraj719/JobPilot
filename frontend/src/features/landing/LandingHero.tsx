import { ArrowDown, Check, Sparkles, UserPlus } from 'lucide-react'
import * as React from 'react'

import { Button } from '@/components/ui/button'
import { type AuthMode, authIntent } from '@/features/auth/authModal'
import { AuthHero3D } from '@/features/brand-3d/AuthHero3D'
import { goToSection } from '@/features/landing/LandingNav'
import { LANDING_CONTAINER } from '@/features/landing/layout'
import {
  HERO_BODY,
  HERO_COPY,
  HERO_CTAS,
  HERO_FACTS,
  HERO_GRID,
  HERO_H1,
  HERO_PILL,
  HERO_POSTER_SIZES,
  HERO_SCENE_BOX,
  HERO_SCENE_COL,
  HERO_SECTION,
  HERO_TEXT_COL,
  HeroBackdrop,
  ON_HERO,
} from '@/features/landing/heroShared'
import { cn } from '@/lib/utils'

export { HERO_GLOWS, HeroBackdrop, ON_HERO } from '@/features/landing/heroShared'

/** Memoised: static copy; only `onOpenAuth` (stable) is a prop. */
export const LandingHero = React.memo(function LandingHero({ onOpenAuth }: { onOpenAuth: (mode: AuthMode) => void }) {
  return (
    <section
      id="top"
      aria-labelledby="hero-title"
      data-landing-section="hero"
      className={HERO_SECTION}
    >
      <HeroBackdrop />

      <div className={cn(LANDING_CONTAINER, HERO_GRID)} data-hero-grid="">
        <div className={HERO_TEXT_COL} data-hero-text="">
          <p className={cn('animate-rise-in', HERO_PILL, ON_HERO.pill)}>
            <Sparkles className="size-3.5 text-primary dark:text-hero-foreground" aria-hidden />
            {HERO_COPY.pill}
          </p>
          <h1 id="hero-title" className={HERO_H1}>
            {HERO_COPY.title}
            <span className="text-gradient-brand">{HERO_COPY.highlight}</span>
          </h1>
          <p className={cn(HERO_BODY, ON_HERO.body)}>{HERO_COPY.body}</p>
          <div className={HERO_CTAS}>
            <Button size="lg" className="w-full min-[480px]:w-auto" onClick={() => onOpenAuth('register')} {...authIntent}>
              <UserPlus />
              {HERO_COPY.primary}
            </Button>
            <Button asChild size="lg" variant="outline" className={cn('w-full min-[480px]:w-auto', ON_HERO.outline)}>
              <a
                href="#how-it-works"
                onClick={(event) => {
                  event.preventDefault()
                  goToSection('how-it-works')
                }}
              >
                {HERO_COPY.secondary}
                <ArrowDown />
              </a>
            </Button>
          </div>
          <ul className={cn(HERO_FACTS, ON_HERO.body)}>
            {HERO_COPY.facts.map((fact) => (
              <li key={fact} className="flex items-center gap-1.5">
                <Check className="size-4 text-primary dark:text-hero-foreground" aria-hidden />
                {fact}
              </li>
            ))}
          </ul>
        </div>

        {/* The interactive scene: poster first (LCP candidate, eager + high priority), live
            three.js chunk faded in after first paint on capable desktops only. Poster and
            canvas fill the same square box, so nothing moves when the scene arrives. */}
        <div className={HERO_SCENE_COL}>
          <div className={HERO_SCENE_BOX} data-hero-box="">
            <div aria-hidden className="pointer-events-none absolute inset-[14%] rounded-full bg-glow-brand/25 blur-3xl dark:bg-glow-brand/30" />
            <div className="absolute inset-0 overflow-hidden rounded-3xl">
              <AuthHero3D priority sizes={HERO_POSTER_SIZES} liveMinWidth={768} liveOn="interaction" className="size-full" />
            </div>
            <p className="sr-only">Illustration: a resume card with a match score chip and a check badge.</p>
          </div>
        </div>
      </div>
    </section>
  )
})
