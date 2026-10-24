import { formatDistanceToNow } from 'date-fns'
import { ArrowRight, Hourglass, Info, LayoutGrid, Lightbulb, Lock, Pin, PinOff, Power, X } from 'lucide-react'
import * as React from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'

import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { SkeletonRegion } from '@/components/common/skeletons'
import { PageContainer } from '@/components/layout/PageContainer'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { toast } from '@/components/ui/toaster'
import { SimpleTooltip } from '@/components/ui/tooltip'
import {
  useUpdateModule,
  useUpdateWorkspacePreferences,
  useWorkspaceModules,
  useWorkspacePreferences,
} from '@/features/workspace/api'
import { unavailableCopy } from '@/features/workspace/copy'
import type { ModuleStat, WorkspaceModule } from '@/features/workspace/types'
import { errorMessage } from '@/lib/api'
import { MODULE_SWITCHER_SHORTCUT_LABEL } from '@/lib/shortcuts'
import { tiltHandlers } from '@/lib/tilt'
import { cn } from '@/lib/utils'
import { PageLoading } from '@/modules/ModuleRoute'
import { loadResumePages, prefetchWhenIdle } from '@/modules/prefetch'
import { useAuthStore } from '@/stores/auth'
import { accentClasses, getModuleDefinition, moduleIcon } from '@/modules/registry'
import { renderableModules } from '@/modules/useActiveModule'

function greeting(name: string | null | undefined): string {
  const hour = new Date().getHours()
  const part = hour < 5 ? 'Good evening' : hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'
  const first = name?.trim().split(/\s+/)[0]
  return first ? `${part}, ${first}` : part
}

function formatStat(stat: ModuleStat): string {
  if (stat.value === null || stat.value === undefined) return '—'
  return `${stat.value.toLocaleString()}${stat.unit ?? ''}`
}

function StatsRow({ stats, loading }: { stats: ModuleStat[]; loading: boolean }) {
  if (loading) {
    return (
      <dl className="grid grid-cols-3 gap-3" aria-busy="true">
        {Array.from({ length: 3 }, (_, index) => (
          <StatCellSkeleton key={index} />
        ))}
      </dl>
    )
  }
  if (!stats.length) return null
  return (
    <dl className="grid grid-cols-3 gap-3">
      {stats.slice(0, 3).map((stat) => (
        // Term before value in the markup (valid <dl>), value on top visually.
        <div key={stat.key} className="flex min-w-0 flex-col-reverse justify-end">
          {/* Fixed two-line label box (clamped), so every cell — and the skeleton — is 62 px. */}
          <dt className="mt-0.5 flex h-8 items-start gap-1 text-xs leading-4 text-muted-foreground" title={stat.label}>
            <span className="line-clamp-2 min-w-0">{stat.label}</span>
            {stat.hint ? (
              <SimpleTooltip label={<span className="block max-w-56">{stat.hint}</span>} side="top">
                <button
                  type="button"
                  className="relative z-10 mt-px shrink-0 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  aria-label={stat.hint}
                >
                  <Info className="size-3" aria-hidden />
                </button>
              </SimpleTooltip>
            ) : null}
          </dt>
          <dd className="h-7 truncate text-xl font-heading tabular-nums leading-7">{formatStat(stat)}</dd>
        </div>
      ))}
    </dl>
  )
}

/** One stat cell's exact box: 28 px value line, 2 px gap, 32 px label (two lines). */
function StatCellSkeleton() {
  return (
    <div className="min-w-0" aria-hidden>
      <div className="flex h-7 items-center">
        <Skeleton className="h-6 w-10" />
      </div>
      <div className="mt-0.5 h-8 space-y-1.5 pt-0.5">
        <Skeleton className="h-3 w-16 max-w-full" />
        <Skeleton className="h-3 w-10 max-w-full" />
      </div>
    </div>
  )
}

