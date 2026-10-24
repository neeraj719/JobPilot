import * as React from 'react'
import { useSearchParams } from 'react-router-dom'

import { prefetchOnIntent } from '@/modules/prefetch'

export type AuthMode = 'login' | 'register'

const PARAM = 'auth'

function isAuthMode(value: string | null): value is AuthMode {
  return value === 'login' || value === 'register'
}

/**
 * The sign-in / sign-up modal and its forms (react-hook-form + zod) are a chunk of their own:
 * a passive landing visit never downloads or parses them. Hovering / focusing a "Log in" or
 * "Create account" button prefetches it (`authIntent`), a `?auth=` deep link loads it at once.
 */
export const loadAuthDialog = () => import('@/features/auth/components/AuthDialog')

/** Spread on every button that opens the modal: prefetches the dialog chunk on intent. */
export const authIntent = prefetchOnIntent(loadAuthDialog)

/**
 * The `?auth=login|register` URL state behind the landing page's sign-in modal: deep-linkable,
 * survives a refresh, and closing the modal removes the parameter. `open()` remembers the
 * element that opened it so focus can go back there (the triggers are plain buttons spread
 * over the page, not one Radix `DialogTrigger`). `open` / `setMode` keep one identity for the
 * page's lifetime, so the memoised landing sections do not re-render when the modal opens.
 */
export function useAuthModal() {
  const [params, setParams] = useSearchParams()
  const raw = params.get(PARAM)
  const mode: AuthMode | null = isAuthMode(raw) ? raw : null
  const returnFocusRef = React.useRef<HTMLElement | null>(null)
  // react-router's setter changes identity with the search params; read it through a ref.
  const setParamsRef = React.useRef(setParams)
  setParamsRef.current = setParams

  const setMode = React.useCallback((next: AuthMode | null) => {
    setParamsRef.current(
      (current) => {
        const copy = new URLSearchParams(current)
        if (next) copy.set(PARAM, next)
        else copy.delete(PARAM)
        return copy
      },
      { replace: true, preventScrollReset: true },
    )
  }, [])

  const open = React.useCallback(
    (next: AuthMode) => {
      if (document.activeElement instanceof HTMLElement && document.activeElement !== document.body) {
        returnFocusRef.current = document.activeElement
      }
      setMode(next)
    },
    [setMode],
  )

  return { mode, open, setMode, returnFocusRef }
}
