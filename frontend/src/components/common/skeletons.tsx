/**
 * Content-shaped loading skeletons (docs/DESIGN.md §"Loading"). Every composite mirrors the
 * real component's box model — same paddings, line heights, radii and grid — so when data
 * arrives nothing moves. Pages pick the composite that matches what they will render; feature
 * folders add their own for distinctive layouts (launcher tiles, editor columns, ATS results…).
 *
 * All of them are `aria-hidden` shapes inside one `role="status"` wrapper with an sr-only
 * label, so screen readers hear "Loading <what>" once instead of a pile of empty boxes.
 */
import * as React from 'react'

import { Skeleton, SkeletonText } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { useUiStore } from '@/stores/ui'
import {
  AUTH_BRAND_ROW,
  AUTH_BRAND_TEXT,
  AUTH_CARD,
  AUTH_CARD_HEAD,
  AUTH_DESCRIPTION,
  AUTH_FOOTER,
  AUTH_FORM_COL,
  AUTH_GRID,
  AUTH_HERO,
  AUTH_HERO_ART,
  AUTH_HERO_ART_BOX,
  AUTH_HERO_BODY,
  AUTH_HERO_BRAND,
  AUTH_HERO_BRAND_TEXT,
  AUTH_HERO_CHIP,
  AUTH_HERO_DEFAULT_TITLE,
  AUTH_HERO_ITEM,
  AUTH_HERO_ITEM_BODY,
  AUTH_HERO_ITEM_TITLE,
  AUTH_HERO_LIST,
  AUTH_HERO_NOTE,
  AUTH_HERO_NOTE_TEXT,
  AUTH_HERO_TITLE,
  AUTH_HIGHLIGHTS,
  AUTH_TITLE,
  CHOOSE_ROLE_COPY,
  ROLE_LIST,
  ROLE_ROW,
} from '@/components/layout/authShell'

/** The accessible wrapper every composite uses. */
export function SkeletonRegion({
  label,
  className,
  children,
  ...props
}: { label: string; className?: string; children: React.ReactNode } & Omit<React.HTMLAttributes<HTMLDivElement>, 'children'>) {
  return (
    <div role="status" aria-busy="true" aria-live="polite" className={className} {...props}>
      <span className="sr-only">{label}</span>
      {children}
    </div>
  )
}

/** Same frame as `Card` (rounded-xl hairline, card surface). */
function CardFrame({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn('rounded-xl border border-border bg-card shadow-xs', className)}>{children}</div>
}

/* ------------------------------------------------------------------ building blocks */

/** `PageHeader`: optional eyebrow, 32 px title line, description, optional action button. */
export function PageHeaderSkeleton({ eyebrow = true, action = true, description = true }: { eyebrow?: boolean; action?: boolean; description?: boolean }) {
  return (
    <div className="space-y-3" aria-hidden>
      {eyebrow ? <Skeleton className="-mb-1 h-4 w-16" /> : null}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1 space-y-1.5">
          <Skeleton className="h-8 w-64 max-w-[70%] rounded-lg" />
          {description ? <Skeleton className="mt-1 h-4 w-[28rem] max-w-full" /> : null}
        </div>
        {action ? <Skeleton className="h-9 w-32 shrink-0 rounded-md" /> : null}
      </div>
    </div>
  )
}

/** One `StatCard` (p-5; 20 px title, 30 px figure, 16 px caption; 36 px icon tile). */
export function StatCardSkeleton() {
  return (
    <CardFrame>
      <div className="flex items-start justify-between gap-4 p-5">
        <div className="min-w-0 flex-1 space-y-2">
          <Skeleton className="h-5 w-28" />
          <Skeleton className="h-[1.875rem] w-14 rounded-lg" />
          <Skeleton className="h-4 w-36 max-w-full" />
        </div>
        <Skeleton className="size-9 shrink-0 rounded-xl" />
      </div>
    </CardFrame>
  )
}

/** A row of KPI tiles, same grid as the dashboards (2 cols from sm, 4 from xl). */
export function StatRowSkeleton({ count = 4, className }: { count?: number; className?: string }) {
  return (
    <div className={cn('grid gap-4 sm:grid-cols-2 xl:grid-cols-4', className)} aria-hidden>
      {Array.from({ length: count }, (_, index) => (
        <StatCardSkeleton key={index} />
      ))}
    </div>
  )
}

