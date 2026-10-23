import * as React from 'react'

import { Button } from '@/components/ui/button'
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
import { toast } from '@/components/ui/toaster'
import { errorMessage, isApiError, isReauthRequired } from '@/lib/api'

/** A sensitive action, run first without and then (if asked) with the password. */
export type ReauthAction = (reauth: { password?: string }) => Promise<void>

/**
 * Saving or removing an API key is a sensitive action: when the access token is older
 * than ten minutes the API answers `401 reauth_required`, and this asks for the password
 * once and retries with it. The password only lives in the dialog's state while it is open.
 */
export function useReauthGate() {
  const [pending, setPending] = React.useState<ReauthAction | null>(null)

  const run = React.useCallback(async (action: ReauthAction, failureTitle: string): Promise<boolean> => {
    try {
      await action({})
      return true
    } catch (error) {
      if (isReauthRequired(error)) {
        setPending(() => action)
        return false
      }
      toast.error(failureTitle, { description: errorMessage(error) })
      return false
    }
  }, [])

  return { run, pending, close: () => setPending(null) }
}

export function ReauthDialog({ action, onClose }: { action: ReauthAction | null; onClose: () => void }) {
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
            <DialogDescription>You signed in a while ago. Enter your password to change an API key.</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="ai-reauth-password" className={error ? 'text-destructive' : undefined}>
              Current password
            </Label>
            <Input
              id="ai-reauth-password"
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
