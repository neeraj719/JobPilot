import * as React from 'react'

import type { AuthMode } from '@/features/auth/authModal'
import { AuthBrand } from '@/components/layout/AuthBrand'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { LoginForm } from '@/features/auth/components/LoginForm'
import { RegisterForm } from '@/features/auth/components/RegisterForm'
import { cn } from '@/lib/utils'
import { loadHome, prefetchWhenIdle } from '@/modules/prefetch'

export type { AuthMode } from '@/features/auth/authModal'

const COPY: Record<AuthMode, { title: string; description: string }> = {
  login: { title: 'Welcome back', description: 'Sign in to pick up where you left off.' },
  register: { title: 'Create your account', description: 'Start from the resume you already have, or from scratch.' },
}

export interface AuthDialogProps {
  mode: AuthMode | null
  onModeChange: (mode: AuthMode | null) => void
  /** The element to focus when the dialog closes (the trigger), if any. */
  returnFocusRef?: React.MutableRefObject<HTMLElement | null>
  /** Fallback focus target after a deep-linked modal closes (e.g. the navbar's Log in). */
  fallbackFocus?: () => HTMLElement | null
}

/**
 * Sign-in / sign-up in a Radix Dialog (focus trap, Esc, scroll lock). A centred card from
 * 640 px up, a bottom sheet below. The forms are the exact ones `/login` and `/register` use,
 * so validation, toasts and post-sign-in routing are identical; nothing navigates until the
 * request succeeds.
 */
/** Focusable only when attached and rendered (not inside a `display: none` branch). */
function canFocus(element: HTMLElement | null | undefined): element is HTMLElement {
  return Boolean(element && element.isConnected && element.getClientRects().length > 0)
}

export function AuthDialog({ mode, onModeChange, returnFocusRef, fallbackFocus }: AuthDialogProps) {
  // Keep the last mode while the close animation runs, so the content does not blank out.
  const [shownMode, setShownMode] = React.useState<AuthMode>(mode ?? 'login')
  React.useEffect(() => {
    if (mode) setShownMode(mode)
  }, [mode])
  // The modal leads to the launcher: fetch its chunk while the visitor types.
  React.useEffect(() => (mode ? prefetchWhenIdle(loadHome) : undefined), [mode])
  const copy = COPY[shownMode]
  const otherMode: AuthMode = shownMode === 'login' ? 'register' : 'login'

  return (
    <Dialog open={mode !== null} onOpenChange={(open) => (!open ? onModeChange(null) : undefined)}>
      <DialogContent
        aria-describedby="auth-dialog-description"
        onCloseAutoFocus={(event) => {
          const trigger = returnFocusRef?.current
          const target = canFocus(trigger) ? trigger : fallbackFocus?.()
          if (canFocus(target)) {
            event.preventDefault()
            target.focus()
          }
          if (returnFocusRef) returnFocusRef.current = null
        }}
        // Close button on the padding grid: 20 px from the visible top-right corner (19 px + the
        // 1 px border; the bottom sheet has no side border), 36 px hit area.
        closeClassName="right-5 top-[19px] flex size-9 items-center justify-center rounded-lg p-0 sm:right-[19px]"
        className={cn(
          'max-h-[92svh] gap-6 overflow-y-auto overscroll-contain p-6 sm:max-w-lg sm:rounded-3xl sm:p-8 md:max-w-xl',
          // Short viewports: tighter rhythm so the register form fits without scrolling.
          '[@media(min-height:801px)_and_(max-height:900px)]:gap-4 sm:[@media(min-height:801px)_and_(max-height:900px)]:p-7 [@media(max-height:800px)]:gap-3 sm:[@media(max-height:800px)]:p-6',
          // Bottom sheet under 640 px: pinned to the bottom edge, full width, top corners rounded,
          // slides up instead of zooming.
          'max-sm:bottom-0 max-sm:left-0 max-sm:top-auto max-sm:max-w-none max-sm:translate-x-0 max-sm:translate-y-0',
          'max-sm:rounded-b-none max-sm:rounded-t-3xl max-sm:border-x-0 max-sm:border-b-0 max-sm:pb-[max(1.5rem,env(safe-area-inset-bottom))]',
          'max-sm:data-[state=closed]:zoom-out-100 max-sm:data-[state=open]:zoom-in-100',
          'max-sm:data-[state=closed]:slide-out-to-bottom max-sm:data-[state=open]:slide-in-from-bottom',
        )}
      >
        <div aria-hidden className="mx-auto -mt-2 h-1.5 w-10 rounded-full bg-border sm:hidden" />
        <DialogHeader className="space-y-2 pr-10 [@media(max-height:800px)]:space-y-1">
          <AuthBrand className="justify-start lg:justify-start" />
          <DialogTitle className="pt-1 [@media(max-height:800px)]:pt-0 font-display text-[1.75rem] font-heading leading-tight tracking-[-0.03em] sm:text-3xl">{copy.title}</DialogTitle>
          <DialogDescription id="auth-dialog-description" className="text-[0.9375rem] leading-6">
            {copy.description}
          </DialogDescription>
        </DialogHeader>

        {/* key: a fresh form (and fresh errors) when switching between the two. */}
        {shownMode === 'login' ? <LoginForm key="login" autoFocus /> : <RegisterForm key="register" autoFocus wide />}

        <p className="text-center text-[0.9375rem] text-muted-foreground">
          {shownMode === 'login' ? 'New here? ' : 'Already have an account? '}
          <button
            type="button"
            onClick={() => onModeChange(otherMode)}
            className="rounded-sm font-medium text-primary underline-offset-4 hover:underline"
          >
            {shownMode === 'login' ? 'Create an account' : 'Log in instead'}
          </button>
        </p>
      </DialogContent>
    </Dialog>
  )
}
