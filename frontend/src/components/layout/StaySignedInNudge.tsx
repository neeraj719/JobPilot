import { KeyRound, X } from 'lucide-react'
import * as React from 'react'
import { Link } from 'react-router-dom'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { useAuthStore } from '@/stores/auth'

/**
 * The owner's "ask after the first login whether to save it", done without storing any
 * credential: after signing in on a device *without* "Stay signed in", suggest turning it
 * on. Shown until dismissed; the dismissal (a plain flag, nothing secret) is remembered
 * per user in this browser's localStorage.
 */
const DISMISSED_PREFIX = 'jobpilot.staySignedInNudgeDismissed.'

function isDismissed(userId: string): boolean {
  try {
    return window.localStorage.getItem(`${DISMISSED_PREFIX}${userId}`) === '1'
  } catch {
    return false
  }
}

function markDismissed(userId: string): void {
  try {
    window.localStorage.setItem(`${DISMISSED_PREFIX}${userId}`, '1')
  } catch {
    // Storage blocked: the banner just comes back next time.
  }
}

export function StaySignedInNudge() {
  const userId = useAuthStore((state) => state.user?.id ?? null)
  const sessionRemembered = useAuthStore((state) => state.sessionRemembered)
  const [dismissed, setDismissed] = React.useState(() => (userId ? isDismissed(userId) : true))

  React.useEffect(() => {
    setDismissed(userId ? isDismissed(userId) : true)
  }, [userId])

  if (!userId || dismissed || sessionRemembered !== false) return null

  function dismiss() {
    if (userId) markDismissed(userId)
    setDismissed(true)
  }

  return (
    <div className="px-4 pt-4 sm:px-6">
      {/* Compact banner (py-2.5): it sits above every page, so it must not push heroes below the fold. */}
      <Alert variant="info" role="status" className="py-2.5 pr-12 [&>svg]:top-3">
        {/* Before the icon: the Alert pads every sibling *after* its svg. */}
        <button
          type="button"
          onClick={dismiss}
          className="absolute right-3 top-1/2 -translate-y-1/2 rounded-sm p-1 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="Dismiss"
        >
          <X className="size-4" />
        </button>
        <KeyRound aria-hidden />
        <AlertDescription className="text-foreground">
          Want to skip the login next time? Turn on Stay signed in from{' '}
          <Link to="/settings?section=security" className="font-medium text-primary underline-offset-4 hover:underline">
            Settings
          </Link>{' '}
          or at your next login.
        </AlertDescription>
      </Alert>
    </div>
  )
}
