import { AlertTriangle, Info, Route, Save } from 'lucide-react'
import * as React from 'react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { SimpleTooltip } from '@/components/ui/tooltip'
import { toast } from '@/components/ui/toaster'
import { errorMessage, isApiError } from '@/lib/api'
import { useUpdateAiSettings } from '@/features/ai-providers/api'
import { ModelSelect } from '@/features/ai-providers/components/ModelSelect'
import { PROVIDER_SHORT, limitsSchema, providerUsable } from '@/features/ai-providers/schema'
import type {
  AiSettingsRead,
  AiSettingsUpdate,
  ProviderId,
  ProviderRead,
  WorkflowId,
  WorkflowTarget,
} from '@/features/ai-providers/types'

const USE_DEFAULT = '__default'

const WORKFLOW_HELP: Record<WorkflowId, string> = {
  generation: 'Writing new resume sections, summaries and tailored versions.',
  analysis: 'Scoring a resume against a job description (ATS estimate).',
  rewriting: 'Rewriting single bullets and polishing wording.',
  jd_analysis: 'Pulling requirements and keywords out of a job description.',
  review: 'The final quality check of a tailored resume.',
  general: 'Resume parsing, application answers, cover letters and email sorting.',
}

type Target = WorkflowTarget | null

interface Draft {
  defaultTarget: Target
  workflows: Partial<Record<WorkflowId, Target>>
  fallbackEnabled: boolean
  fallback: Target
  daily: string
  budget: string
  ack: boolean
}

function toDraft(settings: AiSettingsRead): Draft {
  return {
    defaultTarget: settings.default_provider ? { provider: settings.default_provider, model: settings.default_model ?? '' } : null,
    workflows: { ...settings.workflow_models },
    fallbackEnabled: settings.fallback_enabled,
    fallback: settings.fallback_provider ? { provider: settings.fallback_provider, model: settings.fallback_model ?? '' } : null,
    daily: settings.daily_call_limit != null ? String(settings.daily_call_limit) : '',
    budget: settings.monthly_budget_usd != null ? String(settings.monthly_budget_usd) : '',
    ack: settings.data_residency_ack,
  }
}

function sameDraft(a: Draft, b: Draft): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

interface TargetPickerProps {
  id: string
  label: string
  value: Target
  onChange: (value: Target) => void
  providers: ProviderRead[]
  defaultLabel?: string
  /** Shown next to the provider select while "use default" is selected. */
  inheritText?: string
  allowDefault?: boolean
}

function TargetPicker({ id, label, value, onChange, providers, defaultLabel, inheritText, allowDefault = true }: TargetPickerProps) {
  const usable = providers.filter(providerUsable)
  const selected = value?.provider ?? USE_DEFAULT
  return (
    <div className="grid gap-2 sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)]">
      <Select
        value={selected}
        onValueChange={(next) => {
          if (next === USE_DEFAULT) return onChange(null)
          const provider = providers.find((p) => p.id === next)
          onChange({ provider: next as ProviderId, model: provider?.default_model ?? '' })
        }}
      >
        <SelectTrigger id={`${id}-provider`} aria-label={`${label}: provider`}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {allowDefault ? <SelectItem value={USE_DEFAULT}>{defaultLabel ?? 'Use default'}</SelectItem> : null}
          {usable.map((p) => (
            <SelectItem key={p.id} value={p.id}>
              {PROVIDER_SHORT[p.id]}
            </SelectItem>
          ))}
          {value && !usable.some((p) => p.id === value.provider) ? (
            <SelectItem value={value.provider}>{PROVIDER_SHORT[value.provider]} (not set up)</SelectItem>
          ) : null}
        </SelectContent>
      </Select>
      {value ? (
        <ModelSelect
          id={`${id}-model`}
          provider={value.provider}
          value={value.model || null}
          onChange={(model) => onChange({ ...value, model })}
          aria-label={`${label}: model`}
        />
      ) : (
        <p className="self-center truncate text-sm text-muted-foreground">{inheritText ?? ''}</p>
      )}
    </div>
  )
}

function fieldOf(error: unknown): string | null {
  if (!isApiError(error)) return null
  const details = error.details as { field?: string } | undefined
  return details?.field ?? null
}

