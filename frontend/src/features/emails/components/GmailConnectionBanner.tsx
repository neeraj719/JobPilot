import { Mail, Plug, RefreshCw, ShieldCheck, TriangleAlert } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { formatApiDateTime, formatApiRelative } from '@/features/automation/datetime'
import type { GmailStatus } from '@/types/api'

export interface GmailConnectionBannerProps {
  gmail: GmailStatus | undefined
  loading?: boolean
  connecting?: boolean
  syncing?: boolean
  onConnect: () => void
  onSync: () => void
}

/**
 * Gmail state at the top of the inbox: not configured on the server, configured but
 * disconnected, or connected (with read-only scope, last sync and a sync button).
 */
export function GmailConnectionBanner({
  gmail,
  loading = false,
  connecting = false,
  syncing = false,
  onConnect,
  onSync,
}: GmailConnectionBannerProps) {
  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center gap-4 p-4">
          <Skeleton className="size-10 shrink-0 rounded-lg" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-48" />
            <Skeleton className="h-3 w-72" />
          </div>
          <Skeleton className="h-9 w-28" />
        </CardContent>
      </Card>
    )
  }

  if (!gmail) return null

  const connected = gmail.status === 'CONNECTED'
  const errored = gmail.status === 'ERROR'

  // The server has no Google OAuth credentials — connecting is impossible, so explain it.
  if (!gmail.configured) {
    return (
      <Card className="border-info/30 bg-info/5">
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-info/10 text-info">
            <Mail className="size-5" aria-hidden />
          </span>
          <div className="min-w-0 flex-1 space-y-1">
            <p className="text-sm font-semibold">Gmail is not configured on this server</p>
            <p className="text-sm text-muted-foreground">
              Set <code className="rounded bg-muted px-1 py-0.5 text-xs">GOOGLE_CLIENT_ID</code> and{' '}
              <code className="rounded bg-muted px-1 py-0.5 text-xs">GOOGLE_CLIENT_SECRET</code> in the backend
              environment and restart it to enable the read-only inbox sync. Until then, use{' '}
              <strong>Simulate email</strong> to see how replies flow through the pipeline.
            </p>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!connected) {
    return (
      <Card className={cn(errored && 'border-destructive/30 bg-destructive/5')}>
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
          <span
            className={cn(
              'flex size-10 shrink-0 items-center justify-center rounded-lg',
              errored ? 'bg-destructive/10 text-destructive' : 'bg-muted text-muted-foreground',
            )}
          >
            {errored ? <TriangleAlert className="size-5" aria-hidden /> : <Plug className="size-5" aria-hidden />}
          </span>
          <div className="min-w-0 flex-1 space-y-1">
            <p className="text-sm font-semibold">
              {errored ? 'Gmail needs reconnecting' : 'Connect Gmail to track replies automatically'}
            </p>
            <p className="text-sm text-muted-foreground">
              {gmail.last_error
                ? gmail.last_error
                : 'JobPilot asks for read-only access. It never sends, deletes or modifies anything in your mailbox.'}
            </p>
          </div>
          <Button onClick={onConnect} loading={connecting} className="shrink-0">
            <Plug />
            {errored ? 'Reconnect Gmail' : 'Connect Gmail'}
          </Button>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="border-success/30 bg-success/5">
      <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-success/10 text-success">
          <ShieldCheck className="size-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1 space-y-0.5">
          <p className="truncate text-sm font-semibold">{gmail.email_address ?? 'Gmail connected'}</p>
          <p className="text-sm text-muted-foreground">
            <span className="font-medium text-success">Read-only</span>
            {' · '}
            {gmail.last_synced_at
              ? `Last synced ${formatApiRelative(gmail.last_synced_at)} (${formatApiDateTime(gmail.last_synced_at)})`
              : 'Never synced'}
          </p>
        </div>
        <Button variant="outline" onClick={onSync} loading={syncing} className="shrink-0">
          <RefreshCw />
          Sync now
        </Button>
      </CardContent>
    </Card>
  )
}