/** Every launcher tile — real or skeleton — is at least this tall (taller than any tile's
 *  content at 390–1440 px), so the grid rows never change height when data arrives. */
const TILE_MIN_H = 'min-h-[18.5rem]'

interface ModuleCardProps {
  module: WorkspaceModule
  statsLoading: boolean
  isAdmin: boolean
  onTogglePin: (module: WorkspaceModule) => void
  pinPending: boolean
  /** The module you were last in: gets the gradient border. */
  featured?: boolean
  /** Position in the grid (entrance stagger). */
  index?: number
  className?: string
}

/** Pre-rendered 3D art per module (public/3d, see LICENSES.md); a neutral shape otherwise. */
const MODULE_ART: Record<string, string> = {
  resume: '/3d/module-resume',
  apply: '/3d/module-apply',
  insights: '/3d/module-insights',
}

function ModuleArt({ code, muted }: { code: string; muted: boolean }) {
  const base = MODULE_ART[code] ?? '/3d/module-default'
  return (
    <img
      src={`${base}.webp`}
      srcSet={`${base}-240.webp 240w, ${base}.webp 480w`}
      sizes="128px"
      width={128}
      height={128}
      alt=""
      loading="lazy"
      decoding="async"
      aria-hidden
      className={cn(
        'pointer-events-none absolute bottom-2 right-2 size-20 max-w-[30%] select-none object-contain drop-shadow-[0_18px_24px_hsl(var(--shadow-color)/0.25)]',
        'transition-transform duration-500 ease-out group-hover:-translate-y-1.5 group-hover:-rotate-3 motion-reduce:transition-none',
        muted && 'opacity-45 grayscale',
      )}
    />
  )
}

