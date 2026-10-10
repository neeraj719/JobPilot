import { Bot, CircleCheck, Info, Link2, Link2Off, ShieldQuestion } from 'lucide-react'
import * as React from 'react'

import { ErrorState } from '@/components/common/ErrorState'
import { LoadingState } from '@/components/common/LoadingState'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { SimpleTooltip } from '@/components/ui/tooltip'
import { toast } from '@/components/ui/toaster'
import { errorMessage } from '@/lib/api'
import { formatDate } from '@/lib/utils'
import { useConnectAccount, useDisconnectAccount, useIntegrations } from '@/features/settings/api'
import type { AdapterInfo, ConnectedAccountRead, JobSourceType } from '@/types/api'

function AdapterRow({
  adapter,
  account,
  busy,
  onConnect,
  onDisconnect,
}: {
  adapter: AdapterInfo
  account: ConnectedAccountRead | undefined
  busy: boolean
  onConnect: (source: JobSourceType, identifier: string) => void
  onDisconnect: (account: ConnectedAccountRead) => void
}) {
  const [showForm, setShowForm] = React.useState(false)
  const [identifier, setIdentifier] = React.useState('')

  return (
    <li className="space-y-3 rounded-lg border border-border p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">{adapter.display_name}</span>
            {adapter.is_mock ? (
              <SimpleTooltip
                side="top"
                label="Simulated adapter: it returns realistic demo jobs instead of touching the real site."
              >
                <Badge variant="muted" className="gap-1">
                  <Bot aria-hidden />
                  Mock
                </Badge>
              </SimpleTooltip>
            ) : null}
            {adapter.supports_auto_apply ? (
              <Badge variant="outline" className="gap-1">
                <CircleCheck aria-hidden />
                Supports auto-apply
              </Badge>
            ) : null}
            {adapter.requires_account ? <Badge variant="outline">Requires an account</Badge> : null}
          </div>

          {adapter.terms_note ? (
            <SimpleTooltip side="bottom" label={adapter.terms_note}>
              <p className="line-clamp-2 max-w-2xl cursor-help text-xs text-muted-foreground">
                <ShieldQuestion className="mr-1 inline size-3" aria-hidden />
                {adapter.terms_note}
              </p>
            </SimpleTooltip>
          ) : null}

          {account ? (
            <p className="text-xs text-muted-foreground">
              Connected{account.account_identifier ? ` as ${account.account_identifier}` : ''}
              {account.connected_at ? ` on ${formatDate(account.connected_at)}` : ''}
              {account.last_error ? ` · last error: ${account.last_error}` : ''}
            </p>
          ) : null}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {account ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onDisconnect(account)}
              disabled={busy}
            >
              <Link2Off aria-hidden />
              Disconnect
            </Button>
          ) : (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setShowForm((open) => !open)}
              disabled={busy}
              aria-expanded={showForm}
            >
              <Link2 aria-hidden />
              Connect
            </Button>
          )}
        </div>
      </div>

      {showForm && !account ? (
        <form
          className="flex flex-col gap-2 rounded-md bg-muted/40 p-3 sm:flex-row sm:items-end"
          onSubmit={(event) => {
            event.preventDefault()
            onConnect(adapter.source, identifier.trim())
            setShowForm(false)
            setIdentifier('')
          }}
        >
          <div className="flex-1 space-y-1.5">
            <Label htmlFor={`identifier-${adapter.source}`} className="text-xs font-normal">
              Account identifier (optional)
            </Label>
            <Input
              id={`identifier-${adapter.source}`}
              value={identifier}
              onChange={(event) => setIdentifier(event.target.value)}
              placeholder="you@example.com"
              className="h-8"
            />
          </div>
          <Button type="submit" size="sm" loading={busy}>
            Save connection
          </Button>
        </form>
      ) : null}
    </li>
  )
}

export function ConnectedAccountsCard() {
  const integrationsQuery = useIntegrations()
  const connect = useConnectAccount()
  const disconnect = useDisconnectAccount()
  const [busySource, setBusySource] = React.useState<JobSourceType | null>(null)

  const adapters = integrationsQuery.data?.adapters ?? []
  const accounts = integrationsQuery.data?.accounts ?? []
  const accountBySource = React.useMemo(() => {
    const map = new Map<JobSourceType, ConnectedAccountRead>()
    for (const account of accounts) map.set(account.source, account)
    return map
  }, [accounts])

  const handleConnect = async (source: JobSourceType, identifier: string) => {
    setBusySource(source)
    try {
      await connect.mutateAsync({ source, account_identifier: identifier || null })
      toast.success('Account connected', { description: 'Credentials, when provided, are encrypted at rest.' })
    } catch (error) {
      toast.error('Could not connect the account', { description: errorMessage(error) })
    } finally {
      setBusySource(null)
    }
  }

  const handleDisconnect = async (account: ConnectedAccountRead) => {
    setBusySource(account.source)
    try {
      await disconnect.mutateAsync(account.id)
      toast.success('Account disconnected')
    } catch (error) {
      toast.error('Could not disconnect the account', { description: errorMessage(error) })
    } finally {
      setBusySource(null)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Connected accounts</CardTitle>
        <CardDescription>
          Job platforms JobPilot can search and, where supported, apply through on your behalf.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Alert variant="info">
          <Info aria-hidden />
          <AlertDescription>
            Adapters marked <strong>Mock</strong> return realistic demo listings instead of contacting the real site.
            That is deliberate: the real integrations need a partner API or the candidate&apos;s own consented session,
            and JobPilot never scrapes around a site&apos;s bot protection.
          </AlertDescription>
        </Alert>

        {integrationsQuery.isLoading ? (
          <LoadingState variant="list" rows={4} />
        ) : integrationsQuery.error ? (
          <ErrorState
            error={integrationsQuery.error}
            title="Could not load integrations"
            onRetry={() => void integrationsQuery.refetch()}
            size="sm"
          />
        ) : (
          <ul className="space-y-3">
            {adapters.map((adapter) => (
              <AdapterRow
                key={adapter.source}
                adapter={adapter}
                account={accountBySource.get(adapter.source)}
                busy={busySource === adapter.source}
                onConnect={(source, identifier) => void handleConnect(source, identifier)}
                onDisconnect={(account) => void handleDisconnect(account)}
              />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
