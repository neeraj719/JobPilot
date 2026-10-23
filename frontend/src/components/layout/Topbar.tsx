import { Menu, Search } from 'lucide-react'
import * as React from 'react'

import { NotificationsBell } from '@/components/layout/NotificationsBell'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { UserMenu } from '@/components/layout/UserMenu'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

export interface TopbarProps {
  /** Page title slot — defaults to the active nav item's label. */
  title?: React.ReactNode
  /** Opens the mobile navigation drawer. */
  onOpenMenu?: () => void
  className?: string
}

export function Topbar({ title, onOpenMenu, className }: TopbarProps) {
  return (
    <header
      className={cn(
        'sticky top-0 z-30 flex h-16 shrink-0 items-center gap-2 border-b border-border bg-background/80 px-4 backdrop-blur-md supports-[backdrop-filter]:bg-background/60 sm:px-6',
        className,
      )}
    >
      {/* Mobile and tablet: open the slide-in drawer. */}
      <Button variant="ghost" size="icon" className="-ml-2 shrink-0 lg:hidden" onClick={onOpenMenu} aria-label="Open navigation">
        <Menu />
      </Button>

      {title ? <h2 className="truncate text-sm font-semibold sm:text-base">{title}</h2> : null}

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
    </header>
  )
}