function ModuleCard({ module, statsLoading, isAdmin, onTogglePin, pinPending, featured = false, index = 0, className }: ModuleCardProps) {
  const definition = getModuleDefinition(module.code)
  const Icon = moduleIcon(module.code, module.icon)
  const accent = accentClasses(module.accent)
  const openable = module.available && Boolean(definition)
  // Hover / focus intent: the module's code chunk and its first screen's data, in parallel.
  const preload = () => {
    void definition?.preload?.().catch(() => undefined)
    void definition?.prefetchData?.().catch(() => undefined)
  }

  const copy = unavailableCopy(module.unavailable_reason)
  const reason = copy.explanation
  const ReasonIcon =
    module.unavailable_reason === 'coming_soon' ? Hourglass : module.unavailable_reason === 'platform_disabled' ? Power : Lock

  const heading = (
    <span className="flex items-center gap-2">
      <span className="truncate font-display text-lg font-semibold tracking-tight">{module.name}</span>
      {module.is_pinned ? <Pin className="size-3.5 shrink-0 text-muted-foreground" aria-label="Pinned" /> : null}
    </span>
  )

  return (
    <li
      {...tiltHandlers(openable)}
      style={{ '--i': index } as React.CSSProperties}
      className={cn(
        // Opaque surfaces only (the tiles overlap the hero glow); 20 px radius bento tile.
        'tilt stagger group relative flex min-w-0 animate-rise-in flex-col overflow-hidden rounded-2xl p-5 sm:p-6',
        TILE_MIN_H,
        openable
          ? cn(
              featured ? 'border-gradient shadow-glow' : 'border border-border bg-card shadow-sm dark:shadow-highlight',
              'hover:shadow-lg',
              // Keyboard focus on the card's link rings the whole tile (not the pin button's focus).
              'ring-offset-2 ring-offset-background has-[[data-module-card]:focus-visible]:shadow-lg has-[[data-module-card]:focus-visible]:ring-2 has-[[data-module-card]:focus-visible]:ring-ring',
            )
          : 'border border-dashed border-border bg-surface-2 shadow-none',
        className,
      )}
    >
      <ModuleArt code={module.code} muted={!openable} />

      {/* NOT `relative`: the title link's stretched `after:` overlay must resolve against the
          card (`li`), not this row — otherwise only the title strip is clickable (P0, owner
          report: the tile "does nothing"). The overlay sits at z-[1] above the stats / footer
          rows; real controls (pin, admin links) are z-10 above it. */}
      <div className="flex items-start gap-3">
        <span
          className={cn(
            'flex size-9 shrink-0 items-center justify-center rounded-xl',
            openable ? accent.soft : 'bg-muted text-muted-foreground',
          )}
        >
          <Icon className="size-[1.125rem]" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          {openable && definition ? (
            <Link
              to={definition.homePath}
              data-module-card
              onMouseEnter={preload}
              onFocus={preload}
              // Links activate on Enter natively; the tile also answers Space like a button.
              onKeyDown={(event) => {
                if (event.key === ' ') {
                  event.preventDefault()
                  event.currentTarget.click()
                }
              }}
              className="rounded-sm focus-visible:outline-none after:absolute after:inset-0 after:z-[1] after:content-['']"
              aria-describedby={`module-${module.code}-tagline`}
            >
              {heading}
            </Link>
          ) : (
            <SimpleTooltip label={reason} side="top">
              <span
                data-module-card
                tabIndex={0}
                role="link"
                aria-disabled="true"
                aria-describedby={`module-${module.code}-tagline`}
                className="rounded-sm text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring after:absolute after:inset-0 after:z-[1] after:content-['']"
              >
                {heading}
              </span>
            </SimpleTooltip>
          )}
          <p id={`module-${module.code}-tagline`} className="mt-0.5 pr-2 text-sm text-muted-foreground">
            {module.tagline}
          </p>
        </div>
        {openable ? (
          <SimpleTooltip label={module.is_pinned ? 'Unpin' : 'Pin to the front'} side="top">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="relative z-10 -mr-2 -mt-2 size-8 shrink-0 text-muted-foreground opacity-70 hover:opacity-100 focus-visible:opacity-100"
              onClick={() => onTogglePin(module)}
              disabled={pinPending}
              aria-pressed={module.is_pinned}
              aria-label={module.is_pinned ? `Unpin ${module.name}` : `Pin ${module.name}`}
            >
              {module.is_pinned ? <PinOff /> : <Pin />}
            </Button>
          </SimpleTooltip>
        ) : null}
      </div>

      <div className="relative mt-6 flex-1">
        {openable ? (
          <StatsRow stats={module.summary} loading={statsLoading} />
        ) : (
          <div className="space-y-2">
            <Badge variant="muted">
              <ReasonIcon aria-hidden />
              {copy.badge}
            </Badge>
            {module.unavailable_reason === 'platform_disabled' ? (
              <p className="text-xs text-muted-foreground">{copy.explanation}</p>
            ) : null}
            {module.unavailable_reason === 'platform_disabled' && isAdmin ? (
              // The admin's way back: the platform switch in Settings › Admin.
              <Button asChild size="sm" variant="outline" className="relative z-10 mt-1">
                <Link to="/settings?section=admin" aria-label={`Enable ${module.name} for everyone in Settings › Admin`}>
                  <Power aria-hidden />
                  Enable
                </Link>
              </Button>
            ) : null}
            {module.unavailable_reason === 'disabled_for_user' && isAdmin ? (
              <p className="text-xs text-muted-foreground">
                Admin:{' '}
                <Link
                  to="/settings?section=admin"
                  className="relative z-10 font-medium text-primary underline-offset-4 hover:underline"
                >
                  turn it back on in Settings › Admin
                </Link>
              </p>
            ) : null}
          </div>
        )}
      </div>

      <div className="relative mt-6 flex flex-wrap items-center gap-x-2 gap-y-1 pr-24 text-sm">
        {openable ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-3 py-1 font-medium text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
            Open
            <ArrowRight className="size-4 transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transition-none" aria-hidden />
          </span>
        ) : (
          <span className="text-muted-foreground">Unavailable</span>
        )}
        {module.last_opened_at ? (
          <span className="truncate text-xs text-muted-foreground">
            Opened {formatDistanceToNow(new Date(module.last_opened_at), { addSuffix: true })}
          </span>
        ) : null}
      </div>
    </li>
  )
}

