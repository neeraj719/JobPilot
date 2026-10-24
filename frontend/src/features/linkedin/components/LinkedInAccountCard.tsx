import { Linkedin, ListChecks, RefreshCw, Unplug } from 'lucide-react'
import * as React from 'react'
import { Link } from 'react-router-dom'

import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { ErrorState } from '@/components/common/ErrorState'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { toast } from '@/components/ui/toaster'
import { errorMessage, isApiError } from '@/lib/api'
import { formatDateTime, formatRelative } from '@/lib/utils'

import { useDisconnectLinkedIn, useLinkedIn, useLinkedInDiff, useSyncLinkedIn, useUpdateLinkedIn } from '../api'
import { SCOPE_LABELS } from '../copy'
import { LinkedInCardSkeleton, LinkedInIdentity, LinkedInMark, LinkedInSourceBadge, SWITCH_DARK_FIX } from './LinkedInParts'
import { useStartLinkedInConnect } from './LinkedInConnectPanel'
import { LinkedInReviewDialog } from './LinkedInReviewDialog'

/** Settings › Connected accounts: the LinkedIn connection at a glance. */
export function LinkedInAccountCard() {
  const status = useLinkedIn()
  const sync = useSyncLinkedIn()
  const update = useUpdateLinkedIn()
  const disconnect = useDisconnectLinkedIn()
  const { start, isPending: starting } = useStartLinkedInConnect()
  const [reviewOpen, setReviewOpen] = React.useState(false)
  const [confirmOpen, setConfirmOpen] = React.useState(false)
  const diff = useLinkedInDiff(reviewOpen)
  const data = status.data

  const handleSync = async () => {
    try {
      const result = await sync.mutateAsync()
      toast.success('LinkedIn synced', {
        description: result.diff.changes ? `${result.diff.changes} changes to review.` : 'Your profile already matches LinkedIn.',
      })
    } catch (error) {
      toast.error('LinkedIn sync failed', { description: errorMessage(error) })
    }
  }

  // LinkedIn belongs to Resume Studio: without that module the card has nothing to offer.
  if (isApiError(status.error) && status.error.code === 'module_disabled') return null

  return (
    <Card>
      <CardHeader className="flex-row items-start gap-3 space-y-0">
        <LinkedInMark />
        <div className="min-w-0">
          <CardTitle className="text-base">LinkedIn</CardTitle>
          <CardDescription>Official LinkedIn sign-in. Fills your profile only with the changes you review.</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {status.isLoading ? (
          <LinkedInCardSkeleton />
        ) : status.error || !data ? (
          <ErrorState error={status.error} title="Could not load your LinkedIn connection" onRetry={() => void status.refetch()} size="sm" />
        ) : data.status !== 'connected' ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border p-3">
            <p className="text-sm text-muted-foreground">
              {data.status === 'expired' || data.status === 'revoked'
                ? data.last_error ?? 'Reconnect LinkedIn to keep syncing.'
                : 'Not connected. LinkedIn shares your name, email and photo; your export adds the full history.'}
            </p>
            {data.configured ? (
              <Button type="button" size="sm" onClick={() => void start()} loading={starting}>
                <Linkedin aria-hidden /> {data.status === 'expired' || data.status === 'revoked' ? 'Reconnect' : 'Connect LinkedIn'}
              </Button>
            ) : (
              <Badge variant="muted">Not configured on this server</Badge>
            )}
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <LinkedInIdentity status={data} />
              <LinkedInSourceBadge status={data} />
            </div>

            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <div className="min-w-0">
                <dt className="text-xs font-medium text-muted-foreground">Access granted</dt>
                <dd className="mt-1 flex flex-wrap gap-1.5">
                  {data.scopes.map((scope) => (
                    <Badge key={scope} variant="outline" title={scope}>
                      {SCOPE_LABELS[scope] ?? scope}
                    </Badge>
                  ))}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-muted-foreground">Last sync</dt>
                <dd className="mt-1 tabular-nums">
                  {data.last_synced_at ? `${formatDateTime(data.last_synced_at)} (${formatRelative(data.last_synced_at)})` : 'Not synced yet'}
                </dd>
              </div>
            </dl>

            {data.pending_changes > 0 ? (
              <Alert variant="info">
                <AlertDescription className="flex flex-wrap items-center justify-between gap-2">
                  <span>
                    {data.pending_changes} {data.pending_changes === 1 ? 'change' : 'changes'} from LinkedIn waiting for your review.
                  </span>
                  <Button type="button" size="sm" variant="soft" onClick={() => setReviewOpen(true)}>
                    <ListChecks aria-hidden /> Review latest changes
                  </Button>
                </AlertDescription>
              </Alert>
            ) : null}

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
              <label className="flex items-center gap-2 text-sm">
                <Switch
                  className={SWITCH_DARK_FIX}
                  checked={data.auto_sync}
                  disabled={update.isPending}
                  onCheckedChange={(next) =>
                    update.mutate({ auto_sync: next }, { onError: (err) => toast.error('Could not change auto-sync', { description: errorMessage(err) }) })
                  }
                />
                Auto-check every {data.auto_sync_hours} h (notifies, never overwrites)
              </label>
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="outline" size="sm" onClick={() => void handleSync()} loading={sync.isPending}>
                  <RefreshCw aria-hidden /> Sync now
                </Button>
                <Button type="button" variant="outline" size="sm" asChild>
                  <Link to="/resume/new?source=linkedin">Open in Create Resume</Link>
                </Button>
                <Button type="button" variant="ghost" size="sm" onClick={() => setConfirmOpen(true)}>
                  <Unplug aria-hidden /> Disconnect
                </Button>
              </div>
            </div>
          </>
        )}
      </CardContent>

      <LinkedInReviewDialog open={reviewOpen} onOpenChange={setReviewOpen} result={diff.data} loading={diff.isFetching && !diff.data} />
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Disconnect LinkedIn?"
        description="JobPilot revokes its access at LinkedIn and deletes the stored LinkedIn details. Your profile and resumes stay as they are."
        confirmLabel="Disconnect"
        variant="destructive"
        loading={disconnect.isPending}
        onConfirm={async () => {
          try {
            await disconnect.mutateAsync()
            toast.success('LinkedIn disconnected', { description: 'Access revoked and stored LinkedIn data deleted.' })
          } catch (err) {
            toast.error('Could not disconnect LinkedIn', { description: errorMessage(err) })
          }
        }}
      />
    </Card>
  )
}
