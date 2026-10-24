/**
 * Geometry shared by `AuthLayout` (auth chunk) and `AuthSkeleton` (main bundle): the split grid,
 * the form column and the glass card. One source, so the skeleton has the page's exact boxes and
 * nothing moves when the page chunk arrives. Strings only — safe for the main bundle.
 */
export const AUTH_GRID = 'grid min-h-svh bg-background lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]'
export const AUTH_HERO = 'bg-hero relative hidden flex-col overflow-hidden p-10 text-hero-foreground lg:flex xl:p-12'
export const AUTH_FORM_COL = 'relative flex items-center justify-center overflow-hidden px-4 py-12 sm:px-8'
export const AUTH_CARD =
  'glass relative w-full max-w-md space-y-6 rounded-3xl border border-border/70 p-6 shadow-xl sm:p-8 dark:border-glass-border/40 dark:shadow-highlight'
export const AUTH_CARD_HEAD = 'space-y-2 text-center lg:text-left'
export const AUTH_EYEBROW = 'text-gradient-brand font-display text-sm font-bold tracking-tight'
/** Header brand: 28 px logo mark + wordmark (`AuthBrand`), centred on phones, left on lg. */
export const AUTH_BRAND_ROW = 'flex h-7 items-center justify-center gap-2 lg:justify-start'
export const AUTH_BRAND_TEXT = 'font-display text-base font-semibold tracking-tight'
/** 30 px display title. */
export const AUTH_TITLE = 'text-3xl font-heading tracking-[-0.03em]'
/** 15 px helper line. */
export const AUTH_DESCRIPTION = 'text-[0.9375rem] leading-6 text-muted-foreground'
export const AUTH_FOOTER = 'text-center text-sm text-muted-foreground'

/* Hero side (lg+): its content height sets the grid row on short screens, so the skeleton
   renders the same copy with the same classes (in transparent ink). */
export const AUTH_HERO_BRAND = 'relative z-10 flex items-center gap-2.5'
export const AUTH_HERO_BRAND_TEXT = 'font-display text-lg font-semibold tracking-tight'
/**
 * The 3D art's own track (landing-perf E): a flex-1 row between the brand and the copy, so the
 * art takes the height left over and can never reach the headline (it used to be absolutely
 * positioned at top 5 % / max-h 45 % and touched the headline at 1366×768).
 */
export const AUTH_HERO_ART = 'relative z-0 my-6 flex min-h-[8rem] flex-1 items-center justify-end'
/** The art itself: as tall as its track allows, square, capped at 30 rem. */
export const AUTH_HERO_ART_BOX = 'aspect-square h-full max-h-[30rem] max-w-full'
export const AUTH_HERO_BODY = 'relative z-10 max-w-lg space-y-7'
export const AUTH_HERO_TITLE = 'font-display text-4xl font-semibold leading-[1.05] tracking-[-0.03em] text-balance xl:text-5xl'
export const AUTH_HERO_LIST = 'space-y-4'
export const AUTH_HERO_ITEM = 'flex gap-3'
export const AUTH_HERO_CHIP = 'mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-xl'
export const AUTH_HERO_ITEM_TITLE = 'block text-sm font-semibold'
export const AUTH_HERO_ITEM_BODY = 'block max-w-sm text-sm'
export const AUTH_HERO_NOTE = 'relative z-10 mt-10 text-xs'
export const AUTH_HERO_DEFAULT_TITLE = 'Your resume, built on facts.'
export const AUTH_HERO_NOTE_TEXT = 'Scores are estimates, not an employer’s verdict.'
export const AUTH_HIGHLIGHTS = [
  {
    title: 'Build from what you have',
    body: 'Start from your profile, a PDF or DOCX, pasted text or your LinkedIn export, and review every section.',
  },
  {
    title: 'Score it against the job',
    body: 'An estimated match from fixed rules, with the keywords you have and the ones you are missing.',
  },
  {
    title: 'You approve every change',
    body: 'Suggestions change nothing until you press Apply. Nothing you did not do is ever added.',
  },
] as const

/** `/choose-role` copy and row geometry (the skeleton renders the same text in transparent ink). */
export const CHOOSE_ROLE_COPY = {
  title: 'Choose a role',
  description: 'Your account has more than one role. Pick the one to use now; you can switch any time from the account menu.',
  heroTitle: 'Choose how you want to work today.',
} as const
/** One role option: fixed height so the list never reflows (icon chip, name, one-line description). */
export const ROLE_ROW = 'h-[4.5rem]'
export const ROLE_LIST = 'grid gap-3'
/** "Signed in as" account strip above the list. */
export const ACCOUNT_STRIP = 'flex h-12 items-center gap-3 rounded-xl bg-muted/60 px-3'