/** Arrow keys move between cards (row-aware), Home/End jump; Enter opens (native links). */
function useGridKeyboard(ref: React.RefObject<HTMLUListElement>) {
  return React.useCallback(
    (event: React.KeyboardEvent<HTMLUListElement>) => {
      const grid = ref.current
      if (!grid) return
      const cards = Array.from(grid.querySelectorAll<HTMLElement>('[data-module-card]'))
      const index = cards.indexOf(document.activeElement as HTMLElement)
      if (index < 0) return
      const columns = Math.max(1, getComputedStyle(grid).gridTemplateColumns.split(' ').filter(Boolean).length)
      const moves: Record<string, number> = {
        ArrowRight: index + 1,
        ArrowLeft: index - 1,
        ArrowDown: index + columns,
        ArrowUp: index - columns,
        Home: 0,
        End: cards.length - 1,
      }
      const next = moves[event.key]
      if (next === undefined) return
      event.preventDefault()
      cards[Math.min(cards.length - 1, Math.max(0, next))]?.focus()
    },
    [ref],
  )
}

/**
 * `/` and `/home`: the module launcher. After sign-in (or at `/`) it forwards straight to the
 * last module when the user chose that landing; `/home` opened from "All modules" always
 * shows the launcher, so nobody is ever trapped inside a module.
 */
export default function HomePage() {
  const location = useLocation()
  // Narrow selectors: the launcher re-renders for the name / role it shows, not for every
  // auth-store change (isLoading flips during token refresh, etc.).
  const userName = useAuthStore((state) => state.user?.full_name)
  const isAdmin = useAuthStore((state) => (state.activeRole ?? state.user?.active_role) === 'ADMIN')
  // Most launcher visits continue into Resume Studio: fetch its pages while the browser idles.
  React.useEffect(() => prefetchWhenIdle(loadResumePages), [])
  const base = useWorkspaceModules()
  const withSummary = useWorkspaceModules({ summary: true })
  const preferences = useWorkspacePreferences()
  const updateModule = useUpdateModule()
  const updatePreferences = useUpdateWorkspacePreferences()
  const gridRef = React.useRef<HTMLUListElement>(null)
  const onGridKeyDown = useGridKeyboard(gridRef)

  const isEntry = location.pathname === '/' || Boolean((location.state as { entry?: boolean } | null)?.entry)

  if (isEntry && preferences.isPending) return <PageLoading />
  if (isEntry && preferences.data?.landing === 'LAST_MODULE' && preferences.data.last_module_code) {
    const target = getModuleDefinition(preferences.data.last_module_code)
    if (target) return <Navigate to={target.homePath} replace />
  }

  const modules = renderableModules(withSummary.data ?? base.data)
  const statsLoading = !withSummary.data && !withSummary.isError
  const showTips = preferences.data?.show_tips ?? false

  function togglePin(module: WorkspaceModule) {
    updateModule.mutate(
      { code: module.code, is_pinned: !module.is_pinned },
      {
        onSuccess: (updated) =>
          toast.success(updated.is_pinned ? `${updated.name} pinned` : `${updated.name} unpinned`, {
            description: updated.is_pinned ? 'Pinned modules come first.' : undefined,
          }),
        onError: (error) => toast.error('Could not update the module', { description: errorMessage(error) }),
      },
    )
  }

  function dismissTips() {
    updatePreferences.mutate(
      { show_tips: false },
      { onError: (error) => toast.error('Could not hide the tip', { description: errorMessage(error) }) },
    )
  }

  const lastCode = preferences.data?.last_module_code ?? null
  // Module grid: 3 columns on lg. A row that would end with a hole lets its last tile stretch.
  const remainder = modules.length % 3
  const lastSpan = remainder === 2 ? 'lg:col-span-2' : remainder === 1 && modules.length > 1 ? 'lg:col-span-3' : ''

  return (
    <PageContainer width="default" className="max-w-6xl">
      {/* The greeting comes from the signed-in user (already loaded with the shell), so the hero
          renders immediately at its final size; only the module grid has a skeleton. */}
      <LauncherHero name={userName} />

      {base.isPending && !withSummary.data ? (
        <LauncherSkeleton withTips={preferences.isPending || showTips} />
      ) : base.isError && !withSummary.data ? (
        <ErrorState error={base.error} title="Could not load your modules" onRetry={() => void base.refetch()} />
      ) : (
        <section aria-labelledby="modules-heading">
          <h2 id="modules-heading" className="sr-only">
            Modules
          </h2>
          <ul
            ref={gridRef}
            onKeyDown={onGridKeyDown}
            className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3"
            aria-label="Modules — use the arrow keys to move, Enter to open"
          >
            {modules.length === 0 ? (
              <li className="md:col-span-2 lg:col-span-3">
                <EmptyState
                  icon={LayoutGrid}
                  title="No modules available"
                  description="Nothing is switched on for your account yet. Ask an administrator to turn a module on."
                />
              </li>
            ) : null}
            {modules.map((module, index) => (
              <ModuleCard
                key={module.code}
                module={module}
                statsLoading={statsLoading}
                isAdmin={isAdmin}
                onTogglePin={togglePin}
                pinPending={updateModule.isPending}
                featured={module.code === lastCode && module.available}
                index={index}
                className={index === modules.length - 1 ? lastSpan : undefined}
              />
            ))}
            {showTips ? (
              <TipsCard index={modules.length} onDismiss={dismissTips} />
            ) : preferences.isPending ? (
              // Preferences still loading: hold the tip's slot so nothing below it moves.
              <TipsCard index={modules.length} placeholder />
            ) : null}
          </ul>
        </section>
      )}
    </PageContainer>
  )
}

