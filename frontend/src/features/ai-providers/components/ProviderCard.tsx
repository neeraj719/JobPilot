import { CheckCircle2, ExternalLink, KeyRound, PlugZap, RefreshCw, Trash2, XCircle } from 'lucide-react'
import * as React from 'react'

import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { SkeletonRegion } from '@/components/common/skeletons'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { SimpleTooltip } from '@/components/ui/tooltip'
import { toast } from '@/components/ui/toaster'
import { errorMessage } from '@/lib/api'
import { formatRelative } from '@/lib/utils'
import { useDeleteCredential, useProviderModels, useRefreshModels, useSaveCredential, useTestConnection } from '@/features/ai-providers/api'
import type { ReauthAction } from '@/features/ai-providers/components/ReauthGate'
import { apiKeySchema, baseUrlSchema, credentialPill, type StatusPill } from '@/features/ai-providers/schema'
import type { ConnectionTestResult, ProviderRead } from '@/features/ai-providers/types'

const KIND_LABEL: Record<ProviderRead['kind'], string> = {
  builtin: 'Built-in',
  local: 'Local · free',
  hosted: 'Hosted · your API key',
  self_hosted: 'Self-hosted',
}

const BASE_URL_PLACEHOLDER: Partial<Record<ProviderRead['id'], string>> = {
  ollama: 'http://localhost:11434',
  openai_compatible: 'http://localhost:1234/v1',
}

function Pill({ pill }: { pill: StatusPill }) {
  return (
    <Badge variant={pill.tone} className="whitespace-nowrap">
      {pill.label}
    </Badge>
  )
}

interface ProviderCardProps {
  provider: ProviderRead
  runSensitive: (action: ReauthAction, failureTitle: string) => Promise<boolean>
}

