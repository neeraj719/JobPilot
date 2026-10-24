/**
 * Everything the landing hero and its loading skeleton share: copy, layout classes, the
 * theme-aware backdrop. The skeleton (main bundle) and the real hero (Landing chunk) render
 * from the same constants, so the skeleton has exactly the hero's geometry — nothing moves
 * when the page arrives. Keep this file free of heavy imports: it ships in the main bundle.
 */
import { cn } from '@/lib/utils'

/** Keep in sync with the poster preload in index.html (`imagesizes`). */
export const HERO_POSTER_SIZES = '(min-width: 1440px) 640px, (min-width: 1024px) 45vw, 80vw'
/** The hero poster (same files as `AuthHero3D`'s still); the skeleton paints it too. */
export const HERO_POSTER_SRC = '/3d/hero-scene.webp'
export const HERO_POSTER_SRCSET = '/3d/hero-scene-640.webp 640w, /3d/hero-scene.webp 1120w'

export const HERO_COPY = {
  pill: 'Resume Studio · AI that sticks to your facts',
  title: 'Build, score and tailor your resume with AI that ',
  highlight: 'never invents a fact.',
  body: 'Bring the resume you have or start from your profile. JobPilot checks it against the job you want and suggests changes you approve one by one — nothing you did not do ever lands on the page.',
  facts: ['Works without an API key', 'Export to PDF or DOCX', 'Every change saved as a version'],
  primary: 'Create account',
  secondary: 'See how it works',
} as const

export const BUILT_FOR_LABELS = ['Resume Studio', 'ATS Optimizer', 'Tailored resumes', 'Your own AI provider'] as const

/*
 * Theme-aware hero surface (owner review, amendment 3):
 * - light: the canvas + a soft brand mesh (indigo / violet / fuchsia radial tints at 10–24 %)
 *   and a fine grid that fades out radially; copy is foreground / muted-foreground.
 * - dark: the deep `.bg-hero` band with brand glows; copy is hero-foreground / hero-muted.
 * Both fade into the page canvas through a mask, so the section never ends on a hard edge.
 */
const LIGHT_MESH = [
  // Phones: the section is tall and narrow, so the tints sit behind the copy; keep them softer.
  '[background-image:radial-gradient(60%_34%_at_92%_8%,hsl(var(--glow-brand)/0.14),transparent_70%),radial-gradient(50%_30%_at_0%_4%,hsl(var(--gradient-via)/0.08),transparent_70%),radial-gradient(70%_30%_at_60%_96%,hsl(var(--gradient-to)/0.10),transparent_72%)]',
  'sm:[background-image:radial-gradient(42%_58%_at_86%_18%,hsl(var(--glow-brand)/0.24),transparent_70%),radial-gradient(38%_52%_at_8%_12%,hsl(var(--gradient-via)/0.14),transparent_70%),radial-gradient(46%_46%_at_58%_92%,hsl(var(--gradient-to)/0.10),transparent_72%)]',
].join(' ')
const LIGHT_GRID =
  '[background-image:linear-gradient(hsl(var(--border)/0.55)_1px,transparent_1px),linear-gradient(90deg,hsl(var(--border)/0.55)_1px,transparent_1px)] [background-size:56px_56px] [mask-image:radial-gradient(70%_65%_at_70%_35%,black,transparent_75%)]'
/** Brand glows over the dark band (also used by the bento hero tile). */
export const HERO_GLOWS = [
  '[background-image:radial-gradient(60%_30%_at_96%_4%,hsl(var(--glow-brand)/0.18),transparent_70%),radial-gradient(60%_30%_at_0%_100%,hsl(var(--gradient-to)/0.22),transparent_70%)]',
  'sm:[background-image:radial-gradient(42%_55%_at_88%_12%,hsl(var(--glow-brand)/0.32),transparent_70%),radial-gradient(38%_50%_at_6%_100%,hsl(var(--gradient-to)/0.24),transparent_70%)]',
].join(' ')