/** A generic `Card` with `CardHeader` (title + description) and a few body lines. */
export function CardSkeleton({ lines = 3, className, header = true }: { lines?: number; className?: string; header?: boolean }) {
  return (
    <CardFrame className={className}>
      {header ? (
        <div className="space-y-1.5 p-6">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-4 w-64 max-w-full" />
        </div>
      ) : null}
      <div className={cn('space-y-3 p-6', header && 'pt-0')}>
        {Array.from({ length: lines }, (_, index) => (
          <div key={index} className="flex items-center gap-3">
            <Skeleton className="size-8 shrink-0 rounded-lg" />
            <div className="min-w-0 flex-1 space-y-1.5">
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-3 w-1/3" />
            </div>
          </div>
        ))}
      </div>
    </CardFrame>
  )
}

/** Responsive grid of small entity cards (the `LoadingState variant="cards"` shape). */
export function CardGridSkeleton({ count = 6, className }: { count?: number; className?: string }) {
  return (
    <div className={cn('grid gap-4 sm:grid-cols-2 xl:grid-cols-3', className)} aria-hidden>
      {Array.from({ length: count }, (_, index) => (
        <CardFrame key={index}>
          <div className="space-y-3 p-5">
            <div className="flex items-start gap-3">
              <Skeleton className="size-10 shrink-0 rounded-lg" />
              <div className="min-w-0 flex-1 space-y-2">
                <Skeleton className="h-4 w-2/3" />
                <Skeleton className="h-3 w-1/3" />
              </div>
            </div>
            <div className="flex gap-2 pt-1">
              <Skeleton className="h-5 w-16 rounded-full" />
              <Skeleton className="h-5 w-20 rounded-full" />
            </div>
          </div>
        </CardFrame>
      ))}
    </div>
  )
}

/** `Table` inside a `Card`: 36 px header row, 41 px body rows (py-2.5 + 20 px text + hairline). */
export function TableSkeleton({ rows = 6, cols = 4, className, card = true }: { rows?: number; cols?: number; className?: string; card?: boolean }) {
  const widths = ['w-2/5', 'w-1/4', 'w-1/5', 'w-1/6', 'w-1/4', 'w-1/5']
  const table = (
    <div className="w-full" aria-hidden>
      <div className="flex h-9 items-center gap-6 border-b border-border bg-surface-2 px-4">
        {Array.from({ length: cols }, (_, col) => (
          <Skeleton key={col} className={cn('h-2.5', col === 0 ? 'w-24' : 'w-14', col === cols - 1 && 'ml-auto')} />
        ))}
      </div>
      {Array.from({ length: rows }, (_, row) => (
        <div key={row} className="flex h-[41px] items-center gap-6 border-b border-border px-4 last:border-0">
          {Array.from({ length: cols }, (_, col) => (
            <Skeleton
              key={col}
              className={cn('h-3.5', col === 0 ? 'w-2/5' : widths[(col + row) % widths.length], col === cols - 1 && 'ml-auto')}
            />
          ))}
        </div>
      ))}
    </div>
  )
  return card ? <CardFrame className={cn('overflow-hidden', className)}>{table}</CardFrame> : <div className={className}>{table}</div>
}

/** Stacked list rows in cards (the `LoadingState variant="list"` shape). */
export function ListSkeleton({ rows = 5, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn('space-y-3', className)} aria-hidden>
      {Array.from({ length: rows }, (_, index) => (
        <CardFrame key={index}>
          <div className="flex items-center gap-4 p-4">
            <Skeleton className="size-10 shrink-0 rounded-lg" />
            <div className="min-w-0 flex-1 space-y-2">
              <Skeleton className="h-4 w-1/3" />
              <Skeleton className="h-3 w-1/2" />
            </div>
            <Skeleton className="h-6 w-20 shrink-0 rounded-full" />
          </div>
        </CardFrame>
      ))}
    </div>
  )
}

/** A form card: label (20 px) + 36 px control pairs, then the action row. */
export function FormSkeleton({ fields = 4, className, card = true }: { fields?: number; className?: string; card?: boolean }) {
  const body = (
    <div className="space-y-5 p-6" aria-hidden>
      {Array.from({ length: fields }, (_, index) => (
        <div key={index} className="space-y-2">
          <Skeleton className="h-4 w-28" />
          <Skeleton className="h-9 w-full rounded-md" />
        </div>
      ))}
      <div className="flex justify-end gap-2 pt-1">
        <Skeleton className="h-9 w-20 rounded-md" />
        <Skeleton className="h-9 w-28 rounded-md" />
      </div>
    </div>
  )
  return card ? <CardFrame className={className}>{body}</CardFrame> : <div className={className}>{body}</div>
}

