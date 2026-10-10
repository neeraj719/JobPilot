import { Laptop, LogOut } from 'lucide-react'
import * as React from 'react'

import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { LoadingState } from '@/components/common/LoadingState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { toast } from '@/components/ui/toaster'
import { errorMessage, isApiError, isReauthRequired } from '@/lib/api'
import { formatDateTime, formatRelative } from '@/lib/utils'
import {
  useAuthSessions,
  useRememberThisDevice,
  useRevokeAuthSession,
  useRevokeOtherSessions,
} from '@/features/settings/api'
import { useAuthStore } from '@/stores/auth'
import type { SessionRead } from '@/types/api'

/** A sensitive action, run first without and then (if asked) with the password. */
type ReauthAction = (reauth: { password?: string }) => Promise<void>

/**
 * Runs sensitive actions and, when the API answers `401 reauth_required` (the access
 * token is older than 10 minutes), asks for the current password and retries once with
 * it in `X-Reauth-Password`. The password lives in this dialog's state only while it is
 * open and is cleared as soon as it closes.
 */
function useReauthGate() {
  const [pending, setPending] = React.useState<ReauthAction | null>(null)

  const run = React.useCallback(async (action: ReauthAction, failureTitle: string) => {
    try {
      await action({})
    } catch (error) {
      if (isReauthRequired(error)) {
        setPending(() => action)
        return
      }
      toast.error(failureTitle, { description: errorMessage(error) })
    }
  }, [])

  return { run, pending, close: () => setPending(null) }
}

function ReauthDialog({ action, onClose }: { action: ReauthAction | null; onClose: () => void }) {
  const [password, setPassword] = React.useState('')
  const [error, setError] = React.useState<string | null>(null)
  const [busy, setBusy] = React.useState(false)

  const close = React.useCallback(() => {
    setPassword('')
    setError(null)
    onClose()
  }, [onClose])

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!action || !password) return
    setBusy(true)
    setError(null)
    try {
      await action({ password })
      close()
    } catch (err) {
      setPassword('')
      if (isReauthRequired(err)) setError('That password is not correct.')
      else if (isApiError(err) && err.status === 429) setError('Too many attempts. Wait a few minutes and try again.')
      else setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={action !== null} onOpenChange={(open) => (!open && !busy ? close() : undefined)}>
      <DialogContent className="max-w-sm">
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Confirm it is you</DialogTitle>
            <DialogDescription>
              You signed in a while ago. Enter your password to change your sessions.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="reauth-password" className={error ? 'text-destructive' : undefined}>
              Current password
            </Label>
            <Input
              id="reauth-password"
              type="password"
              autoComplete="current-password"
              autoFocus
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              aria-invalid={error ? true : undefined}
            />
            {error ? <p className="text-xs font-medium text-destructive">{error}</p> : null}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={close} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" loading={busy} disabled={!password}>
              Confirm
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function SessionRow({
  session,
  busy,
  onSignOut,
}: {
  session: SessionRead
  busy: boolean
  onSignOut: (session: SessionRead) => void
}) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 p-3">
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">{session.device_label}</span>
          {session.is_current ? <Badge variant="success">This device</Badge> : null}
          {session.remembered ? <Badge variant="secondary">Remembered</Badge> : null}
        </div>
        <p className="text-xs text-muted-foreground" title={session.user_agent ?? undefined}>
          {/* A session's row is replaced on every refresh, so this is its latest activity. */}
          Signed in or last active {formatRelative(session.created_at)} · signs out automatically{' '}
          {formatDateTime(session.expires_at)}
        </p>
      </div>
      <Button type="button" variant="outline" size="sm" loading={busy} onClick={() => onSignOut(session)}>
        Sign out
      </Button>
    </li>
  )
}

/**
 * Settings → Security → Sessions and devices: every browser signed in to this account,
 * a "Stay signed in" switch for this one, and sign-out per device or for all others.
 * No credentials are shown or kept: a session is just a refresh token the server holds
 * hashed.
 */
export function DeviceSessionsCard() {
  const sessions = useAuthSessions()
  const revokeOne = useRevokeAuthSession()
  const revokeOthers = useRevokeOtherSessions()
  const rememberThisDevice = useRememberThisDevice()
  const logout = useAuthStore((state) => state.logout)
  const setSessionRemembered = useAuthStore((state) => state.setSessionRemembered)
  const { run, pending, close } = useReauthGate()
  const [busyId, setBusyId] = React.useState<string | null>(null)

  const list = sessions.data ?? []
  const current = list.find((session) => session.is_current)
  const others = list.filter((session) => !session.is_current)

  async function signOut(session: SessionRead) {
    if (session.is_current) {
      // This browser: a normal sign-out (revokes the cookie and clears local state).
      await logout()
      toast.success('Signed out of this device')
      return
    }
    setBusyId(session.id)
    try {
      await run(async (reauth) => {
        await revokeOne.mutateAsync({ id: session.id, ...reauth })
        toast.success(`Signed out ${session.device_label}`, {
          description: 'It needs the password again within half an hour at most.',
        })
      }, 'Could not sign out that device')
    } finally {
      setBusyId(null)
    }
  }

  async function signOutOthers() {
    await run(async (reauth) => {
      const result = await revokeOthers.mutateAsync(reauth)
      toast.success(
        result.revoked === 1 ? 'Signed out of 1 other device' : `Signed out of ${result.revoked} other devices`,
      )
    }, 'Could not sign out the other devices')
  }

  async function setRemember(remember: boolean) {
    await run(async (reauth) => {
      const session = await rememberThisDevice.mutateAsync({ remember, ...reauth })
      setSessionRemembered(session.remembered)
      toast.success(remember ? 'This device stays signed in for 14 days' : 'This device signs out when the browser closes')
    }, 'Could not change this setting')
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Laptop className="size-4" aria-hidden />
          Sessions and devices
        </CardTitle>
        <CardDescription>
          Browsers signed in to your account. JobPilot never stores your password; to skip typing it, let your
          browser&apos;s password manager save it.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {current ? (
          <div className="flex items-start justify-between gap-4 rounded-lg border border-border p-3">
            <div className="space-y-0.5">
              <Label htmlFor="stay-signed-in" className="text-sm font-medium">
                Stay signed in on this device
              </Label>
              <p className="text-xs text-muted-foreground">
                Keeps you signed in for 14 days. Only use on a device you own.
              </p>
            </div>
            <Switch
              id="stay-signed-in"
              checked={current.remembered}
              disabled={rememberThisDevice.isPending}
              onCheckedChange={(value) => void setRemember(value)}
            />
          </div>
        ) : null}

        {sessions.isLoading ? (
          <LoadingState variant="list" rows={2} />
        ) : sessions.error ? (
          <ErrorState error={sessions.error} size="sm" onRetry={() => void sessions.refetch()} />
        ) : list.length === 0 ? (
          <EmptyState
            size="sm"
            icon={Laptop}
            title="No active sessions"
            description="Sessions appear here when you sign in."
          />
        ) : (
          <ul className="divide-y divide-border rounded-lg border border-border">
            {[...(current ? [current] : []), ...others].map((session) => (
              <SessionRow key={session.id} session={session} busy={busyId === session.id} onSignOut={signOut} />
            ))}
          </ul>
        )}
      </CardContent>
      <CardFooter className="justify-end border-t bg-muted/30 py-3">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={others.length === 0}
          loading={revokeOthers.isPending}
          onClick={() => void signOutOthers()}
        >
          <LogOut aria-hidden />
          Sign out of all other devices
        </Button>
      </CardFooter>

      <ReauthDialog action={pending} onClose={close} />
    </Card>
  )
}
