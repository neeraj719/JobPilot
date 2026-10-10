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
  const [mobileOpen, setMobileOpen] = React.useState(false)

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
            'fixed inset-y-0 left-0 z-40 hidden border-r border-sidebar-border transition-[width] duration-200 lg:block',
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

        <div className={cn('flex min-h-svh flex-col transition-[padding] duration-200', collapsed ? 'lg:pl-16' : 'lg:pl-64')}>
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
