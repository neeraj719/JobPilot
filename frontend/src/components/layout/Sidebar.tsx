import { ChevronDown, ChevronLeft } from 'lucide-react'
import * as React from 'react'
import { Link, useLocation } from 'react-router-dom'

import {
  activeNavChild,
  isNavGroupActive,
  isNavItemActive,
  RAIL_FOCUS,
  RAIL_TOOLTIP,
  type NavItem,
} from '@/components/layout/navigation'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { SimpleTooltip } from '@/components/ui/tooltip'
import { SIDEBAR_SHORTCUT_LABEL } from '@/lib/shortcuts'
import { cn } from '@/lib/utils'
import { ModuleSwitcher } from '@/modules/ModuleSwitcher'
import { useActiveModule } from '@/modules/useActiveModule'
import { useUiStore } from '@/stores/ui'

export interface SidebarProps {
  /** Collapsed rail (icons + tooltips). Ignored inside the mobile drawer. */
  collapsed?: boolean
  /** Rendered inside the mobile Sheet — hides the rail handle, closes on navigate. */
  onNavigate?: () => void
  className?: string
}

/*
 * Layout maths that keep icons still while the rail animates:
 * the rail is 64px (w-16); the column padding (px-3, 12px) plus the item padding
 * (px-3, 12px) puts every 16px icon at 24–40px, i.e. dead centre of the rail, and in
 * exactly the same place when expanded. Only the labels fade, so nothing jumps.
 *
 * Colour: the rail is the dark indigo `sidebar` surface in BOTH themes. Everything on it uses
 * the `sidebar-*` tokens only (foreground, muted, section, accent, primary, raised, border,
 * ring) — never the page tokens, which are tuned for the light canvas.
 */
const LABEL_FADE = 'whitespace-nowrap transition-[opacity,transform] duration-200 ease-out motion-reduce:transition-none'

/** The JobPilot logo tile: brand-600 (light) / brand-400 tint (dark), the same everywhere. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        'flex size-8 shrink-0 items-center justify-center rounded-lg bg-brand-600 text-brand-50 shadow-sm ring-1 ring-inset ring-brand-50/15',
        'dark:bg-brand-400 dark:text-brand-950',
        className,
      )}
      aria-hidden
    >
      <svg viewBox="0 0 24 24" className="size-4" fill="currentColor" aria-hidden>
        <path d="M20.3 3.9 5.6 9.8c-.9.4-.9 1.6 0 2l5.1 2.2 2.3 5.2c.4.9 1.6.8 2-.1l5.9-14.3c.3-.8-.4-1.5-1.2-1.2Z" />
      </svg>
    </span>
  )
}

/** The JobPilot mark. Always links to the launcher ("All modules"). */
export function BrandMark({ withName = false, onRail = false, className }: { withName?: boolean; onRail?: boolean; className?: string }) {
  return (
    <SimpleTooltip label="All modules" side="bottom" disabled={withName} className={onRail ? RAIL_TOOLTIP : undefined}>
      <Link
        to="/home"
        className={cn(
          'flex shrink-0 items-center gap-2.5 rounded-md p-1',
          onRail ? RAIL_FOCUS : 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          className,
        )}
      >
        <LogoMark />
        {withName ? (
          <span className="min-w-0">
            <span className="block truncate text-sm font-semibold leading-tight tracking-tight text-foreground">JobPilot AI</span>
            <span className="block truncate text-[11px] leading-tight text-muted-foreground">All modules</span>
          </span>
        ) : null}
        <span className="sr-only">JobPilot AI — all modules</span>
      </Link>
    </SimpleTooltip>
  )
}

/**
 * Collapse toggle pinned to the middle of the rail's right border, plus a thin full-height
 * hit area along that edge so the whole border is clickable. The round button is the
 * visible affordance; the hairline appears on hover.
 */