/** A detail page body: main column of sections + a narrow side column. */
export function DetailSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn('grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]', className)} aria-hidden>
      <div className="space-y-6">
        <CardSkeleton lines={4} />
        <CardFrame>
          <div className="space-y-3 p-6">
            <Skeleton className="h-5 w-36" />
            <SkeletonText lines={4} />
          </div>
        </CardFrame>
      </div>
      <div className="space-y-6">
        <CardFrame>
          <div className="space-y-4 p-6">
            {Array.from({ length: 4 }, (_, index) => (
              <div key={index} className="flex items-center justify-between gap-3">
                <Skeleton className="h-3.5 w-20" />
                <Skeleton className="h-3.5 w-24" />
              </div>
            ))}
          </div>
        </CardFrame>
      </div>
    </div>
  )
}

/** A chart card: header + plot area of the given height with faint bars. */
export function ChartSkeleton({ height = 260, className }: { height?: number; className?: string }) {
  const bars = [55, 80, 40, 95, 65, 75, 50, 85]
  return (
    <CardFrame className={className}>
      <div className="space-y-1.5 p-6">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-4 w-56 max-w-full" />
      </div>
      <div className="flex items-end gap-3 px-6 pb-6" style={{ height }} aria-hidden>
        {bars.map((value, index) => (
          <Skeleton key={index} className="flex-1 rounded-t-md rounded-b-none" style={{ height: `${value}%` }} />
        ))}
      </div>
    </CardFrame>
  )
}

/* ------------------------------------------------------------------ page level */

export type PageSkeletonVariant = 'dashboard' | 'list' | 'cards' | 'table' | 'form' | 'detail'

/**
 * A whole page inside `PageContainer` (same gutters and max width): the header, then content
 * shaped by `variant`. The default Suspense fallback for lazy route chunks.
 */
export function PageSkeleton({
  variant = 'dashboard',
  label = 'Loading page',
  className,
  width = 'default',
}: {
  variant?: PageSkeletonVariant
  label?: string
  className?: string
  width?: 'narrow' | 'default' | 'wide'
}) {
  return (
    <SkeletonRegion
      label={label}
      className={cn(
        'mx-auto w-full space-y-6 px-4 py-6 sm:px-6 lg:px-8',
        width === 'narrow' && 'max-w-3xl',
        width === 'default' && 'max-w-[1400px]',
        className,
      )}
    >
      <PageHeaderSkeleton action={variant !== 'form' && variant !== 'detail'} />
      {variant === 'dashboard' ? (
        <>
          <StatRowSkeleton />
          <div className="grid gap-4 lg:grid-cols-2">
            <CardSkeleton lines={2} />
            <CardSkeleton lines={2} />
          </div>
        </>
      ) : null}
      {variant === 'list' ? <ListSkeleton rows={5} /> : null}
      {variant === 'cards' ? <CardGridSkeleton count={6} /> : null}
      {variant === 'table' ? <TableSkeleton rows={8} cols={5} /> : null}
      {variant === 'form' ? <FormSkeleton fields={5} /> : null}
      {variant === 'detail' ? <DetailSkeleton /> : null}
    </SkeletonRegion>
  )
}