export function ProviderCard({ provider, runSensitive }: ProviderCardProps) {
  const credential = provider.credential
  const needsKeyField = provider.requires_key || provider.id === 'openai_compatible'
  const [editingKey, setEditingKey] = React.useState(!credential?.has_key)
  const [apiKey, setApiKey] = React.useState('')
  const [baseUrl, setBaseUrl] = React.useState(credential?.base_url ?? '')
  const [fieldError, setFieldError] = React.useState<{ api_key?: string; base_url?: string }>({})
  const [result, setResult] = React.useState<ConnectionTestResult | null>(null)
  const [confirmRemove, setConfirmRemove] = React.useState(false)

  const save = useSaveCredential()
  const remove = useDeleteCredential()
  const test = useTestConnection()
  const refresh = useRefreshModels()
  const isOllama = provider.id === 'ollama'
  const models = useProviderModels(provider.id, { enabled: provider.id !== 'openai_compatible' && provider.id !== 'mock' })

  React.useEffect(() => {
    setBaseUrl(credential?.base_url ?? '')
    if (!credential?.has_key) setEditingKey(true)
  }, [credential?.base_url, credential?.has_key])

  // Ollama: the cheap local probe (GET /api/tags through the API) is the status.
  let pill = credentialPill(provider, credential)
  // While that probe runs, the status pill is a skeleton of the same size (no "Checking…" text).
  const probing = isOllama && !credential && models.isLoading
  if (isOllama && !credential) {
    if (models.data?.live) pill = { label: `Running · ${models.data.models.length} model${models.data.models.length === 1 ? '' : 's'}`, tone: 'success' }
    else if (models.data?.error) pill = { label: 'Not running', tone: 'destructive' }
  }

  const baseUrlDirty = provider.supports_base_url && baseUrl.trim() !== (credential?.base_url ?? '')
  const keyDirty = needsKeyField && apiKey.trim() !== ''
  const canSave = keyDirty || baseUrlDirty

  async function runTest() {
    setResult(null)
    try {
      const outcome = await test.mutateAsync({ provider: provider.id })
      setResult(outcome)
      if (outcome.ok) toast.success(`${provider.name} is connected`, { description: outcome.latency_ms != null ? `Answered in ${outcome.latency_ms} ms.` : undefined })
    } catch (error) {
      toast.error('Connection test failed', { description: errorMessage(error) })
    }
  }

  async function onSave(event: React.FormEvent) {
    event.preventDefault()
    const errors: { api_key?: string; base_url?: string } = {}
    const payload: { api_key?: string; base_url?: string } = {}
    if (keyDirty) {
      const parsed = apiKeySchema.safeParse(apiKey)
      if (!parsed.success) errors.api_key = parsed.error.issues[0]?.message
      else payload.api_key = parsed.data
    } else if (provider.requires_key && !credential?.has_key) {
      errors.api_key = `Paste your ${provider.name} API key.`
    }
    if (provider.supports_base_url) {
      const parsed = baseUrlSchema.safeParse(baseUrl)
      if (!parsed.success) errors.base_url = parsed.error.issues[0]?.message
      else payload.base_url = parsed.data
    }
    setFieldError(errors)
    if (errors.api_key || errors.base_url) return

    const updating = Boolean(credential)
    // The follow-up lives inside the action so it also runs after a password confirmation.
    await runSensitive(async ({ password }) => {
      await save.mutateAsync({ provider: provider.id, payload, password })
      setApiKey('')
      setEditingKey(false)
      toast.success(updating ? `${provider.name} credential updated` : `${provider.name} saved`, {
        description: 'Stored encrypted on the server. Testing the connection…',
      })
      void runTest()
    }, `Could not save the ${provider.name} settings`)
  }

  async function onRemove() {
    setConfirmRemove(false)
    await runSensitive(async ({ password }) => {
      await remove.mutateAsync({ provider: provider.id, password })
      setResult(null)
      setApiKey('')
      toast.success(`${provider.name} credential removed`, { description: 'The encrypted key was deleted from the server.' })
    }, `Could not remove the ${provider.name} credential`)
  }

  async function onRefresh() {
    try {
      const data = await refresh.mutateAsync(provider.id)
      if (data.error) toast.error('Could not list models', { description: data.error })
      else toast.success(`${data.models.length} models listed`, { description: data.live ? 'Fresh from the provider.' : 'From JobPilot’s registry.' })
    } catch (error) {
      toast.error('Could not list models', { description: errorMessage(error) })
    }
  }

  const titleId = `provider-${provider.id}-title`
  const showResult = result ?? null
  const lastError = !showResult && credential?.status === 'ERROR' ? credential.last_error : null

  return (
    <Card aria-labelledby={titleId} className="flex h-full flex-col">
      <CardHeader className="space-y-2 pb-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <CardTitle id={titleId} className="text-base">
              {provider.name}
            </CardTitle>
            <p className="mt-0.5 text-xs text-muted-foreground">{KIND_LABEL[provider.kind]}</p>
          </div>
          {probing ? (
            <SkeletonRegion label="Checking the local Ollama server">
              <Skeleton className="h-[22px] w-28 rounded-full" />
            </SkeletonRegion>
          ) : (
            <Pill pill={pill} />
          )}
        </div>
        <CardDescription>{provider.description}</CardDescription>
      </CardHeader>

      <CardContent className="flex-1 space-y-4">
        <p className="rounded-md bg-muted/50 p-2.5 text-xs text-muted-foreground">{provider.privacy_note}</p>

        {provider.id === 'mock' ? null : (
          <form className="space-y-3" onSubmit={onSave} noValidate>
            {needsKeyField ? (
              <div className="space-y-1.5">
                <Label htmlFor={`${provider.id}-key`} className={fieldError.api_key ? 'text-destructive' : undefined}>
                  API key{provider.requires_key ? '' : ' (optional)'}
                </Label>
                {credential?.has_key && !editingKey ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <code className="rounded bg-muted px-2 py-1 text-sm tracking-wider" aria-label="Saved key, masked">
                      {credential.masked_key}
                    </code>
                    <Button type="button" variant="outline" size="sm" onClick={() => setEditingKey(true)}>
                      <KeyRound aria-hidden /> Rotate
                    </Button>
                    <Button type="button" variant="ghost" size="sm" className="text-destructive" onClick={() => setConfirmRemove(true)}>
                      <Trash2 aria-hidden /> Remove
                    </Button>
                  </div>
                ) : (
                  <Input
                    id={`${provider.id}-key`}
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    placeholder={credential?.has_key ? 'Paste the new key' : 'Paste your API key'}
                    value={apiKey}
                    onChange={(event) => setApiKey(event.target.value)}
                    aria-invalid={fieldError.api_key ? true : undefined}
                    aria-describedby={`${provider.id}-key-help`}
                  />
                )}
                <p id={`${provider.id}-key-help`} className={fieldError.api_key ? 'text-xs font-medium text-destructive' : 'text-xs text-muted-foreground'}>
                  {fieldError.api_key ??
                    (credential?.has_key
                      ? `Saved ${formatRelative(credential.rotated_at ?? credential.updated_at)} · encrypted, never shown again.`
                      : 'Stored encrypted on the server and never shown again.')}
                </p>
              </div>
            ) : null}

            {provider.supports_base_url ? (
              <div className="space-y-1.5">
                <Label htmlFor={`${provider.id}-url`} className={fieldError.base_url ? 'text-destructive' : undefined}>
                  Server address
                </Label>
                <Input
                  id={`${provider.id}-url`}
                  inputMode="url"
                  placeholder={BASE_URL_PLACEHOLDER[provider.id]}
                  value={baseUrl}
                  onChange={(event) => setBaseUrl(event.target.value)}
                  aria-invalid={fieldError.base_url ? true : undefined}
                />
                <p className={fieldError.base_url ? 'text-xs font-medium text-destructive' : 'text-xs text-muted-foreground'}>
                  {fieldError.base_url ??
                    (isOllama
                      ? 'Only needed when Ollama runs somewhere other than this server’s default (localhost:11434).'
                      : 'http:// is only accepted for local or private-network servers; use https:// on the internet.')}
                </p>
              </div>
            ) : null}

            {canSave ? (
              <div className="flex flex-wrap gap-2">
                <Button type="submit" size="sm" loading={save.isPending}>
                  {credential ? 'Save changes' : 'Save'}
                </Button>
                {credential?.has_key && editingKey ? (
                  <Button type="button" size="sm" variant="ghost" onClick={() => { setEditingKey(false); setApiKey('') }}>
                    Cancel
                  </Button>
                ) : null}
              </div>
            ) : credential?.has_key && editingKey ? (
              <Button type="button" size="sm" variant="ghost" onClick={() => setEditingKey(false)}>
                Cancel
              </Button>
            ) : credential && !credential.has_key ? (
              <Button type="button" size="sm" variant="ghost" className="text-destructive" onClick={() => setConfirmRemove(true)}>
                <Trash2 aria-hidden /> Remove saved address
              </Button>
            ) : null}
          </form>
        )}

        {showResult ? (
          <Alert variant={showResult.ok ? 'success' : 'destructive'} aria-live="polite">
            {showResult.ok ? <CheckCircle2 aria-hidden /> : <XCircle aria-hidden />}
            <AlertTitle>{showResult.ok ? 'Connected' : 'Connection failed'}</AlertTitle>
            <AlertDescription className="text-xs">
              {showResult.ok
                ? `${showResult.model ?? 'Default model'} answered in ${showResult.latency_ms ?? '?'} ms.`
                : showResult.error ?? 'The provider did not answer.'}
            </AlertDescription>
          </Alert>
        ) : lastError ? (
          <Alert variant="destructive">
            <XCircle aria-hidden />
            <AlertTitle>Last test failed</AlertTitle>
            <AlertDescription className="text-xs">{lastError}</AlertDescription>
          </Alert>
        ) : isOllama && models.data?.error && !models.data.live ? (
          <Alert variant="warning">
            <XCircle aria-hidden />
            <AlertTitle>Local model server not reachable</AlertTitle>
            <AlertDescription className="text-xs">{models.data.error}</AlertDescription>
          </Alert>
        ) : null}
      </CardContent>

      <CardFooter className="flex flex-wrap items-center gap-2 border-t pt-4">
        <SimpleTooltip label={provider.hosted ? 'Makes one free model-list request with your key' : 'Checks the server and model'} side="top">
          <Button type="button" variant="outline" size="sm" onClick={() => void runTest()} disabled={!provider.allowed} loading={test.isPending}>
            {test.isPending ? null : <PlugZap aria-hidden />}
            Test connection
          </Button>
        </SimpleTooltip>
        {provider.supports_live_models ? (
          <Button type="button" variant="ghost" size="sm" onClick={() => void onRefresh()} disabled={!provider.allowed} loading={refresh.isPending}>
            {refresh.isPending ? null : <RefreshCw aria-hidden />} Refresh models
          </Button>
        ) : null}
        <div className="ml-auto flex gap-3 text-xs">
          {provider.key_url ? (
            <a className="inline-flex items-center gap-1 text-primary hover:underline" href={provider.key_url} target="_blank" rel="noreferrer noopener">
              Get an API key <ExternalLink className="size-3" aria-hidden />
            </a>
          ) : null}
          {provider.docs_url ? (
            <a className="inline-flex items-center gap-1 text-muted-foreground hover:underline" href={provider.docs_url} target="_blank" rel="noreferrer noopener">
              Docs <ExternalLink className="size-3" aria-hidden />
            </a>
          ) : null}
        </div>
      </CardFooter>

      <ConfirmDialog
        open={confirmRemove}
        onOpenChange={setConfirmRemove}
        title={credential?.has_key ? `Remove the ${provider.name} key?` : `Remove the saved ${provider.name} address?`}
        description="The encrypted key is deleted from the server. Workflows routed to this provider will stop working until you add a key again or pick another model."
        confirmLabel="Remove key"
        variant="destructive"
        loading={remove.isPending}
        onConfirm={onRemove}
      />
    </Card>
  )
}