function SidebarRail({ collapsed }: { collapsed: boolean }) {
  const toggleSidebar = useUiStore((state) => state.toggleSidebar)
  const label = collapsed ? 'Expand sidebar' : 'Collapse sidebar'
  return (
    <div className="group/rail absolute inset-y-0 -right-2 z-50 hidden w-4 lg:block">
      {/* Full-height edge: click anywhere on the border. */}
      <button
        type="button"
        onClick={toggleSidebar}
        aria-hidden
        tabIndex={-1}
        className={cn('absolute inset-0', collapsed ? 'cursor-e-resize' : 'cursor-w-resize')}
      >
        <span className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-transparent transition-colors duration-150 group-hover/rail:bg-sidebar-primary/70" />
      </button>

      {/* The visible toggle, centred on the border line: a white (card) disc that reads on
          both the dark rail and the light canvas. */}
      <SimpleTooltip
        side="right"
        className={RAIL_TOOLTIP}
        label={
          <span className="flex items-center gap-2">
            {label}
            <kbd className="rounded border border-sidebar-border bg-sidebar px-1.5 font-mono text-[10px] text-sidebar-muted">
              {SIDEBAR_SHORTCUT_LABEL}
            </kbd>
          </span>
        }
      >
        <button
          type="button"
          onClick={toggleSidebar}
          aria-label={label}
          aria-expanded={!collapsed}
          aria-keyshortcuts="Control+B Meta+B"
          className={cn(
            'absolute left-1/2 top-1/2 flex size-6 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full',
            'border border-border bg-card text-muted-foreground shadow-sm',
            'transition-[color,background-color,border-color,box-shadow,transform] duration-150',
            'hover:scale-110 hover:border-primary/50 hover:bg-primary hover:text-primary-foreground hover:shadow-md',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
          )}
        >
          <ChevronLeft
            className={cn('size-3.5 transition-transform duration-300 motion-reduce:transition-none', collapsed && 'rotate-180')}
            aria-hidden
          />
        </button>
      </SimpleTooltip>
    </div>
  )
}

interface NavRowProps {
  item: NavItem
  pathname: string
  isCollapsed: boolean
  onNavigate?: () => void
  /** Nested rows are a little shorter and smaller. */
  depth?: 0 | 1
  /** Overrides the item's own active test (groups decide which row carries the highlight). */
  active?: boolean
}

function NavRow({ item, pathname, isCollapsed, onNavigate, depth = 0, active }: NavRowProps) {
  const isActive = active ?? isNavItemActive(item, pathname)
  const Icon = item.icon
  return (
    <SimpleTooltip label={item.label} side="right" disabled={!isCollapsed} className={RAIL_TOOLTIP}>
      <Link
        to={item.to}
        onClick={onNavigate}
        onPointerEnter={() => prefetchNavTarget(item.to)}
        onFocus={() => prefetchNavTarget(item.to)}
        aria-current={isActive ? 'page' : undefined}
        aria-label={isCollapsed ? item.label : undefined}
        className={cn(
          'group relative flex items-center gap-3 overflow-hidden rounded-md px-3 font-medium',
          depth === 0 ? 'h-9 text-sm' : 'h-8 text-[13px]',
          'transition-colors duration-150 motion-reduce:transition-none',
          RAIL_FOCUS,
          isActive
            ? 'bg-sidebar-accent text-sidebar-accent-foreground shadow-[inset_0_1px_0_0_hsl(var(--sidebar-accent-foreground)/0.06),0_6px_18px_-8px_hsl(var(--sidebar-primary)/0.6)]'
            : 'text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground',
        )}
      >
        {/* Active indicator: a short bright bar on the leading edge. */}
        <span
          className={cn(
            'absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-gradient-to-b from-sidebar-primary to-sidebar-glow transition-all duration-200',
            isActive ? 'opacity-100' : 'h-0 opacity-0',
          )}
          aria-hidden
        />
        <Icon
          className={cn(
            'shrink-0 transition-colors',
            depth === 0 ? 'size-4' : 'size-3.5',
            isActive ? 'text-sidebar-primary' : 'text-sidebar-muted group-hover:text-sidebar-accent-foreground',
          )}
          aria-hidden
        />
        <span className={cn('truncate', LABEL_FADE, isCollapsed ? 'w-0 -translate-x-1 opacity-0' : 'opacity-100')}>
          {item.label}
        </span>
      </Link>
    </SimpleTooltip>
  )
}

/**
 * A nav item with children: the parent row is the group's landing page, a chevron folds
 * the children, and the group opens itself whenever the route moves inside it. In the
 * collapsed rail only the parent icon shows (highlighted when any child is active).
 */
