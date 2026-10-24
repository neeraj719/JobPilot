import { ChevronRight } from 'lucide-react'
import * as React from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'

import { Sidebar } from '@/components/layout/Sidebar'
import { StaySignedInNudge } from '@/components/layout/StaySignedInNudge'
import { Topbar } from '@/components/layout/Topbar'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useOpenModule } from '@/features/workspace/api'
import { cn } from '@/lib/utils'
import { isModuleSwitcherShortcut } from '@/lib/shortcuts'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useActiveModule } from '@/modules/useActiveModule'
import { useUiStore } from '@/stores/ui'

function isTyping(target: EventTarget | null): boolean {
  return Boolean((target as HTMLElement | null)?.closest('input, textarea, select, [contenteditable="true"]'))
}

/**
 * Application chrome: a fixed sidebar from `lg` upwards, a Sheet drawer below it, and a
 * sticky topbar. Pages render into the `<Outlet />`.
 *
 * The sidebar belongs to the active workspace module (derived from the path through the
 * module registry); the launcher (`/`, `/home`) has no sidebar at all. Account pages keep
 * the sidebar of the module the user came from.
 */
export function AppShell() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const collapsed = useUiStore((state) => state.sidebarCollapsed)
  const toggleSidebar = useUiStore((state) => state.toggleSidebar)
  const setLastModuleCode = useUiStore((state) => state.setLastModuleCode)
  const setModuleSwitcherOpen = useUiStore((state) => state.setModuleSwitcherOpen)
  const [mobileOpen, setMobileOpen] = React.useState(false)
  const active = useActiveModule()
  const showSidebar = !active.isLauncher

  // Animate only user-driven changes: skip the transition on the first paint so a
  // persisted "collapsed" state does not visibly slide shut on every page load.
  const [animate, setAnimate] = React.useState(false)
  React.useEffect(() => {
    const id = requestAnimationFrame(() => setAnimate(true))
    return () => cancelAnimationFrame(id)
  }, [])

  // Ctrl+B / Cmd+B toggles the rail (the convention VS Code, Linear and shadcn use).
  // Ctrl+Shift+M / Cmd+Shift+M opens the module switcher (the launcher on small screens).
  React.useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (isModuleSwitcherShortcut(event)) {
        event.preventDefault()
        if (showSidebar && window.matchMedia('(min-width: 1024px)').matches) setModuleSwitcherOpen(true)
        else navigate('/home')
        return
      }
      if (event.key.toLowerCase() !== 'b' || !(event.metaKey || event.ctrlKey) || event.altKey || event.shiftKey) return
      if (isTyping(event.target)) return
      if (!showSidebar) return
      event.preventDefault()
      if (window.matchMedia('(min-width: 1024px)').matches) toggleSidebar()
      else setMobileOpen((open) => !open)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [toggleSidebar, setModuleSwitcherOpen, navigate, showSidebar])

  // Entering a module records it (last opened, "land in my last module"). Once per entry,
  // not per page inside the module.
  const openModule = useOpenModule()
  const enteredCode = active.pathModule && active.module?.available ? active.pathModule.code : null
  const lastRecorded = React.useRef<string | null>(null)
  React.useEffect(() => {
    if (!enteredCode) {
      if (active.isLauncher) lastRecorded.current = null
      return
    }
    setLastModuleCode(enteredCode)
    if (lastRecorded.current === enteredCode) return
    lastRecorded.current = enteredCode
    openModule.mutate(enteredCode)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `mutate` is stable; run on entry only
  }, [enteredCode, active.isLauncher, setLastModuleCode])

  const motion = animate ? 'duration-300 ease-drawer motion-reduce:transition-none' : 'transition-none'

  const moduleName = active.pathModule ? (active.module?.name ?? active.pathModule.name) : undefined
  const pageLabel = active.navItem?.label
  useDocumentTitle(
    active.isLauncher ? 'All modules' : pageLabel && moduleName ? `${pageLabel} · ${moduleName}` : (pageLabel ?? moduleName),
  )

  // Memoised so the (memoised) topbar does not re-render when the shell does for unrelated
  // reasons (a module-list refetch, the rail animation flag).
  const homePath = active.pathModule?.homePath
  const title = React.useMemo(
    () =>
      active.isLauncher ? null : moduleName && homePath ? (
        <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1.5">
          <Link
            to={homePath}
            className="hidden shrink-0 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:inline"
          >
            {moduleName}
          </Link>
          {pageLabel ? (
            <>
              <ChevronRight className="hidden size-4 shrink-0 text-muted-foreground/70 sm:inline" aria-hidden />
              <span className="truncate" aria-current="page">
                {pageLabel}
              </span>
            </>
          ) : null}
        </nav>
      ) : (
        pageLabel
      ),
    [active.isLauncher, moduleName, homePath, pageLabel],
  )
  const openMobile = React.useCallback(() => setMobileOpen(true), [])
  const closeMobile = React.useCallback(() => setMobileOpen(false), [])

  // Any navigation closes the mobile drawer.
  React.useEffect(() => {
    setMobileOpen(false)
  }, [pathname])

  return (
    <TooltipProvider delayDuration={200}>
      <div className="min-h-svh bg-background">
        {showSidebar ? (
          <>
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
              <SheetContent
                side="left"
                className="w-72 border-sidebar-border bg-sidebar p-0 text-sidebar-foreground"
                closeClassName="right-3.5 top-[1.375rem] text-sidebar-muted ring-offset-sidebar hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus:ring-sidebar-ring"
                showClose
              >
                <SheetTitle className="sr-only">Navigation</SheetTitle>
                <SheetDescription className="sr-only">
                  {active.module?.name ?? active.definition?.name ?? 'JobPilot AI'} sections
                </SheetDescription>
                <Sidebar onNavigate={closeMobile} />
              </SheetContent>
            </Sheet>
          </>
        ) : null}

        <div
          className={cn(
            'flex min-h-svh flex-col transition-[padding]',
            motion,
            showSidebar && (collapsed ? 'lg:pl-16' : 'lg:pl-64'),
          )}
        >
          <Topbar
            title={title}
            showBrand={!showSidebar}
            onOpenMenu={showSidebar ? openMobile : undefined}
          />
          <main className="flex-1">
            <StaySignedInNudge />
            {/* Route change: 180 ms fade + 4 px lift (CSS, reduced-motion safe). */}
            <div key={pathname} className="animate-page-in">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </TooltipProvider>
  )
}