/**
 * The launcher hero: a full-width band on the brand gradient. Sized to fit the visible UI —
 * its height is clamped to the viewport (≈ 26 vh, 10–15 rem) so the module cards stay above the
 * fold on a 768 px laptop; on lg+ text and the 3D still sit in a two-column grid, below lg the
 * still is stacked above the text at a fixed small height. Every decoration lives inside the
 * rounded, overflow-hidden surface, positioned with `inset`, so nothing can widen the page.
 */
function LauncherHero({ name }: { name: string | null | undefined }) {
  return (
    <section
      aria-labelledby="launcher-greeting"
      className="bg-hero relative isolate w-full min-w-0 animate-rise-in overflow-hidden rounded-3xl text-hero-foreground shadow-lg"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-y-0 right-0 -z-10 w-2/3 bg-[radial-gradient(closest-side,hsl(var(--glow-brand)/0.42),transparent)]"
      />
      <div className="grid min-h-[clamp(10rem,26vh,15rem)] items-center gap-3 p-6 sm:p-8 lg:grid-cols-[minmax(0,1fr)_auto] lg:gap-10 lg:py-6">
        <img
          src="/3d/hero-scene.webp"
          srcSet="/3d/hero-scene-640.webp 640w, /3d/hero-scene.webp 1120w"
          sizes="(min-width: 1024px) 200px, 112px"
          width={300}
          height={300}
          alt=""
          aria-hidden
          decoding="async"
          className="pointer-events-none order-first h-28 w-auto max-w-full select-none justify-self-center object-contain motion-safe:animate-float lg:order-last lg:h-[clamp(8rem,20vh,12.5rem)] lg:justify-self-end"
        />
        <div className="min-w-0 space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.1em] text-hero-muted">JobPilot AI · All modules</p>
          <h1 id="launcher-greeting" className="text-3xl font-heading leading-[1.05] tracking-[-0.03em] lg:text-4xl">
            {greeting(name)}
          </h1>
          <p className="max-w-2xl text-sm leading-relaxed text-hero-muted sm:text-base">
            Choose where to work. Each module has its own menu; switch any time from the module menu at the top of the
            sidebar.
          </p>
        </div>
      </div>
    </section>
  )
}

