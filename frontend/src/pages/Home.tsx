import { formatDistanceToNow } from 'date-fns'
import { ArrowRight, Hourglass, Info, LayoutGrid, Lightbulb, Lock, Pin, PinOff, Power, X } from 'lucide-react'
import * as React from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'

import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { LoadingState } from '@/components/common/LoadingState'
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
import { useAuth } from '@/hooks/useAuth'
import { errorMessage } from '@/lib/api'
import { MODULE_SWITCHER_SHORTCUT_LABEL } from '@/lib/shortcuts'
import { cn } from '@/lib/utils'
import { PageLoading } from '@/modules/ModuleRoute'
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
          <div key={index} className="space-y-1.5">
            <Skeleton className="h-6 w-10" />
            <Skeleton className="h-3 w-16" />
          </div>
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
          <dt className="mt-0.5 flex items-start gap-1 text-xs leading-snug text-muted-foreground">
            <span className="min-w-0">{stat.label}</span>
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
          <dd className="text-xl font-semibold tabular-nums leading-tight">{formatStat(stat)}</dd>
        </div>
      ))}
    </dl>
  )
}

interface ModuleCardProps {
  module: WorkspaceModule
  statsLoading: boolean
  isAdmin: boolean
  onTogglePin: (module: WorkspaceModule) => void
  pinPending: boolean
}

function ModuleCard({ module, statsLoading, isAdmin, onTogglePin, pinPending }: ModuleCardProps) {
  const definition = getModuleDefinition(module.code)
  const Icon = moduleIcon(module.code, module.icon)
  const accent = accentClasses(module.accent)
  const openable = module.available && Boolean(definition)
  const preload = () => void definition?.preload?.().catch(() => undefined)

  const copy = unavailableCopy(module.unavailable_reason)
  const reason = copy.explanation
  const ReasonIcon =
    module.unavailable_reason === 'coming_soon' ? Hourglass : module.unavailable_reason === 'platform_disabled' ? Power : Lock

  const heading = (
    <span className="flex items-center gap-2">
      <span className="truncate text-base font-semibold">{module.name}</span>
      {module.is_pinned ? <Pin className="size-3.5 shrink-0 text-muted-foreground" aria-label="Pinned" /> : null}
    </span>
  )

  return (
    <li
      className={cn(
        'group relative flex min-h-52 flex-col overflow-hidden rounded-xl border border-border bg-card p-5 shadow-sm',
        'transition-[border-color,box-shadow] duration-200 motion-reduce:transition-none',
        openable
          ? 'hover:border-primary/40 hover:shadow-md focus-within:border-primary/50 focus-within:shadow-md'
          : 'bg-muted/30',
      )}
    >
      <span className={cn('absolute inset-x-0 top-0 h-1', openable ? accent.bar : 'bg-border')} aria-hidden />

      <div className="flex items-start gap-3">
        <span
          className={cn(
            'flex size-11 shrink-0 items-center justify-center rounded-lg',
            openable ? accent.soft : 'bg-muted text-muted-foreground',
          )}
        >
          <Icon className="size-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          {openable && definition ? (
            <Link
              to={definition.homePath}
              data-module-card
              onMouseEnter={preload}
              onFocus={preload}
              className="rounded-sm focus-visible:outline-none after:absolute after:inset-0 after:content-['']"
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
                className="rounded-sm text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring after:absolute after:inset-0 after:content-['']"
              >
                {heading}
              </span>
            </SimpleTooltip>
          )}
          <p id={`module-${module.code}-tagline`} className="mt-0.5 text-sm text-muted-foreground">
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

      <div className="mt-5 flex-1">
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

      <div className="mt-5 flex items-center justify-between gap-2 text-sm">
        {openable ? (
          <span className="inline-flex items-center gap-1 font-medium text-primary">
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
  const { user, isAdmin } = useAuth()
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

  return (
    <PageContainer width="default" className="max-w-6xl">
      <header className="space-y-1 pt-2 sm:pt-6">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{greeting(user?.full_name)}</h1>
        <p className="text-sm text-muted-foreground sm:text-base">
          Choose where to work. Each module has its own menu; switch any time from the module menu at the top of the
          sidebar.
        </p>
      </header>

      {showTips ? (
        <div className="flex items-start gap-3 rounded-lg border border-border bg-card/60 px-4 py-3 text-sm">
          <Lightbulb className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
          <p className="flex-1 text-muted-foreground">
            Press{' '}
            <kbd className="rounded border border-border bg-muted px-1.5 font-mono text-[11px] text-foreground">
              {MODULE_SWITCHER_SHORTCUT_LABEL}
            </kbd>{' '}
            anywhere to switch modules. Pin the ones you use most, and choose where you land after signing in in{' '}
            <Link to="/settings?section=workspace" className="font-medium text-primary underline-offset-4 hover:underline">
              Settings › Workspace
            </Link>
            . Profile and Settings are always in your account menu.
          </p>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="-my-1 -mr-2 size-7 shrink-0"
            onClick={dismissTips}
            aria-label="Hide tips"
          >
            <X />
          </Button>
        </div>
      ) : null}

      {base.isPending && !withSummary.data ? (
        <LoadingState variant="cards" rows={3} />
      ) : base.isError && !withSummary.data ? (
        <ErrorState error={base.error} title="Could not load your modules" onRetry={() => void base.refetch()} />
      ) : modules.length === 0 ? (
        <EmptyState
          icon={LayoutGrid}
          title="No modules available"
          description="Nothing is switched on for your account yet. Ask an administrator to turn a module on."
        />
      ) : (
        <section aria-labelledby="modules-heading">
          <h2 id="modules-heading" className="sr-only">
            Modules
          </h2>
          <ul
            ref={gridRef}
            onKeyDown={onGridKeyDown}
            className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3"
            aria-label="Modules — use the arrow keys to move, Enter to open"
          >
            {modules.map((module) => (
              <ModuleCard
                key={module.code}
                module={module}
                statsLoading={statsLoading}
                isAdmin={isAdmin}
                onTogglePin={togglePin}
                pinPending={updateModule.isPending}
              />
            ))}
          </ul>
        </section>
      )}
    </PageContainer>
  )
}
