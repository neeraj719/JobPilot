import { zodResolver } from '@hookform/resolvers/zod'
import { TriangleAlert } from 'lucide-react'
import * as React from 'react'
import { Controller, useForm } from 'react-hook-form'

import { ErrorState } from '@/components/common/ErrorState'
import { LoadingState } from '@/components/common/LoadingState'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Slider } from '@/components/ui/slider'
import { Switch } from '@/components/ui/switch'
import { toast } from '@/components/ui/toaster'
import { SimpleTooltip } from '@/components/ui/tooltip'
import { errorMessage } from '@/lib/api'
import { cn, formatDateTime } from '@/lib/utils'
import { Field, FieldGrid } from '@/features/profile/components/SectionCard'
import { useAutomationConfig, useIntegrations, useUpdateAutomationConfig } from '@/features/settings/api'
import { useSyncDefaults } from '@/features/profile/useSyncDefaults'
import {
  COMMON_TIMEZONES,
  automationDefaults,
  automationSchema,
  automationToPayload,
  defaultSourceMode,
  type AutomationValues,
} from '@/features/settings/schema'
import type { AdapterInfo, SourceApplyMode } from '@/types/api'

const FORM_ID = 'automation-settings-form'

const APPLY_MODE_OPTIONS: { value: SourceApplyMode; label: string }[] = [
  { value: 'AUTO_APPLY', label: 'Auto apply' },
  { value: 'DISCOVER_ONLY', label: 'Discover only' },
]