/** The keyboard tip, as a grid item. `placeholder` renders the identical box (the real text,
 *  invisible, under a skeleton) so the slot is reserved while preferences load. */
function TipsCard({ index, onDismiss, placeholder = false }: { index: number; onDismiss?: () => void; placeholder?: boolean }) {
  return (
    <li
      className="border-gradient-soft stagger relative flex animate-rise-in flex-col justify-between gap-4 rounded-2xl p-5 sm:p-6 md:col-span-2 lg:col-span-3"
      style={{ '--i': index } as React.CSSProperties}
      aria-hidden={placeholder || undefined}
    >
      <div className={cn('flex min-w-0 items-start gap-3 text-sm', placeholder && 'invisible')}>
        <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-card text-warning shadow-xs">
          <Lightbulb className="size-[1.125rem]" aria-hidden />
        </span>
        <p className="min-w-0 flex-1 text-muted-foreground">
          Press{' '}
          <kbd className="rounded border border-border bg-card px-1.5 font-mono text-[11px] text-foreground">
            {MODULE_SWITCHER_SHORTCUT_LABEL}
          </kbd>{' '}
          anywhere to switch modules. Pin the ones you use most, and choose where you land after signing in in{' '}
          <Link
            to="/settings?section=workspace"
            tabIndex={placeholder ? -1 : undefined}
            className="font-medium text-primary underline-offset-4 hover:underline"
          >
            Settings › Workspace
          </Link>
          . Profile and Settings are always in your account menu.
        </p>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="-my-1 -mr-2 size-7 shrink-0"
          onClick={onDismiss}
          tabIndex={placeholder ? -1 : undefined}
          aria-label="Hide tips"
        >
          <X />
        </Button>
      </div>
      {placeholder ? (
        <div className="absolute inset-5 flex items-start gap-3 sm:inset-6">
          <Skeleton className="size-9 shrink-0 rounded-xl" />
          <div className="min-w-0 flex-1 space-y-2 pt-1">
            <Skeleton className="h-3.5 w-full" />
            <Skeleton className="h-3.5 w-2/3" />
          </div>
        </div>
      ) : null}
    </li>
  )
}

/** Module-grid skeleton: three tiles + the tip slot, same grid, padding and heights as the
 *  loaded launcher (tiles share TILE_MIN_H; stat cells use StatCellSkeleton). */
function LauncherSkeleton({ withTips }: { withTips: boolean }) {
  return (
    <SkeletonRegion label="Loading your modules">
      <ul className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3" aria-hidden>
        {Array.from({ length: 3 }, (_, index) => (
          <li key={index} className={cn('flex min-w-0 flex-col rounded-2xl border border-border bg-card p-5 sm:p-6', TILE_MIN_H)}>
            <div className="flex items-start gap-3">
              <Skeleton className="size-9 rounded-xl" />
              <div className="min-w-0 flex-1 space-y-2">
                <Skeleton className="h-5 w-32" />
                <Skeleton className="h-4 w-48 max-w-full" />
              </div>
            </div>
            <div className="mt-6 grid flex-1 grid-cols-3 content-start gap-3">
              {Array.from({ length: 3 }, (_, stat) => (
                <StatCellSkeleton key={stat} />
              ))}
            </div>
            <Skeleton className="mt-6 h-7 w-20 rounded-full" />
          </li>
        ))}
        {withTips ? <TipsCard index={3} placeholder /> : null}
      </ul>
    </SkeletonRegion>
  )
}