export function RoutingCard({ settings, providers }: { settings: AiSettingsRead; providers: ProviderRead[] }) {
  const initial = React.useMemo(() => toDraft(settings), [settings])
  const [draft, setDraft] = React.useState<Draft>(initial)
  const [error, setError] = React.useState<{ message: string; field: string | null } | null>(null)
  const [limitErrors, setLimitErrors] = React.useState<{ daily?: string; budget?: string }>({})
  const update = useUpdateAiSettings()

  React.useEffect(() => setDraft(initial), [initial])

  const dirty = !sameDraft(draft, initial)
  const byId = React.useMemo(() => Object.fromEntries(providers.map((p) => [p.id, p])), [providers]) as Record<ProviderId, ProviderRead>
  const server = settings.server_default
  const defaultName = draft.defaultTarget
    ? `${PROVIDER_SHORT[draft.defaultTarget.provider]} · ${draft.defaultTarget.model || 'default model'}`
    : `${PROVIDER_SHORT[server.provider]} · ${server.model}`
  const chosen: Target[] = [draft.defaultTarget, ...Object.values(draft.workflows), draft.fallbackEnabled ? draft.fallback : null]
  const hostedChosen = chosen.some((t) => t && (byId[t.provider]?.hosted || t.provider === 'openai_compatible'))

  function setWorkflow(workflow: WorkflowId, target: Target) {
    setDraft((d) => {
      const workflows = { ...d.workflows }
      if (target) workflows[workflow] = target
      else delete workflows[workflow]
      return { ...d, workflows }
    })
  }

  async function onSave() {
    setError(null)
    const limits = limitsSchema.safeParse({ daily_call_limit: draft.daily.trim(), monthly_budget_usd: draft.budget.trim() })
    if (!limits.success) {
      const issues = limits.error.flatten().fieldErrors
      setLimitErrors({ daily: issues.daily_call_limit?.[0], budget: issues.monthly_budget_usd?.[0] })
      return
    }
    setLimitErrors({})
    const workflow_models: AiSettingsUpdate['workflow_models'] = {}
    for (const [key, target] of Object.entries(draft.workflows)) {
      if (target) workflow_models[key as WorkflowId] = target
    }
    const payload: AiSettingsUpdate = {
      default_provider: draft.defaultTarget?.provider ?? null,
      default_model: draft.defaultTarget?.model || null,
      workflow_models,
      fallback_enabled: draft.fallbackEnabled,
      fallback_provider: draft.fallback?.provider ?? null,
      fallback_model: draft.fallback?.model || null,
      daily_call_limit: limits.data.daily_call_limit,
      monthly_budget_usd: limits.data.monthly_budget_usd,
      data_residency_ack: draft.ack,
    }
    try {
      await update.mutateAsync(payload)
      toast.success('AI model settings saved', { description: 'New AI calls use these models right away.' })
    } catch (err) {
      setError({ message: errorMessage(err), field: fieldOf(err) })
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Route className="size-4" aria-hidden /> Model for each task
        </CardTitle>
        <CardDescription>
          Pick a default model, then override it for the tasks where a different model fits better — for example a
          cheaper model for bullet rewriting and a stronger one for the final review.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <section aria-labelledby="routing-default" className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h3 id="routing-default" className="text-sm font-semibold">Default model</h3>
            <SimpleTooltip label="Used by every task that has no model of its own." side="top">
              <Info className="size-3.5 text-muted-foreground" aria-label="About the default model" />
            </SimpleTooltip>
          </div>
          <TargetPicker
            id="routing-default"
            label="Default model"
            value={draft.defaultTarget}
            onChange={(value) => setDraft((d) => ({ ...d, defaultTarget: value }))}
            providers={providers}
            defaultLabel={`Server default (${PROVIDER_SHORT[server.provider]})`}
            inheritText={`${PROVIDER_SHORT[server.provider]} · ${server.model} — set by the server`}
          />
        </section>

        <section aria-labelledby="routing-workflows" className="space-y-3">
          <h3 id="routing-workflows" className="text-sm font-semibold">Per task</h3>
          <ul className="divide-y rounded-lg border">
            {(Object.keys(WORKFLOW_HELP) as WorkflowId[]).map((workflow) => {
              const effective = settings.effective[workflow]
              const label = WORKFLOW_LABELS[workflow]
              return (
                <li key={workflow} className="grid gap-2 p-3 lg:grid-cols-[minmax(0,14rem)_minmax(0,1fr)] lg:items-center">
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{label}</p>
                    <p className="text-xs text-muted-foreground">{WORKFLOW_HELP[workflow]}</p>
                    {effective ? (
                      <p className="mt-1 flex flex-wrap items-center gap-1 text-xs">
                        <span className="text-muted-foreground">Now:</span>
                        <span className="font-medium">{PROVIDER_SHORT[effective.provider]} · {effective.model}</span>
                        {effective.usable ? null : (
                          <Badge variant="destructive" className="ml-1">
                            {effective.problem ?? 'not usable'}
                          </Badge>
                        )}
                      </p>
                    ) : null}
                  </div>
                  <TargetPicker
                    id={`routing-${workflow}`}
                    label={label}
                    value={draft.workflows[workflow] ?? null}
                    onChange={(value) => setWorkflow(workflow, value)}
                    providers={providers}
                    defaultLabel="Use default"
                    inheritText={`Uses the default: ${defaultName}`}
                  />
                </li>
              )
            })}
          </ul>
        </section>

        <section aria-labelledby="routing-fallback" className="space-y-3 rounded-lg border p-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 id="routing-fallback" className="text-sm font-semibold">Fallback</h3>
              <p className="text-xs text-muted-foreground">
                Only used when the chosen model fails (timeout, quota, outage) — never silently: the switch is recorded in
                your usage, and nothing goes to a provider you did not pick here.
              </p>
            </div>
            <Switch
              checked={draft.fallbackEnabled}
              onCheckedChange={(checked) => setDraft((d) => ({ ...d, fallbackEnabled: checked }))}
              aria-label="Use a fallback model"
            />
          </div>
          {draft.fallbackEnabled ? (
            <TargetPicker
              id="routing-fallback-target"
              label="Fallback"
              value={draft.fallback}
              onChange={(value) => setDraft((d) => ({ ...d, fallback: value }))}
              providers={providers}
              allowDefault={false}
            />
          ) : null}
        </section>

        <section aria-labelledby="routing-limits" className="grid gap-4 sm:grid-cols-2">
          <h3 id="routing-limits" className="sr-only">Usage limits</h3>
          <div className="space-y-1.5">
            <Label htmlFor="limit-daily" className={limitErrors.daily ? 'text-destructive' : undefined}>Daily AI calls</Label>
            <Input
              id="limit-daily"
              inputMode="numeric"
              placeholder="No limit"
              value={draft.daily}
              onChange={(event) => setDraft((d) => ({ ...d, daily: event.target.value }))}
              aria-invalid={limitErrors.daily ? true : undefined}
            />
            <p className={limitErrors.daily ? 'text-xs font-medium text-destructive' : 'text-xs text-muted-foreground'}>
              {limitErrors.daily ?? 'Counts every model call. When reached, AI features fall back to the built-in rules until tomorrow.'}
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="limit-budget" className={limitErrors.budget ? 'text-destructive' : undefined}>Monthly budget (USD, estimated)</Label>
            <Input
              id="limit-budget"
              inputMode="decimal"
              placeholder="No budget"
              value={draft.budget}
              onChange={(event) => setDraft((d) => ({ ...d, budget: event.target.value }))}
              aria-invalid={limitErrors.budget ? true : undefined}
            />
            <p className={limitErrors.budget ? 'text-xs font-medium text-destructive' : 'text-xs text-muted-foreground'}>
              {limitErrors.budget ?? 'Hosted calls stop once the estimated spend this month reaches it. Local models are free and not affected.'}
            </p>
          </div>
        </section>

        {hostedChosen || draft.ack ? (
          <div className="flex items-start gap-3 rounded-lg border border-warning/40 bg-warning/5 p-3">
            <Checkbox
              id="data-ack"
              checked={draft.ack}
              onCheckedChange={(checked) => setDraft((d) => ({ ...d, ack: checked === true }))}
              aria-describedby="data-ack-help"
            />
            <div className="space-y-1">
              <Label htmlFor="data-ack" className="text-sm font-medium">
                I understand hosted providers receive my resume and job text
              </Label>
              <p id="data-ack-help" className="text-xs text-muted-foreground">
                OpenAI, Google and Anthropic process the text under their own API terms. The local Ollama model keeps
                everything on this machine.
              </p>
            </div>
          </div>
        ) : null}

        {error ? (
          <Alert variant="destructive" aria-live="assertive">
            <AlertTriangle aria-hidden />
            <AlertTitle>Settings not saved</AlertTitle>
            <AlertDescription className="text-xs">{error.message}</AlertDescription>
          </Alert>
        ) : null}
      </CardContent>
      <CardFooter className="flex flex-wrap items-center justify-end gap-2 border-t pt-4">
        {dirty ? <span className="mr-auto text-xs text-muted-foreground">Unsaved changes</span> : null}
        <Button type="button" variant="ghost" disabled={!dirty || update.isPending} onClick={() => { setDraft(initial); setError(null) }}>
          Reset
        </Button>
        <Button type="button" onClick={() => void onSave()} disabled={!dirty} loading={update.isPending}>
          <Save aria-hidden /> Save settings
        </Button>
      </CardFooter>
    </Card>
  )
}

const WORKFLOW_LABELS: Record<WorkflowId, string> = {
  generation: 'Resume generation',
  analysis: 'ATS analysis',
  rewriting: 'Bullet rewriting',
  jd_analysis: 'Job-description analysis',
  review: 'Final review',
  general: 'Everything else',
}
