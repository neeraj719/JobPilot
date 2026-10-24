import { useLocation } from 'react-router-dom'

import { isLauncherPath } from '@/modules/registry'

/**
 * Where a successful sign-in / sign-up goes, shared by the full pages and the landing modals:
 * a deep link the user was sent away from wins; otherwise the launcher, flagged as the
 * post-sign-in entry so it can forward to the last module when the user chose that.
 */
export function usePostAuthRedirect() {
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from
  const redirectTo = from && !isLauncherPath(from) ? from : '/home'
  const redirectState = redirectTo === '/home' ? { entry: true } : undefined
  return { from, redirectTo, redirectState }
}
