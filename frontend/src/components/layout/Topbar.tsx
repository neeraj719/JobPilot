import { useIsFetching } from '@tanstack/react-query'
import { Menu, Search } from 'lucide-react'
import * as React from 'react'

import { TopProgressBar } from '@/components/common/skeletons'
import { NotificationsBell } from '@/components/layout/NotificationsBell'
import { BrandMark } from '@/components/layout/Sidebar'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { UserMenu } from '@/components/layout/UserMenu'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

export interface TopbarProps {
  /** Page title slot — defaults to the active nav item's label. */
  title?: React.ReactNode
  /** Opens the mobile navigation drawer. Omit it where there is no sidebar (the launcher). */
  onOpenMenu?: () => void
  /** Show the JobPilot mark on the left (the launcher has no sidebar to carry it). */
  showBrand?: boolean
  className?: string
}

/**
 * Background refreshes keep the content on screen; a thin gradient bar says "updating". The
 * `useIsFetching` subscription lives here, in a leaf, so a refetch re-renders this bar only —
 * not the whole topbar (search, bell, theme, account menu).
 */
function FetchingBar() {
  const fetching = useIsFetching() > 0
  return <TopProgressBar active={fetching} className="absolute inset-x-0 bottom-0 translate-y-px" />
}

export const Topbar = React.memo(function Topbar({ title, onOpenMenu, showBrand = false, className }: TopbarProps) {
  return (
    <header
      className={cn(
        'glass sticky top-0 z-30 flex h-16 shrink-0 items-center gap-2 border-b border-border/70 px-4 sm:px-6 dark:border-glass-border/30',
        className,
      )}
    >
      {/* Mobile and tablet: open the slide-in drawer. */}
      {onOpenMenu ? (
        <Button variant="ghost" size="icon" className="-ml-2 shrink-0 lg:hidden" onClick={onOpenMenu} aria-label="Open navigation">
          <Menu />
        </Button>
      ) : null}

      {showBrand ? <BrandMark withName className="-ml-1 mr-2" /> : null}

      {title ? <h2 className="min-w-0 truncate text-sm font-semibold tracking-tight sm:text-base">{title}</h2> : null}

      <div className="ml-auto flex items-center gap-1 sm:gap-2">
        <div className="relative hidden md:block">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            type="search"
            placeholder="Search jobs, companies, applications…"
            aria-label="Global search"
            className="h-9 w-64 pl-8 lg:w-80"
          />
        </div>
        <Button variant="ghost" size="icon" className="md:hidden" aria-label="Search">
          <Search />
        </Button>
        <NotificationsBell />
        <ThemeToggle />
        <UserMenu />
      </div>
      <FetchingBar />
    </header>
  )
})