function NavGroup({ item, pathname, isCollapsed, onNavigate }: Omit<NavRowProps, 'depth' | 'active'>) {
  const groupActive = isNavGroupActive(item, pathname)
  const activeChild = activeNavChild(item, pathname)
  const [open, setOpen] = React.useState(groupActive)
  React.useEffect(() => {
    if (groupActive) setOpen(true)
  }, [groupActive])

  const expanded = open && !isCollapsed
  const listId = `nav-group-${item.to.replace(/\W+/g, '-')}`
  return (
    <div>
      <div className="relative">
        {/* The parent carries the highlight only while its children are hidden. */}
        <NavRow
          item={item}
          pathname={pathname}
          isCollapsed={isCollapsed}
          onNavigate={onNavigate}
          active={isCollapsed ? groupActive : groupActive && !expanded}
        />
        {!isCollapsed ? (
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            aria-controls={listId}
            aria-label={open ? `Collapse ${item.label}` : `Expand ${item.label}`}
            className={cn(
              'absolute right-1.5 top-1/2 flex size-6 -translate-y-1/2 items-center justify-center rounded-md text-sidebar-muted',
              'transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
              RAIL_FOCUS,
            )}
          >
            <ChevronDown
              className={cn('size-3.5 transition-transform duration-200 motion-reduce:transition-none', open && 'rotate-180')}
              aria-hidden
            />
          </button>
        ) : null}
      </div>
      <div
        id={listId}
        className={cn(
          'grid transition-[grid-template-rows] duration-200 ease-out motion-reduce:transition-none',
          expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]',
        )}
        aria-hidden={!expanded}
      >
        <div className="overflow-hidden">
          {/* The guide line sits under the parent icon's centre (12px padding + 8px half icon). */}
          <ul className="ml-[1.1875rem] mt-0.5 space-y-0.5 border-l border-sidebar-border pl-2.5">
            {(item.children ?? []).map((child) => (
              <li key={`${child.to}:${child.label}`}>
                <NavRow
                  item={child}
                  pathname={pathname}
                  isCollapsed={false}
                  onNavigate={onNavigate}
                  depth={1}
                  active={activeChild?.to === child.to && activeChild?.label === child.label}
                />
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}

/** Left navigation: the module switcher on top, then the active module's sections only. */
/** Hover / focus intent on a Resume Studio link: warm its first queries (on-demand chunk). */
function prefetchNavTarget(path: string) {
  if (!path.startsWith('/resume')) return
  void import('@/modules/resume/prefetchData').then((m) => m.prefetchResumePath(path)).catch(() => undefined)
}

/** Memoised: the shell re-renders on module-list refetches; the rail only needs to on its own props / route. */
export const Sidebar = React.memo(function Sidebar({ collapsed = false, onNavigate, className }: SidebarProps) {
  const { pathname } = useLocation()
  const isDrawer = Boolean(onNavigate)
  const isCollapsed = collapsed && !isDrawer
  const active = useActiveModule()
  const sections = active.definition?.navSections ?? []

  return (
    <div className={cn('relative flex h-full flex-col bg-sidebar text-sidebar-foreground', className)}>
      <div
        className={cn(
          'flex h-16 shrink-0 items-center gap-2 overflow-hidden border-b border-sidebar-border',
          isCollapsed ? 'justify-center px-3' : 'px-3',
          // The drawer's close button sits at the right end of this row.
          isDrawer && 'pr-12',
        )}
      >
        {!isCollapsed ? <BrandMark onRail /> : null}
        <ModuleSwitcher
          definition={active.definition}
          module={active.module}
          modules={active.modules}
          collapsed={isCollapsed}
          onNavigate={onNavigate}
          shortcutControlled={!isDrawer}
        />
      </div>

      <ScrollArea className="flex-1 [&_[data-radix-scroll-area-viewport]>div]:!block">
        <nav className="space-y-6 px-3 py-5" aria-label={active.definition ? `${active.module?.name ?? active.definition.name} navigation` : 'Main'}>
          {active.isLoading && !active.definition ? (
            <div className="space-y-2 px-3" aria-hidden>
              {Array.from({ length: 6 }, (_, index) => (
                <Skeleton key={index} className="h-7 w-full bg-sidebar-accent/60" />
              ))}
            </div>
          ) : null}
          {sections.map((section) => (
            <div key={section.title} className="space-y-0.5">
              <div className="relative mb-1 flex h-6 items-center px-3">
                <p
                  className={cn(
                    'text-[11px] font-semibold uppercase tracking-[0.08em] text-sidebar-section',
                    LABEL_FADE,
                    isCollapsed ? 'w-0 overflow-hidden opacity-0' : 'opacity-100',
                  )}
                  aria-hidden={isCollapsed}
                >
                  {section.title}
                </p>
                <span
                  className={cn(
                    'absolute left-1/2 top-1/2 h-px w-5 -translate-x-1/2 bg-sidebar-border transition-opacity duration-200',
                    isCollapsed ? 'opacity-100' : 'opacity-0',
                  )}
                  aria-hidden
                />
              </div>

              {section.items.map((item) =>
                item.children?.length ? (
                  <NavGroup key={item.to} item={item} pathname={pathname} isCollapsed={isCollapsed} onNavigate={onNavigate} />
                ) : (
                  <NavRow key={item.to} item={item} pathname={pathname} isCollapsed={isCollapsed} onNavigate={onNavigate} />
                ),
              )}
            </div>
          ))}
        </nav>
      </ScrollArea>

      {!isDrawer ? <SidebarRail collapsed={isCollapsed} /> : null}
    </div>
  )
})