const FADE = {
  bottom: '[mask-image:linear-gradient(to_bottom,black_0%,black_62%,transparent_100%)]',
  both: '[mask-image:linear-gradient(to_bottom,transparent_0%,black_22%,black_78%,transparent_100%)]',
} as const

/** The hero / CTA backdrop: an `inset-0` stack behind the content, faded into the canvas. */
export function HeroBackdrop({ fade = 'bottom', mirror = false }: { fade?: keyof typeof FADE; mirror?: boolean }) {
  return (
    <div aria-hidden className={cn('pointer-events-none absolute inset-0 -z-10', FADE[fade])}>
      <div className={cn('absolute inset-0 dark:hidden', LIGHT_MESH, mirror && '-scale-x-100')} />
      <div className={cn('absolute inset-0 dark:hidden', LIGHT_GRID)} />
      <div className="bg-hero absolute inset-0 hidden dark:block" />
      <div className={cn('absolute inset-0 hidden dark:block', HERO_GLOWS, mirror && '-scale-x-100')} />
    </div>
  )
}

/** Text colours on the backdrop, per theme. */
export const ON_HERO = {
  title: 'text-foreground dark:text-hero-foreground',
  body: 'text-muted-foreground dark:text-hero-muted',
  pill: 'bg-card/80 text-foreground ring-1 ring-inset ring-border shadow-xs dark:bg-hero-foreground/10 dark:text-hero-foreground dark:ring-hero-foreground/20 dark:shadow-none',
  /** Secondary button: the outline button in light, a hairline pill on the dark band. */
  outline:
    'dark:border-transparent dark:bg-transparent dark:text-hero-foreground dark:shadow-none dark:ring-1 dark:ring-inset dark:ring-hero-foreground/30 dark:hover:bg-hero-foreground/10 dark:hover:text-hero-foreground',
} as const

/*
 * First-view fit: on lg+ the hero is the viewport minus the navbar (`--nav-h`, set on the
 * page root) minus a 3 rem peek of the "Built for" strip; capped at viewport − navbar on
 * desktop windows tall enough for the content. Headline and 3D box scale with the viewport.
 */
export const HERO_SECTION = cn(
  'relative isolate flex w-full flex-col justify-center',
  ON_HERO.title,
  'lg:min-h-[calc(100svh_-_var(--nav-h)_-_3rem)] [@media(min-width:1280px)_and_(min-height:700px)]:max-h-[calc(100svh_-_var(--nav-h))]',
)
export const HERO_GRID = 'relative grid items-center gap-8 pb-6 pt-10 sm:pt-14 lg:grid-cols-2 lg:gap-12 lg:py-8'
export const HERO_TEXT_COL = 'min-w-0 space-y-6 xl:space-y-7'
export const HERO_PILL = 'inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium'
export const HERO_H1 =
  'max-w-[17ch] text-[clamp(2.25rem,min(5vw+1rem,7.4svh),4.5rem)] font-semibold leading-[1.02] tracking-[-0.035em] text-balance'
export const HERO_BODY = 'max-w-prose text-base sm:text-lg'
export const HERO_CTAS = 'flex flex-col gap-3 min-[480px]:flex-row'
export const HERO_FACTS = 'flex flex-wrap gap-x-5 gap-y-2 text-sm'
export const HERO_SCENE_COL = 'flex min-w-0 justify-center lg:justify-end'
/** The 3D box: square, as large as the column and the first view allow. */
export const HERO_SCENE_BOX =
  'relative aspect-square w-full max-w-[min(18rem,36svh)] sm:max-w-[min(26rem,42svh)] lg:max-w-[min(100%,40rem,calc(100svh_-_var(--nav-h)_-_7rem))]'

/** "Built for" strip layout, shared with the skeleton. */
export const STRIP_ROW = 'flex flex-col items-center gap-4 pb-6 pt-4 sm:flex-row sm:justify-between sm:gap-8 lg:pt-2'
export const STRIP_PILL = 'flex items-center gap-2 rounded-full border border-border bg-card px-3.5 py-1.5 text-sm font-medium shadow-xs dark:shadow-highlight'
