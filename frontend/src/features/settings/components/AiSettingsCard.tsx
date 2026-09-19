import { Bot, Chrome, Sparkles } from 'lucide-react'

import { ErrorState } from '@/components/common/ErrorState'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useAiStatus, useBrowserStatus } from '@/features/settings/api'

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border py-2 last:border-0">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="text-sm font-medium">{value}</dd>
    </div>
  )
}

/** Read-only view of the server's AI provider and browser capability. */
export function AiSettingsCard() {
  const aiStatus = useAiStatus()
  const browserStatus = useBrowserStatus()

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="size-4" aria-hidden />
            AI provider
          </CardTitle>
          <CardDescription>Configured on the server, not per account.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {aiStatus.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-5 w-full" />
              <Skeleton className="h-5 w-full" />
              <Skeleton className="h-5 w-2/3" />
            </div>
          ) : aiStatus.error ? (
            <ErrorState error={aiStatus.error} size="sm" onRetry={() => void aiStatus.refetch()} />
          ) : (
            <dl>
              <Row label="Provider" value={aiStatus.data?.provider ?? '—'} />
              <Row label="Model" value={aiStatus.data?.model ?? '—'} />
              <Row
                label="Credentials"
                value={
                  aiStatus.data?.configured ? (
                    <Badge variant="success">Configured</Badge>
                  ) : (
                    <Badge variant="warning">Missing</Badge>
                  )
                }
              />
            </dl>
          )}

          <p className="rounded-md bg-muted/50 p-3 text-xs text-muted-foreground">
            <Bot className="mr-1 inline size-3.5" aria-hidden />
            The <strong>mock</strong> provider is deterministic and needs no API key — the whole app works without one.
            To use a real model, set <code>LLM_PROVIDER</code> together with <code>OPENAI_API_KEY</code> or{' '}
            <code>ANTHROPIC_API_KEY</code> in the backend environment and restart the API.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Chrome className="size-4" aria-hidden />
            Browser automation
          </CardTitle>
          <CardDescription>Whether Playwright Chromium can launch on this deployment.</CardDescription>
        </CardHeader>
        <CardContent>
          {browserStatus.isLoading ? (
            <Skeleton className="h-5 w-full" />
          ) : browserStatus.error ? (
            <ErrorState error={browserStatus.error} size="sm" onRetry={() => void browserStatus.refetch()} />
          ) : (
            <dl>
              <Row
                label="Chromium"
                value={
                  browserStatus.data?.available ? (
                    <Badge variant="success">Available</Badge>
                  ) : (
                    <Badge variant="warning">Unavailable</Badge>
                  )
                }
              />
              <Row label="Mode" value={browserStatus.data?.headless ? 'Headless' : 'Headed'} />
            </dl>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