/** The rail's nav items in the rail's own colours (both themes). */
function RailSkeleton({ collapsed }: { collapsed: boolean }) {
  return (
    <div className="flex h-full flex-col bg-sidebar" aria-hidden>
      <div className={cn('flex h-16 shrink-0 items-center gap-2 border-b border-sidebar-border px-3', collapsed && 'justify-center')}>
        {collapsed ? (
          <Skeleton className="size-8 rounded-lg bg-sidebar-raised" />
        ) : (
          <>
            <Skeleton className="size-8 shrink-0 rounded-lg bg-sidebar-raised" />
            <Skeleton className="h-10 flex-1 rounded-lg bg-sidebar-raised" />
          </>
        )}
      </div>
      <div className="space-y-6 px-3 py-5">
        {[3, 3, 1].map((count, section) => (
          <div key={section} className="space-y-1.5">
            {collapsed ? null : <Skeleton className="mb-2 ml-3 h-2.5 w-16 bg-sidebar-raised" />}
            {Array.from({ length: count }, (_, index) => (
              <div key={index} className="flex h-9 items-center gap-3 px-3">
                <Skeleton className="size-4 shrink-0 rounded bg-sidebar-raised" />
                {collapsed ? null : <Skeleton className="h-3 flex-1 bg-sidebar-raised" />}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

/**
 * The whole app chrome while the session bootstraps: rail (desktop), topbar, a page skeleton.
 * Mirrors `AppShell`'s geometry (w-64 / w-16 rail, 64 px topbar) and the persisted rail state.
 */
export function AppShellSkeleton({ withSidebar = true }: { withSidebar?: boolean }) {
  const collapsed = useUiStore((state) => state.sidebarCollapsed)
  return (
    <SkeletonRegion label="Loading JobPilot" className="min-h-svh bg-background">
      {withSidebar ? (
        <div className={cn('fixed inset-y-0 left-0 z-40 hidden border-r border-sidebar-border lg:block', collapsed ? 'w-16' : 'w-64')}>
          <RailSkeleton collapsed={collapsed} />
        </div>
      ) : null}
      <div className={cn('flex min-h-svh flex-col', withSidebar && (collapsed ? 'lg:pl-16' : 'lg:pl-64'))}>
        <div className="flex h-16 shrink-0 items-center gap-3 border-b border-border/80 px-4 sm:px-6" aria-hidden>
          <Skeleton className="size-8 rounded-md lg:hidden" />
          <Skeleton className="h-4 w-44" />
          <div className="ml-auto flex items-center gap-2">
            <Skeleton className="hidden h-9 w-80 rounded-md md:block" />
            <Skeleton className="size-9 rounded-md" />
            <Skeleton className="size-9 rounded-md" />
            <Skeleton className="h-9 w-32 rounded-full" />
          </div>
        </div>
        <PageSkeleton label="Loading page" />
      </div>
    </SkeletonRegion>
  )
}

/**
 * Text in transparent ink on a skeleton band that wraps line by line: the bar has exactly the
 * width and line height of the real copy. `onHero`: the hero-tinted band on the indigo panel.
 */
function InkBar({ children, onHero = false }: { children: React.ReactNode; onHero?: boolean }) {
  return (
    <span
      className={cn(
        'text-transparent [box-decoration-break:clone] [-webkit-box-decoration-break:clone] motion-safe:animate-pulse',
        onHero
          ? '[background-image:linear-gradient(to_bottom,transparent_18%,hsl(var(--hero-foreground)/0.12)_18%,hsl(var(--hero-foreground)/0.12)_82%,transparent_82%)]'
          : '[background-image:linear-gradient(to_bottom,transparent_18%,hsl(var(--skeleton))_18%,hsl(var(--skeleton))_82%,transparent_82%)]',
      )}
    >
      {children}
    </span>
  )
}

/**
 * Auth pages while their chunk loads (and `/choose-role` while the session bootstraps). Renders
 * `AuthLayout`'s shell from the same `authShell.ts` classes and copy — the hero side in
 * transparent ink (its height decides the grid row on short screens) and the glass card — so the
 * page lands on exactly these boxes. `variant="roles"` sketches the role chooser (account strip,
 * one fixed-height row per role, remember row, Continue, footer); `form` the sign-in form.
 */
export function AuthSkeleton({ variant = 'form', roles = 2 }: { variant?: 'form' | 'roles'; roles?: number }) {
  const roleCopy = variant === 'roles'
  return (
    <SkeletonRegion label={roleCopy ? 'Loading roles' : 'Loading sign-in'} className={AUTH_GRID}>
      <div className={AUTH_HERO} aria-hidden data-skeleton-auth-hero="">
        <div className={AUTH_HERO_BRAND}>
          <span className="size-9 rounded-lg bg-hero-foreground/10" />
          <span className={AUTH_HERO_BRAND_TEXT}>
            <InkBar onHero>JobPilot AI</InkBar>
          </span>
        </div>
        <div className={AUTH_HERO_ART}>
          <span className={cn(AUTH_HERO_ART_BOX, "rounded-3xl bg-hero-foreground/[0.06]")} />
        </div>
        <div className={AUTH_HERO_BODY}>
          <h2 className={AUTH_HERO_TITLE}>
            <InkBar onHero>{roleCopy ? CHOOSE_ROLE_COPY.heroTitle : AUTH_HERO_DEFAULT_TITLE}</InkBar>
          </h2>
          <ul className={AUTH_HERO_LIST}>
            {AUTH_HIGHLIGHTS.map((item) => (
              <li key={item.title} className={AUTH_HERO_ITEM}>
                <span className={cn(AUTH_HERO_CHIP, 'bg-hero-foreground/10')} />
                <span className="space-y-0.5">
                  <span className={AUTH_HERO_ITEM_TITLE}>
                    <InkBar onHero>{item.title}</InkBar>
                  </span>
                  <span className={AUTH_HERO_ITEM_BODY}>
                    <InkBar onHero>{item.body}</InkBar>
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
        <p className={AUTH_HERO_NOTE}>
          <InkBar onHero>{AUTH_HERO_NOTE_TEXT}</InkBar>
        </p>
      </div>

      <div className={AUTH_FORM_COL} aria-hidden>
        <div className={cn(AUTH_CARD, 'backdrop-blur-none')} data-skeleton-auth-card="">
          <div className={AUTH_CARD_HEAD}>
            <div className={AUTH_BRAND_ROW}>
              <span className="size-7 rounded-lg bg-[hsl(var(--skeleton))]" />
              <span className={AUTH_BRAND_TEXT}>
                <InkBar>JobPilot AI</InkBar>
              </span>
            </div>
            <h1 className={AUTH_TITLE}>
              <InkBar>{roleCopy ? CHOOSE_ROLE_COPY.title : 'Sign in'}</InkBar>
            </h1>
            <p className={AUTH_DESCRIPTION}>
              <InkBar>{roleCopy ? CHOOSE_ROLE_COPY.description : 'Pick up where your job search left off.'}</InkBar>
            </p>
          </div>
          {roleCopy ? (
            <div className="space-y-4">
              <Skeleton className="h-12 w-full rounded-xl" />
              <div className={ROLE_LIST} data-skeleton-role-list="">
                {Array.from({ length: Math.max(1, roles) }, (_, index) => (
                  <Skeleton key={index} className={cn(ROLE_ROW, 'w-full rounded-2xl')} />
                ))}
              </div>
              <Skeleton className="h-5 w-60" />
              <Skeleton className="h-12 w-full rounded-lg" />
            </div>
          ) : (
            <div className="space-y-5">
              {/* authFormStyles: 20 px between fields, 20 px label line + 8 px + 48 px field. */}
              {[0, 1].map((index) => (
                <div key={index} className="space-y-2">
                  <Skeleton className="h-5 w-20" />
                  <Skeleton className="h-12 w-full rounded-xl" />
                </div>
              ))}
              <Skeleton className="h-10 w-64" />
              <Skeleton className="h-12 w-full rounded-xl" />
            </div>
          )}
          <div className={AUTH_FOOTER}>
            <InkBar>{roleCopy ? 'Not you? Sign out' : 'New here? Create an account'}</InkBar>
          </div>
        </div>
      </div>
    </SkeletonRegion>
  )
}

/** Thin indeterminate bar for background refreshes (content stays visible underneath). */
export function TopProgressBar({ active, className }: { active: boolean; className?: string }) {
  return (
    <div
      role="progressbar"
      aria-label="Refreshing"
      aria-hidden={!active}
      className={cn(
        'pointer-events-none h-0.5 w-full overflow-hidden transition-opacity duration-200',
        active && 'progress-bar-indeterminate',
        active ? 'opacity-100' : 'opacity-0',
        className,
      )}
    />
  )
}

/* ------------------------------------------------------------------ text lines */

/** [line-height box, glyph bar] per type size — matches the `fontSize` scale in tailwind.config. */
const LINE_SIZES = {
  '2xs': ['h-4', 'h-2.5'],
  xs: ['h-4', 'h-3'],
  sm: ['h-5', 'h-3.5'],
  /** `CardTitle` (text-base, leading-tight). */
  title: ['h-5', 'h-4'],
  base: ['h-6', 'h-4'],
  lg: ['h-[1.625rem]', 'h-[1.125rem]'],
  xl: ['h-7', 'h-5'],
  '2xl': ['h-8', 'h-6'],
  '3xl': ['h-9', 'h-7'],
} as const

/**
 * One line of text at a given type size: the outer box is the real line height (so the
 * layout matches to the pixel), the bar inside is the glyph height. Set the bar's width with
 * `className` (`w-1/2`, `w-24`…); `boxClassName` styles the line box (margins, flex sizing).
 */
export function SkeletonLine({
  size = 'sm',
  className,
  boxClassName,
}: {
  size?: keyof typeof LINE_SIZES
  className?: string
  boxClassName?: string
}) {
  const [box, bar] = LINE_SIZES[size]
  return (
    <div className={cn('flex items-center', box, boxClassName)} aria-hidden>
      <Skeleton className={cn('w-full', bar, className)} />
    </div>
  )
}
