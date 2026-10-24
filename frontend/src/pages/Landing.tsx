import * as React from 'react'

import { loadAuthDialog, useAuthModal } from '@/features/auth/authModal'
import { LandingHero } from '@/features/landing/LandingHero'
import { LandingNav } from '@/features/landing/LandingNav'
import { BuiltForStrip, FaqSection, FeatureBento, FinalCta, HowItWorks, LandingFooter, SafetySection } from '@/features/landing/LandingSections'
import { useDocumentMeta } from '@/hooks/useDocumentMeta'

/** The modal + forms chunk; prefetched on hover / focus of any Log in / Create account button. */
const AuthDialog = React.lazy(() => loadAuthDialog().then((m) => ({ default: m.AuthDialog })))

const META = {
  title: 'JobPilot AI — build, score and tailor your resume',
  description:
    'Build your resume, score it against a real job description and tailor it with AI suggestions you approve. Nothing is added that you did not do.',
  image: '/landing/og.png',
  rawTitle: true,
}

/**
 * `/` for anonymous visitors (signed-in users get the launcher). A lazy chunk with no app
 * shell. Sign-in and sign-up open in a modal driven by `?auth=login|register`.
 */
export default function LandingPage() {
  useDocumentMeta(META)
  const { mode, open, setMode, returnFocusRef } = useAuthModal()
  // Mount the (lazy) dialog the first time it is needed and keep it mounted for its close animation.
  const [dialogMounted, setDialogMounted] = React.useState(mode !== null)
  React.useEffect(() => {
    if (mode !== null) setDialogMounted(true)
  }, [mode])
  const loginButtonRef = React.useRef<HTMLButtonElement>(null)

  const fallbackFocus = React.useCallback(() => {
    const login = loginButtonRef.current
    if (login && login.getClientRects().length > 0) return login
    return document.querySelector<HTMLElement>('[data-landing-menu]')
  }, [])

  return (
    // --nav-h: the navbar's height (h-16), used by the hero's first-view fit.
    <div className="min-h-svh bg-background text-foreground" style={{ '--nav-h': '4rem' } as React.CSSProperties}>
      <a
        href="#main"
        className="sr-only z-50 rounded-lg bg-card px-4 py-2 text-sm font-medium shadow-lg focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
      >
        Skip to content
      </a>
      <LandingNav onOpenAuth={open} loginButtonRef={loginButtonRef} />
      <main id="main" tabIndex={-1} className="outline-none">
        <LandingHero onOpenAuth={open} />
        <BuiltForStrip />
        <FeatureBento />
        <HowItWorks />
        <SafetySection />
        <FaqSection />
        <FinalCta onOpenAuth={open} />
      </main>
      <LandingFooter onOpenAuth={open} />
      {dialogMounted || mode !== null ? (
        <React.Suspense fallback={null}>
          <AuthDialog mode={mode} onModeChange={setMode} returnFocusRef={returnFocusRef} fallbackFocus={fallbackFocus} />
        </React.Suspense>
      ) : null}
    </div>
  )
}
