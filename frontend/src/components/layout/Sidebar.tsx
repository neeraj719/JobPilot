import { PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'

import { NAV_SECTIONS, isNavItemActive } from '@/components/layout/navigation'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { SimpleTooltip } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { useUiStore } from '@/stores/ui'

export interface SidebarProps {
  /** Collapsed rail (icons + tooltips). Ignored inside the mobile drawer. */
  collapsed?: boolean
  /** Rendered inside the mobile Sheet — hides the collapse toggle, closes on navigate. */
  onNavigate?: () => void
  className?: string
}

export function SidebarBrand({ collapsed = false }: { collapsed?: boolean }) {
  return (
    <Link
      to="/dashboard"
      className="flex items-center gap-2.5 rounded-md px-2 py-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
        <svg viewBox="0 0 24 24" className="size-4" fill="currentColor" aria-hidden>
          <path d="M20.3 3.9 5.6 9.8c-.9.4-.9 1.6 0 2l5.1 2.2 2.3 5.2c.4.9 1.6.8 2-.1l5.9-14.3c.3-.8-.4-1.5-1.2-1.2Z" />
        </svg>
      </span>
      {!collapsed ? (
        <span className="min-w-0">
          <span className="block truncate text-sm font-semibold leading-tight">JobPilot AI</span>
          <span className="block truncate text-[11px] leading-tight text-muted-foreground">Application copilot</span>
        </span>
      ) : null}
      <span className="sr-only">JobPilot AI — go to dashboard</span>
    </Link>
  )
}

/** Left navigation. Rendered as a fixed rail at `lg`+ and inside a Sheet on mobile. */
export function Sidebar({ collapsed = false, onNavigate, className }: SidebarProps) {
  const { pathname } = useLocation()
  const toggleSidebar = useUiStore((state) => state.toggleSidebar)
  const isDrawer = Boolean(onNavigate)
  const isCollapsed = collapsed && !isDrawer

  return (
    <div className={cn('flex h-full flex-col bg-sidebar text-sidebar-foreground', className)}>
      <div className={cn('flex h-16 shrink-0 items-center border-b border-sidebar-border px-3', isCollapsed && 'justify-center px-2')}>
        <SidebarBrand collapsed={isCollapsed} />
      </div>

      <ScrollArea className="flex-1">
        <nav className={cn('space-y-6 px-3 py-4', isCollapsed && 'px-2')} aria-label="Main">
          {NAV_SECTIONS.map((section) => (
            <div key={section.title} className="space-y-1">
              {!isCollapsed ? (
                <p className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                  {section.title}
                </p>
              ) : (
                <div className="mx-auto mb-2 h-px w-6 bg-sidebar-border" aria-hidden />
              )}
              {section.items.map((item) => {
                const active = isNavItemActive(item, pathname)
                const Icon = item.icon
                const link = (
                  <Link
                    key={item.to}
                    to={item.to}
                    onClick={onNavigate}
                    aria-current={active ? 'page' : undefined}
                    className={cn(
                      'group flex items-center gap-3 rounded-md px-2 py-2 text-sm font-medium transition-colors',
                      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                      active
                        ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                        : 'text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground',
                      isCollapsed && 'justify-center px-0',
                    )}
                  >
                    <Icon className={cn('size-4 shrink-0', active && 'text-current')} aria-hidden />
                    {!isCollapsed ? <span className="truncate">{item.label}</span> : null}
                    {!isCollapsed && active ? (
                      <span className="ml-auto size-1.5 rounded-full bg-current opacity-70" aria-hidden />
                    ) : null}
                  </Link>
                )

                return isCollapsed ? (
                  <SimpleTooltip key={item.to} label={item.label} side="right">
                    {link}
                  </SimpleTooltip>
                ) : (
                  link
                )
              })}
            </div>
          ))}
        </nav>
      </ScrollArea>

      {!isDrawer ? (
        <div className={cn('shrink-0 border-t border-sidebar-border p-2', isCollapsed && 'flex justify-center')}>
          <SimpleTooltip label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} side="right" disabled={!isCollapsed}>
            <Button
              variant="ghost"
              size={isCollapsed ? 'icon-sm' : 'sm'}
              onClick={toggleSidebar}
              className={cn(!isCollapsed && 'w-full justify-start gap-2')}
              aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
              {!isCollapsed ? <span>Collapse</span> : null}
            </Button>
          </SimpleTooltip>
        </div>
      ) : null}
    </div>
  )
}
