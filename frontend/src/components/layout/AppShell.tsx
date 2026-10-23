import * as React from 'react'
import { Outlet, useLocation } from 'react-router-dom'

import { Sidebar } from '@/components/layout/Sidebar'
import { StaySignedInNudge } from '@/components/layout/StaySignedInNudge'
import { Topbar } from '@/components/layout/Topbar'
import { findNavItem } from '@/components/layout/navigation'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
import { TooltipProvider } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useUiStore } from '@/stores/ui'

/**
 * Application chrome: a fixed sidebar from `lg` upwards, a Sheet drawer below it, and a
 * sticky topbar. Pages render into the `<Outlet />`.
 */
export function AppShell() {
  const { pathname } = useLocation()
  const collapsed = useUiStore((state) => state.sidebarCollapsed)
  const toggleSidebar = useUiStore((state) => state.toggleSidebar)
  const [mobileOpen, setMobileOpen] = React.useState(false)

  // Animate only user-driven changes: skip the transition on the first paint so a
  // persisted "collapsed" state does not visibly slide shut on every page load.
  const [animate, setAnimate] = React.useState(false)
  React.useEffect(() => {
    const id = requestAnimationFrame(() => setAnimate(true))
    return () => cancelAnimationFrame(id)
  }, [])

  // Ctrl+B / Cmd+B toggles the rail (the convention VS Code, Linear and shadcn use).
  React.useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== 'b' || !(event.metaKey || event.ctrlKey) || event.altKey || event.shiftKey) return
      const target = event.target as HTMLElement | null
      if (target?.closest('input, textarea, select, [contenteditable="true"]')) return
      event.preventDefault()
      if (window.matchMedia('(min-width: 1024px)').matches) toggleSidebar()
      else setMobileOpen((open) => !open)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [toggleSidebar])

  const motion = animate ? 'duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:transition-none' : 'transition-none'

  const active = findNavItem(pathname)
  useDocumentTitle(active?.label)

  // Any navigation closes the mobile drawer.
  React.useEffect(() => {
    setMobileOpen(false)
  }, [pathname])

  return (
    <TooltipProvider delayDuration={200}>
      <div className="min-h-svh bg-background">
        {/* Desktop rail */}
        <aside
          className={cn(
            'fixed inset-y-0 left-0 z-40 hidden border-r border-sidebar-border transition-[width] lg:block',
            motion,
            collapsed ? 'w-16' : 'w-64',
          )}
        >
          <Sidebar collapsed={collapsed} />
        </aside>

        {/* Mobile drawer */}
        <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetContent side="left" className="w-72 p-0" showClose>
            <SheetTitle className="sr-only">Navigation</SheetTitle>
            <SheetDescription className="sr-only">JobPilot AI sections</SheetDescription>
            <Sidebar onNavigate={() => setMobileOpen(false)} />
          </SheetContent>
        </Sheet>

        <div className={cn('flex min-h-svh flex-col transition-[padding]', motion, collapsed ? 'lg:pl-16' : 'lg:pl-64')}>
          <Topbar title={active?.label} onOpenMenu={() => setMobileOpen(true)} />
          <main className="flex-1">
            <StaySignedInNudge />
            <Outlet />
          </main>
        </div>
      </div>
    </TooltipProvider>
  )
}
