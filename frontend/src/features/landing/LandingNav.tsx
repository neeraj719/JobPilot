import { Menu } from 'lucide-react'
import * as React from 'react'

import { LogoMark } from '@/components/layout/Sidebar'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { type AuthMode, authIntent } from '@/features/auth/authModal'
import { LANDING_CONTAINER } from '@/features/landing/layout'
import { cn } from '@/lib/utils'

export const LANDING_ANCHORS = [
  { id: 'features', label: 'Features' },
  { id: 'how-it-works', label: 'How it works' },
  { id: 'safety', label: 'Safety' },
  { id: 'faq', label: 'FAQ' },
] as const

/** Scroll to a section and move focus there (keyboard and screen-reader users land on it too). */
export function goToSection(id: string) {
  const target = document.getElementById(id)
  if (!target) return
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  target.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' })
  target.focus({ preventScroll: true })
  window.history.replaceState(window.history.state, '', `${window.location.pathname}${window.location.search}#${id}`)
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={className}>
      <span className="font-display text-[1.0625rem] font-semibold tracking-tight">JobPilot</span>{' '}
      <span className="text-gradient-brand font-display text-[1.0625rem] font-bold tracking-tight">AI</span>
    </span>
  )
}

export interface LandingNavProps {
  onOpenAuth: (mode: AuthMode) => void
  /** The desktop "Log in" button: focus falls back here after a deep-linked modal closes. */
  loginButtonRef: React.RefObject<HTMLButtonElement>
}

/** Floating glass navbar: logo, section anchors, theme, Log in / Create account, mobile menu. */
/** Memoised: props are a stable callback and a ref. */
export const LandingNav = React.memo(function LandingNav({ onOpenAuth, loginButtonRef }: LandingNavProps) {
  const [menuOpen, setMenuOpen] = React.useState(false)
  /** What to do once the menu has closed (and Radix has finished restoring focus). */
  const pending = React.useRef<{ section: string } | { auth: AuthMode } | null>(null)
  const menuButtonRef = React.useRef<HTMLButtonElement>(null)

  const closeMenuThen = (next: { section: string } | { auth: AuthMode }) => {
    pending.current = next
    setMenuOpen(false)
  }

  return (
    <header className="glass sticky top-0 z-40 w-full border-b border-border/70 pt-[env(safe-area-inset-top)] dark:border-glass-border/40">
      <nav
        aria-label="Main"
        className={cn(LANDING_CONTAINER, 'flex h-16 items-center gap-1 pl-[max(1.25rem,env(safe-area-inset-left))] pr-[max(1.25rem,env(safe-area-inset-right))] sm:gap-2')}
      >
        <a href="#top" className="-ml-1 flex items-center gap-2 rounded-lg p-1 pr-2" aria-label="JobPilot AI, back to top">
          <LogoMark />
          <Wordmark className="hidden min-[420px]:inline" />
        </a>

        <ul className="ml-10 hidden items-center gap-0.5 lg:flex">
          {LANDING_ANCHORS.map((anchor) => (
            <li key={anchor.id}>
              <a
                href={`#${anchor.id}`}
                className="rounded-lg px-3 py-2 text-sm font-medium text-foreground/90 transition-colors hover:bg-accent hover:text-accent-foreground"
              >
                {anchor.label}
              </a>
            </li>
          ))}
        </ul>

        <div className="ml-auto flex items-center gap-1 sm:gap-1.5">
          {/* 44 px tap targets on touch layouts; the shared toggle is 36 px by default. */}
          <span className="contents [&_button]:size-11 lg:[&_button]:size-9">
            <ThemeToggle />
          </span>
          <Button ref={loginButtonRef} variant="ghost" className="hidden h-11 sm:inline-flex lg:h-9" onClick={() => onOpenAuth('login')} {...authIntent}>
            Log in
          </Button>
          <Button size="sm" className="h-11 px-3.5 sm:px-4 lg:h-9" onClick={() => onOpenAuth('register')} {...authIntent}>
            Create account
          </Button>

          <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
            <SheetTrigger asChild>
              <Button ref={menuButtonRef} variant="ghost" size="icon" className="size-11 lg:hidden" aria-label="Open menu" data-landing-menu="">
                <Menu />
              </Button>
            </SheetTrigger>
            <SheetContent
              side="right"
              className="flex w-[min(20rem,85vw)] flex-col gap-0 p-0"
              onCloseAutoFocus={(event) => {
                const next = pending.current
                pending.current = null
                if (!next) return
                event.preventDefault()
                if ('section' in next) {
                  // Going to a section: focus moves there instead of back to the menu button.
                  window.setTimeout(() => goToSection(next.section), 0)
                } else {
                  // Opening the sign-in modal: it returns focus to the menu button when it closes.
                  menuButtonRef.current?.focus()
                  onOpenAuth(next.auth)
                }
              }}
            >
              <SheetHeader className="pb-2">
                <SheetTitle className="font-display text-lg">Menu</SheetTitle>
                <SheetDescription className="sr-only">Jump to a section, sign in or create an account.</SheetDescription>
              </SheetHeader>
              <ul className="space-y-1 px-3">
                {LANDING_ANCHORS.map((anchor) => (
                  <li key={anchor.id}>
                    <a
                      href={`#${anchor.id}`}
                      onClick={(event) => {
                        event.preventDefault()
                        closeMenuThen({ section: anchor.id })
                      }}
                      className="flex h-11 items-center rounded-lg px-3 text-[0.9375rem] font-medium transition-colors hover:bg-accent"
                    >
                      {anchor.label}
                    </a>
                  </li>
                ))}
              </ul>
              <div className="mt-auto grid gap-2 border-t border-border p-4">
                <Button
                  variant="outline"
                  size="lg"
                  onClick={() => closeMenuThen({ auth: 'login' })}
                >
                  Log in
                </Button>
                <Button
                  size="lg"
                  onClick={() => closeMenuThen({ auth: 'register' })}
                >
                  Create account
                </Button>
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </nav>
    </header>
  )
})