/** Two-option segmented control for one source's apply mode. */
function ApplyModeControl({
  id,
  value,
  onChange,
  disabled,
  label,
}: {
  id: string
  value: SourceApplyMode
  onChange: (next: SourceApplyMode) => void
  disabled: boolean
  label: string
}) {
  return (
    <div
      id={id}
      role="radiogroup"
      aria-label={`Apply mode for ${label}`}
      className={cn(
        'inline-flex rounded-md border border-border bg-muted/40 p-0.5 text-xs',
        disabled && 'cursor-not-allowed opacity-60',
      )}
    >
      {APPLY_MODE_OPTIONS.map((option) => {
        const selected = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={disabled}
            onClick={() => onChange(option.value)}
            className={cn(
              'rounded-[5px] px-2.5 py-1 font-medium transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              selected ? 'bg-card text-foreground shadow-sm dark:bg-surface-3' : 'text-muted-foreground hover:text-foreground',
              disabled && 'pointer-events-none',
            )}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

/** One row per source: name, what it can do, and the segmented apply-mode control. */
function SourceModeTable({
  adapters,
  value,
  onChange,
  status,
  onRetry,
}: {
  adapters: AdapterInfo[]
  value: Record<string, SourceApplyMode>
  onChange: (next: Record<string, SourceApplyMode>) => void
  status: 'loading' | 'error' | 'empty' | 'ready'
  onRetry: () => void
}) {
  if (status !== 'ready' || adapters.length === 0) {
    return (
      <AdapterNotice
        status={status === 'ready' ? 'empty' : status}
        emptyLabel="No adapters reported by the server."
        onRetry={onRetry}
      />
    )
  }
  return (
    <ul className="divide-y divide-border rounded-lg border border-border">
      {adapters.map((adapter) => {
        const supported = Boolean(adapter.supports_auto_apply)
        const mode: SourceApplyMode = supported ? (value[adapter.source] ?? defaultSourceMode(adapter)) : 'DISCOVER_ONLY'
        const control = (
          <ApplyModeControl
            id={`source-mode-${adapter.source}`}
            value={mode}
            disabled={!supported}
            label={adapter.display_name}
            onChange={(next) => onChange({ ...value, [adapter.source]: next })}
          />
        )
        return (
          <li key={adapter.source} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-3 py-2">
            <div className="min-w-0">
              <p className="text-sm">
                {adapter.display_name}
                {adapter.is_mock ? <span className="ml-1 text-xs text-muted-foreground">(mock)</span> : null}
              </p>
              <p className="text-xs text-muted-foreground">
                {!supported
                  ? 'Discovery only — this adapter cannot submit applications'
                  : adapter.uses_browser
                    ? 'Fills the real form in Chromium'
                    : 'Applies inside the platform'}
              </p>
            </div>
            {supported ? (
              control
            ) : (
              <SimpleTooltip
                side="left"
                label={`${adapter.display_name} does not support automated applications, so its jobs can only be discovered.`}
              >
                {/* A disabled button cannot receive pointer events; the wrapper carries the tooltip. */}
                <span tabIndex={0} className="inline-flex rounded-md">
                  {control}
                </span>
              </SimpleTooltip>
            )}
          </li>
        )
      })}
    </ul>
  )
}

function ToggleRow({
  id,
  label,
  description,
  checked,
  onChange,
}: {
  id: string
  label: string
  description: string
  checked: boolean
  onChange: (next: boolean) => void
}) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border border-border p-3">
      <div className="space-y-0.5">
        <Label htmlFor={id}>{label}</Label>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      <Switch id={id} checked={checked} onCheckedChange={onChange} />
    </div>
  )
}

/**
 * Message shown instead of a source list. Distinguishes "still loading" and "the adapter
 * list failed to load" from "this deployment genuinely has no such adapter" — claiming the
 * last one after a failed request would be a lie.
 */
function AdapterNotice({
  status,
  emptyLabel,
  onRetry,
}: {
  status: 'loading' | 'error' | 'empty'
  emptyLabel: string
  onRetry: () => void
}) {
  if (status === 'loading') return <p className="text-xs text-muted-foreground">Loading the adapter list…</p>
  if (status === 'error') {
    return (
      <p className="flex flex-wrap items-center gap-2 text-xs text-warning">
        The adapter list could not be loaded, so the sources are hidden.
        <Button type="button" variant="outline" size="sm" onClick={onRetry}>
          Retry
        </Button>
      </p>
    )
  }
  return <p className="text-xs text-muted-foreground">{emptyLabel}</p>
}

function SourceCheckboxes({
  idPrefix,
  adapters,
  value,
  onChange,
  emptyLabel,
  status,
  onRetry,
}: {
  idPrefix: string
  adapters: AdapterInfo[]
  value: string[]
  onChange: (next: string[]) => void
  emptyLabel: string
  status: 'loading' | 'error' | 'empty' | 'ready'
  onRetry: () => void
}) {
  if (status !== 'ready' || adapters.length === 0) {
    return (
      <AdapterNotice
        status={status === 'ready' ? 'empty' : status}
        emptyLabel={emptyLabel}
        onRetry={onRetry}
      />
    )
  }
  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
      {adapters.map((adapter) => {
        const id = `${idPrefix}-${adapter.source}`
        const checked = value.includes(adapter.source)
        return (
          <div key={adapter.source} className="flex items-center gap-2">
            <Checkbox
              id={id}
              checked={checked}
              onCheckedChange={(next) =>
                onChange(
                  next === true
                    ? [...value.filter((item) => item !== adapter.source), adapter.source]
                    : value.filter((item) => item !== adapter.source),
                )
              }
            />
            <Label htmlFor={id} className="font-normal">
              {adapter.display_name}
              {adapter.is_mock ? <span className="ml-1 text-xs text-muted-foreground">(mock)</span> : null}
            </Label>
          </div>
        )
      })}
    </div>
  )
}

export function AutomationSettingsForm() {
  const configQuery = useAutomationConfig()
  const integrationsQuery = useIntegrations()
  const updateConfig = useUpdateAutomationConfig()

  const adapters = React.useMemo(() => integrationsQuery.data?.adapters ?? [], [integrationsQuery.data])
  const autoApplyAdapters = React.useMemo(() => adapters.filter((a) => a.supports_auto_apply), [adapters])
  const adapterStatus: 'loading' | 'error' | 'empty' | 'ready' = integrationsQuery.isLoading
    ? 'loading'
    : integrationsQuery.isError
      ? 'error'
      : adapters.length === 0
        ? 'empty'
        : 'ready'
  const retryAdapters = () => void integrationsQuery.refetch()

  const defaults = React.useMemo(() => automationDefaults(configQuery.data), [configQuery.data])

  const form = useForm<AutomationValues>({
    resolver: zodResolver(automationSchema),
    defaultValues: defaults,
  })
  const { register, control, handleSubmit, reset, watch, setValue, formState } = form
  const errors = formState.errors

  useSyncDefaults(defaults, formState.isDirty, reset)

  const autoSubmitEnabled = watch('auto_submit_enabled')
  const perPlatform = watch('per_platform_limit')
  // `per_platform_limit` is a record, so RHF types its error as a record too — the
  // superRefine issue lands on the group itself.
  const perPlatformError = (errors.per_platform_limit as { message?: string } | undefined)?.message

  const onSubmit = handleSubmit(async (values) => {
    try {
      const updated = await updateConfig.mutateAsync(automationToPayload(values))
      reset(automationDefaults(updated))
      toast.success('Automation settings saved', { description: 'The next scheduled run uses these values.' })
    } catch (error) {
      toast.error('Could not save automation settings', { description: errorMessage(error) })
    }
  })

  if (configQuery.isLoading) return <LoadingState variant="cards" rows={2} />
  if (configQuery.error) {
    return (
      <ErrorState
        error={configQuery.error}
        title="Could not load automation settings"
        onRetry={() => void configQuery.refetch()}
      />
    )
  }

  const config = configQuery.data

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Application limits and schedule</CardTitle>
        <CardDescription>
          How often the pipeline runs, how many applications it may prepare, and how much of that it is allowed to
          submit without you.
          {config?.next_run_at ? (
            <>
              {' '}
              Next run: <span className="font-medium">{formatDateTime(config.next_run_at)}</span>.
            </>
          ) : null}
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-6">
        <form id={FORM_ID} onSubmit={onSubmit} className="space-y-6" noValidate>
          <Controller
            control={control}
            name="enabled"
            render={({ field }) => (
              <ToggleRow
                id="automation-enabled"
                label="Run the pipeline on a schedule"
                description="Discover, match, queue and prepare applications every day at the time below."
                checked={field.value}
                onChange={field.onChange}
              />
            )}
          />

          <FieldGrid>
            <Field
              label="Schedule time"
              htmlFor="schedule_time"
              error={errors.schedule_time?.message}
              hint="24-hour clock, e.g. 09:00"
            >
              <Input id="schedule_time" type="time" {...register('schedule_time')} />
            </Field>
            <Field label="Timezone" htmlFor="timezone" error={errors.timezone?.message}>
              <Controller
                control={control}
                name="timezone"
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger id="timezone">
                      <SelectValue placeholder="Select a timezone" />
                    </SelectTrigger>
                    <SelectContent>
                      {(COMMON_TIMEZONES as readonly string[]).includes(field.value) ? null : (
                        <SelectItem value={field.value}>{field.value}</SelectItem>
                      )}
                      {COMMON_TIMEZONES.map((zone) => (
                        <SelectItem key={zone} value={zone}>
                          {zone}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </Field>
          </FieldGrid>

          <FieldGrid cols={3}>
            <Field
              label="Daily application limit"
              htmlFor="daily_application_limit"
              error={errors.daily_application_limit?.message}
              hint="Hard stop for one day. The server caps this at 100."
            >
              <Input id="daily_application_limit" inputMode="numeric" {...register('daily_application_limit')} />
            </Field>
            <Field
              label="Delay between actions (s)"
              htmlFor="delay_between_actions_seconds"
              error={errors.delay_between_actions_seconds?.message}
              hint="Keeps the automation polite on every site."
            >
              <Input
                id="delay_between_actions_seconds"
                inputMode="decimal"
                {...register('delay_between_actions_seconds')}
              />
            </Field>
            <Field
              label="Retry limit"
              htmlFor="retry_limit"
              error={errors.retry_limit?.message}
              hint="Attempts per application before it is parked."
            >
              <Input id="retry_limit" inputMode="numeric" {...register('retry_limit')} />
            </Field>
          </FieldGrid>

          <section className="space-y-2">
            <h3 className="text-sm font-medium">Per-platform limits</h3>
            <p className="text-xs text-muted-foreground">
              Optional cap per source. Leave a field empty for “no separate limit”.
            </p>
            {adapterStatus === 'ready' ? null : (
              <AdapterNotice status={adapterStatus} emptyLabel="No adapters reported by the server." onRetry={retryAdapters} />
            )}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {adapters.map((adapter) => (
                <div key={adapter.source} className="space-y-1.5">
                  <Label htmlFor={`platform-limit-${adapter.source}`} className="text-xs font-normal">
                    {adapter.display_name}
                  </Label>
                  <Input
                    id={`platform-limit-${adapter.source}`}
                    inputMode="numeric"
                    value={perPlatform[adapter.source] ?? ''}
                    onChange={(event) =>
                      setValue(
                        'per_platform_limit',
                        { ...perPlatform, [adapter.source]: event.target.value },
                        { shouldDirty: true },
                      )
                    }
                    className="h-8"
                  />
                </div>
              ))}
            </div>
            {perPlatformError ? <p className="text-xs font-medium text-destructive">{perPlatformError}</p> : null}
          </section>

          <Separator />

          <Controller
            control={control}
            name="min_match_score"
            render={({ field }) => (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label htmlFor="automation_min_match_score">Minimum match score to queue</Label>
                  <span className="text-sm font-semibold tabular-nums">{field.value}</span>
                </div>
                <Slider
                  id="automation_min_match_score"
                  min={0}
                  max={100}
                  step={1}
                  value={[field.value]}
                  onValueChange={([next]) => field.onChange(next ?? 0)}
                  aria-label="Minimum match score to queue"
                />
              </div>
            )}
          />

          <Field
            label="Only jobs posted within (hours)"
            htmlFor="only_posted_within_hours"
            error={errors.only_posted_within_hours?.message}
            className="sm:max-w-xs"
            hint="24 = the last day, 168 = the last week."
          >
            <Input id="only_posted_within_hours" inputMode="numeric" {...register('only_posted_within_hours')} />
          </Field>

          <Controller
            control={control}
            name="prioritize_priority_companies"
            render={({ field }) => (
              <ToggleRow
                id="prioritize_priority_companies"
                label="Put priority companies first"
                description="Orders the queue by your P1/P2/P3 list. It never changes a match score."
                checked={field.value}
                onChange={field.onChange}
              />
            )}
          />

          <section className="space-y-2">
            <h3 className="text-sm font-medium">Sources to search</h3>
            <p className="text-xs text-muted-foreground">
              Leave everything unchecked to search every adapter that is available.
            </p>
            <Controller
              control={control}
              name="enabled_sources"
              render={({ field }) => (
                <SourceCheckboxes
                  idPrefix="enabled-source"
                  adapters={adapters}
                  value={field.value}
                  onChange={field.onChange}
                  emptyLabel="No adapters reported by the server."
                  status={adapterStatus}
                  onRetry={retryAdapters}
                />
              )}
            />
          </section>

          <section className="space-y-2">
            <h3 className="text-sm font-medium">Per-source apply mode</h3>
            <p className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground">Auto apply</span> lets the pipeline prepare answers, fill the
              form and park it for your approval (or submit it, if auto-submit allows that source).{' '}
              <span className="font-medium text-foreground">Discover only</span> still finds and scores the jobs but
              never creates an application — you apply from the Jobs page yourself.
            </p>
            <Controller
              control={control}
              name="source_modes"
              render={({ field }) => (
                <SourceModeTable
                  adapters={adapters}
                  value={field.value}
                  onChange={field.onChange}
                  status={adapterStatus}
                  onRetry={retryAdapters}
                />
              )}
            />
          </section>

          <Separator />

          <Controller
            control={control}
            name="auto_generate_cover_letters"
            render={({ field }) => (
              <ToggleRow
                id="auto_generate_cover_letters"
                label="Generate cover letters"
                description="Drafts a tailored cover letter whenever a form asks for one."
                checked={field.value}
                onChange={field.onChange}
              />
            )}
          />

          <Controller
            control={control}
            name="notify_on_input_required"
            render={({ field }) => (
              <ToggleRow
                id="notify_on_input_required"
                label="Notify me when input is required"
                description="Sends a notification when the automation pauses for a question only you can answer."
                checked={field.value}
                onChange={field.onChange}
              />
            )}
          />

          <section className="space-y-3">
            <Controller
              control={control}
              name="auto_submit_enabled"
              render={({ field }) => (
                <ToggleRow
                  id="auto_submit_enabled"
                  label="Submit applications without asking me"
                  description="Off by default. When off, every prepared application waits for your approval in the review queue."
                  checked={field.value}
                  onChange={field.onChange}
                />
              )}
            />

            {autoSubmitEnabled ? (
              <>
                <Alert variant="warning">
                  <TriangleAlert aria-hidden />
                  <AlertTitle>Applications will be sent on your behalf</AlertTitle>
                  <AlertDescription>
                    Human review is what stops a wrong answer reaching a real employer. Auto-submit works only for
                    sources that support automated applications, and it never bypasses a CAPTCHA, OTP or login — those
                    still pause and wait for you.
                  </AlertDescription>
                </Alert>

                <div className="space-y-2">
                  <h3 className="text-sm font-medium">Auto-submit sources</h3>
                  <p className="text-xs text-muted-foreground">
                    Only adapters that support automated applications can be selected.
                  </p>
                  <Controller
                    control={control}
                    name="auto_submit_sources"
                    render={({ field }) => (
                      <SourceCheckboxes
                        idPrefix="auto-submit-source"
                        adapters={autoApplyAdapters}
                        value={field.value}
                        onChange={field.onChange}
                        emptyLabel="No adapter on this deployment supports automated applications."
                        status={adapterStatus}
                        onRetry={retryAdapters}
                      />
                    )}
                  />
                  {errors.auto_submit_sources?.message ? (
                    <p className="text-xs font-medium text-destructive">{errors.auto_submit_sources.message}</p>
                  ) : null}
                </div>
              </>
            ) : null}
          </section>

          {config?.last_run_at ? (
            <p className="text-xs text-muted-foreground">Last run {formatDateTime(config.last_run_at)}.</p>
          ) : null}

        </form>
      </CardContent>

      <CardFooter className="flex flex-wrap items-center justify-end gap-2 border-t bg-muted/30 py-3">
        {formState.isDirty ? <span className="mr-auto text-xs text-warning">Unsaved changes</span> : null}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => reset(defaults)}
          disabled={!formState.isDirty || updateConfig.isPending}
        >
          Discard
        </Button>
        <Button type="submit" form={FORM_ID} size="sm" loading={updateConfig.isPending} disabled={!formState.isDirty}>
          Save settings
        </Button>
      </CardFooter>
    </Card>
  )
}
