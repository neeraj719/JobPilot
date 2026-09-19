import { zodResolver } from '@hookform/resolvers/zod'
import { ShieldCheck } from 'lucide-react'
import * as React from 'react'
import { Controller, useFieldArray, useForm } from 'react-hook-form'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Switch } from '@/components/ui/switch'
import { toast } from '@/components/ui/toaster'
import { errorMessage } from '@/lib/api'
import { SectionCard } from '@/features/profile/components/SectionCard'
import {
  eligibilityDefaults,
  eligibilitySchema,
  eligibilityToPayload,
  type EligibilityValues,
  type TriState,
} from '@/features/profile/schema'
import { useUpdateProfile } from '@/features/profile/api'
import { useSyncDefaults } from '@/features/profile/useSyncDefaults'
import type { ProfileRead } from '@/types/api'

export interface EligibilitySectionProps {
  profile: ProfileRead
}

const FORM_ID = 'profile-eligibility-form'

const TRI_OPTIONS: { value: TriState; label: string }[] = [
  { value: 'yes', label: 'Yes' },
  { value: 'no', label: 'No' },
  { value: 'unknown', label: 'Not answered' },
]

function TriStateField({
  legend,
  hint,
  name,
  value,
  onChange,
}: {
  legend: string
  hint?: string
  name: string
  value: TriState
  onChange: (next: TriState) => void
}) {
  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium leading-none">{legend}</legend>
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
      <RadioGroup
        value={value}
        onValueChange={(next) => onChange(next as TriState)}
        className="flex flex-wrap gap-4 pt-1"
      >
        {TRI_OPTIONS.map((option) => (
          <div key={option.value} className="flex items-center gap-2">
            <RadioGroupItem value={option.value} id={`${name}-${option.value}`} />
            <Label htmlFor={`${name}-${option.value}`} className="font-normal">
              {option.label}
            </Label>
          </div>
        ))}
      </RadioGroup>
    </fieldset>
  )
}

export function EligibilitySection({ profile }: EligibilitySectionProps) {
  const updateProfile = useUpdateProfile()
  const defaults = React.useMemo(() => eligibilityDefaults(profile), [profile])

  const form = useForm<EligibilityValues>({
    resolver: zodResolver(eligibilitySchema),
    defaultValues: defaults,
  })
  const { register, control, handleSubmit, reset, formState } = form
  const errors = formState.errors

  useSyncDefaults(defaults, formState.isDirty, reset)

  const authorization = useFieldArray({ control, name: 'work_authorization' })

  const onSubmit = handleSubmit(async (values) => {
    try {
      const updated = await updateProfile.mutateAsync(eligibilityToPayload(values))
      reset(eligibilityDefaults(updated))
      toast.success('Eligibility saved')
    } catch (error) {
      toast.error('Could not save eligibility', { description: errorMessage(error) })
    }
  })

  return (
    <SectionCard
      title="Eligibility"
      description="Legal facts about where you can work. These are never inferred by AI — if a value is missing, the automation pauses and asks you."
      formId={FORM_ID}
      isDirty={formState.isDirty}
      isSaving={updateProfile.isPending}
      onReset={() => reset(defaults)}
    >
      <form id={FORM_ID} onSubmit={onSubmit} className="space-y-6" noValidate>
        <Alert>
          <ShieldCheck aria-hidden />
          <AlertDescription>
            Answer these truthfully. JobPilot copies them straight into application forms and will never guess a work
            authorization answer on your behalf.
          </AlertDescription>
        </Alert>

        <section className="space-y-3">
          <div className="space-y-0.5">
            <h3 className="text-sm font-medium">Work authorization</h3>
            <p className="text-xs text-muted-foreground">
              One row per country or region — an ISO code (IN, US, EU) or a country name both work.
            </p>
          </div>

          {authorization.fields.length === 0 ? (
            <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
              No countries recorded yet.
            </p>
          ) : (
            <ul className="divide-y divide-border rounded-lg border border-border">
              {authorization.fields.map((row, index) => (
                <li key={row.id} className="flex flex-wrap items-center gap-3 p-3">
                  <div className="min-w-[10rem] flex-1">
                    <Input
                      aria-label={`Country ${index + 1}`}
                      placeholder="IN"
                      {...register(`work_authorization.${index}.country` as const)}
                    />
                    {errors.work_authorization?.[index]?.country?.message ? (
                      <p className="mt-1 text-xs font-medium text-destructive">
                        {errors.work_authorization[index]?.country?.message}
                      </p>
                    ) : null}
                  </div>
                  <Controller
                    control={control}
                    name={`work_authorization.${index}.authorized` as const}
                    render={({ field }) => (
                      <div className="flex items-center gap-2">
                        <Switch
                          id={`auth-${row.id}`}
                          checked={field.value}
                          onCheckedChange={field.onChange}
                          aria-label={`Authorized to work in row ${index + 1}`}
                        />
                        <Label htmlFor={`auth-${row.id}`} className="font-normal">
                          {field.value ? 'Authorized' : 'Not authorized'}
                        </Label>
                      </div>
                    )}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="text-muted-foreground hover:text-destructive"
                    onClick={() => authorization.remove(index)}
                  >
                    Remove
                  </Button>
                </li>
              ))}
            </ul>
          )}

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => authorization.append({ country: '', authorized: true })}
          >
            Add country
          </Button>
        </section>

        <div className="grid gap-6 sm:grid-cols-2">
          <Controller
            control={control}
            name="requires_sponsorship"
            render={({ field }) => (
              <TriStateField
                legend="Do you require visa sponsorship?"
                hint="Asked on almost every US and EU application."
                name="requires_sponsorship"
                value={field.value}
                onChange={field.onChange}
              />
            )}
          />
          <Controller
            control={control}
            name="willing_to_relocate"
            render={({ field }) => (
              <TriStateField
                legend="Are you willing to relocate?"
                name="willing_to_relocate"
                value={field.value}
                onChange={field.onChange}
              />
            )}
          />
        </div>
      </form>
    </SectionCard>
  )
}
