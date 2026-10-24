import { Mail, RefreshCw, ShieldCheck, Unplug } from 'lucide-react'

import { ErrorState } from '@/components/common/ErrorState'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { toast } from '@/components/ui/toaster'
import { errorMessage } from '@/lib/api'
import { formatDateTime, formatRelative } from '@/lib/utils'
import { useConnectGmail, useDisconnectGmail, useIntegrations, useSyncGmail } from '@/features/settings/api'
import { GmailStatusSkeleton } from '@/features/settings/components/SettingsSkeletons'

function StatusBadge({ status }: { status: string }) {
  if (status === 'CONNECTED') return <Badge variant="success">Connected</Badge>
  if (status === 'ERROR') return <Badge variant="destructive">Error</Badge>
  return <Badge variant="muted">Not connected</Badge>
}

export function EmailIntegrationCard() {
  const integrationsQuery = useIntegrations()
  const connectGmail = useConnectGmail()
  const syncGmail = useSyncGmail()
  const disconnectGmail = useDisconnectGmail()

  const gmail = integrationsQuery.data?.gmail

  const handleConnect = async () => {
    try {
      const { authorization_url } = await connectGmail.mutateAsync()
      window.location.href = authorization_url
    } catch (error) {
      toast.error('Could not start the Gmail connection', { description: errorMessage(error) })
    }
  }

  const handleSync = async () => {
    try {
      const result = await syncGmail.mutateAsync()
      toast.success('Gmail synced', {
        description: `${result.fetched} fetched · ${result.new} new · ${result.linked} linked to applications · ${result.status_updates} status updates`,
      })
    } catch (error) {
      toast.error('Gmail sync failed', { description: errorMessage(error) })
    }
  }

  const handleDisconnect = async () => {
    try {
      await disconnectGmail.mutateAsync()
      toast.success('Gmail disconnected', { description: 'Stored tokens were revoked and wiped.' })
    } catch (error) {
      toast.error('Could not disconnect Gmail', { description: errorMessage(error) })
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Email integration</CardTitle>
        <CardDescription>
          Reads recruiting mail so replies, interviews and rejections update your applications automatically.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {integrationsQuery.isLoading ? (
          <GmailStatusSkeleton />
        ) : integrationsQuery.error ? (
          <ErrorState
            error={integrationsQuery.error}
            title="Could not load the Gmail status"
            onRetry={() => void integrationsQuery.refetch()}
            size="sm"
          />
        ) : !gmail ? null : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border p-3">
              <div className="flex items-center gap-3">
                <span className="flex size-9 items-center justify-center rounded-full bg-muted">
                  <Mail className="size-4" aria-hidden />
                </span>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">Gmail</span>
                    <StatusBadge status={gmail.status} />
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {gmail.email_address ?? 'No account linked yet'}
                    {gmail.connected_at ? ` · connected ${formatDateTime(gmail.connected_at)}` : ''}
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {gmail.status === 'CONNECTED' ? (
                  <>
                    <Button type="button" variant="outline" size="sm" onClick={() => void handleSync()} loading={syncGmail.isPending}>
                      <RefreshCw aria-hidden />
                      Sync now
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => void handleDisconnect()}
                      loading={disconnectGmail.isPending}
                    >
                      <Unplug aria-hidden />
                      Disconnect
                    </Button>
                  </>
                ) : (
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => void handleConnect()}
                    loading={connectGmail.isPending}
                    disabled={!gmail.configured}
                  >
                    <Mail aria-hidden />
                    Connect Gmail
                  </Button>
                )}
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <ShieldCheck className="size-3.5 text-success" aria-hidden />
              <span>Read-only access</span>
              {gmail.scopes.length > 0 ? (
                <span className="truncate" title={gmail.scopes.join(', ')}>
                  · {gmail.scopes.length} {gmail.scopes.length === 1 ? 'scope' : 'scopes'} granted
                </span>
              ) : null}
              {gmail.last_synced_at ? <span>· last synced {formatRelative(gmail.last_synced_at)}</span> : null}
            </div>

            {gmail.last_error ? (
              <Alert variant="destructive">
                <AlertDescription>{gmail.last_error}</AlertDescription>
              </Alert>
            ) : null}

            {!gmail.configured ? (
              <Alert variant="warning">
                <AlertTitle>Gmail is not configured on this server</AlertTitle>
                <AlertDescription>
                  Set <code>GOOGLE_CLIENT_ID</code> and <code>GOOGLE_CLIENT_SECRET</code> in the backend environment
                  (plus a redirect URI pointing at <code>/api/v1/integrations/gmail/callback</code>), then restart the
                  API. Until then the app runs happily on simulated emails.
                </AlertDescription>
              </Alert>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  )
}
