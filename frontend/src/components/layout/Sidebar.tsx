import { ChevronLeft } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'

import { NAV_SECTIONS, isNavItemActive } from '@/components/layout/navigation'
import { ScrollArea } from '@/components/ui/scroll-area'
import { SimpleTooltip } from '@/components/ui/tooltip'
import { SIDEBAR_SHORTCUT_LABEL } from '@/lib/shortcuts'
import { cn } from '@/lib/utils'
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
 */
const LABEL_FADE = 'whitespace-nowrap transition-[opacity,transform] duration-200 ease-out motion-reduce:transition-none'

export function SidebarBrand({ collapsed = false }: { collapsed?: boolean }) {
  return (
    <Link
      to="/dashboard"
      className="flex min-w-0 items-center gap-2.5 rounded-md px-1 py-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-primary/70 text-primary-foreground shadow-sm ring-1 ring-primary/20">
        <svg viewBox="0 0 24 24" className="size-4" fill="currentColor" aria-hidden>
          <path d="M20.3 3.9 5.6 9.8c-.9.4-.9 1.6 0 2l5.1 2.2 2.3 5.2c.4.9 1.6.8 2-.1l5.9-14.3c.3-.8-.4-1.5-1.2-1.2Z" />
        </svg>
      </span>
      <span className={cn('min-w-0', LABEL_FADE, collapsed ? 'pointer-events-none -translate-x-1 opacity-0' : 'opacity-100')} aria-hidden={collapsed}>
        <span className="block truncate text-sm font-semibold leading-tight text-foreground">JobPilot AI</span>
        <span className="block truncate text-[11px] leading-tight text-muted-foreground">Application copilot</span>
      </span>
      <span className="sr-only">JobPilot AI — go to dashboard</span>
    </Link>
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
        <span className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-transparent transition-colors duration-150 group-hover/rail:bg-primary/40" />
      </button>

      {/* The visible toggle, centred on the border line. */}
      <SimpleTooltip
        side="right"
        label={
          <span className="flex items-center gap-2">
            {label}
            <kbd className="rounded border border-border bg-muted px-1.5 font-mono text-[10px] text-muted-foreground">
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
            'border border-sidebar-border bg-background text-muted-foreground shadow-sm',
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

/** Left navigation. Rendered as a fixed rail at `lg`+ and inside a Sheet on mobile. */
export function Sidebar({ collapsed = false, onNavigate, className }: SidebarProps) {
  const { pathname } = useLocation()
  const isDrawer = Boolean(onNavigate)
  const isCollapsed = collapsed && !isDrawer

  return (
    <div className={cn('relative flex h-full flex-col bg-sidebar text-sidebar-foreground', className)}>
      <div className="flex h-16 shrink-0 items-center overflow-hidden border-b border-sidebar-border px-3">
        <SidebarBrand collapsed={isCollapsed} />
      </div>

      <ScrollArea className="flex-1 [&_[data-radix-scroll-area-viewport]>div]:!block">
        <nav className="space-y-5 px-3 py-4" aria-label="Main">
          {NAV_SECTIONS.map((section) => (
            <div key={section.title} className="space-y-0.5">
              <div className="relative flex h-6 items-center px-3">
                <p
                  className={cn(
                    'text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70',
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

              {section.items.map((item) => {
                const active = isNavItemActive(item, pathname)
                const Icon = item.icon
                return (
                  <SimpleTooltip key={item.to} label={item.label} side="right" disabled={!isCollapsed}>
                    <Link
                      to={item.to}
                      onClick={onNavigate}
                      aria-current={active ? 'page' : undefined}
                      aria-label={isCollapsed ? item.label : undefined}
                      className={cn(
                        'group relative flex h-9 items-center gap-3 overflow-hidden rounded-md px-3 text-sm font-medium',
                        'transition-colors duration-150 motion-reduce:transition-none',
                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                        active
                          ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                          : 'text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground',
                      )}
                    >
                      {/* Active indicator: a short accent bar on the leading edge. */}
                      <span
                        className={cn(
                          'absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-primary transition-all duration-200',
                          active ? 'opacity-100' : 'h-0 opacity-0',
                        )}
                        aria-hidden
                      />
                      <Icon
                        className={cn(
                          'size-4 shrink-0 transition-colors',
                          active ? 'text-primary' : 'text-muted-foreground group-hover:text-sidebar-accent-foreground',
                        )}
                        aria-hidden
                      />
                      <span className={cn('truncate', LABEL_FADE, isCollapsed ? 'w-0 -translate-x-1 opacity-0' : 'opacity-100')}>
                        {item.label}
                      </span>
                    </Link>
                  </SimpleTooltip>
                )
              })}
            </div>
          ))}
        </nav>
      </ScrollArea>

      {!isDrawer ? <SidebarRail collapsed={isCollapsed} /> : null}
    </div>
  )
}
