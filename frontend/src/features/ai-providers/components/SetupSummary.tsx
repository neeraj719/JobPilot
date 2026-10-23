import { AlertTriangle, CreditCard, Lock, ShieldCheck } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Card, CardContent } from '@/components/ui/card'
import type { AiSettingsRead, ProvidersResponse } from '@/features/ai-providers/types'

/** The effective setup in one line, and what choosing a hosted provider means. */
export function SetupSummary({ settings, catalog }: { settings: AiSettingsRead; catalog: ProvidersResponse }) {
  const status = settings.status
  const keyLinks = catalog.providers.filter((p) => p.key_url)
  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <span
              className={
                status.hosted
                  ? 'flex size-10 shrink-0 items-center justify-center rounded-full bg-info/10 text-info'
                  : 'flex size-10 shrink-0 items-center justify-center rounded-full bg-success/10 text-success'
              }
            >
              {status.hosted ? <CreditCard className="size-5" aria-hidden /> : <ShieldCheck className="size-5" aria-hidden />}
            </span>
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Your AI setup</p>
              <p className="text-base font-semibold" data-testid="ai-setup-summary">{settings.summary}</p>
              <p className="text-xs text-muted-foreground">
                {status.source === 'server_default' ? 'Using the server default — nothing to configure.' : 'Your own choice.'}{' '}
                Tasks with their own model are listed below.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {!status.configured ? (
        <Alert variant="warning">
          <AlertTriangle aria-hidden />
          <AlertTitle>Your default model cannot be used</AlertTitle>
          <AlertDescription className="text-xs">
            {status.problem ?? 'Check the provider below.'} Until then AI features answer with the built-in rules.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-3 md:grid-cols-2">
        <div className="flex gap-3 rounded-lg border p-3">
          <Lock className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
          <p className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">Privacy.</span> The local Ollama model and the built-in rules keep
            everything on this machine. A hosted provider receives the text of your resume and of the job descriptions you
            analyse. Keys are encrypted on the server, never shown again, and never sent to your browser.
          </p>
        </div>
        <div className="flex gap-3 rounded-lg border p-3">
          <CreditCard className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
          <p className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">Billing.</span> {catalog.billing_note}{' '}
            {keyLinks.map((p, index) => (
              <span key={p.id}>
                <a className="text-primary hover:underline" href={p.key_url ?? '#'} target="_blank" rel="noreferrer noopener">
                  {p.name} keys
                </a>
                {index < keyLinks.length - 1 ? ' · ' : ''}
              </span>
            ))}
          </p>
        </div>
      </div>
    </div>
  )
}
