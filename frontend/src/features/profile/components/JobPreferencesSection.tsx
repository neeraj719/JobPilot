import { zodResolver } from '@hookform/resolvers/zod'
import * as React from 'react'
import { Controller, useForm } from 'react-hook-form'

import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Slider } from '@/components/ui/slider'
import { toast } from '@/components/ui/toaster'
import { errorMessage } from '@/lib/api'
import { EMPLOYMENT_TYPE_LABELS, WORK_MODE_LABELS, formatCurrency } from '@/lib/utils'
import { Field, FieldGrid, SectionCard } from '@/features/profile/components/SectionCard'
import { TagInput } from '@/features/profile/components/TagInput'
import {
  CURRENCIES,
  jobPreferenceDefaults,
  jobPreferenceSchema,
  jobPreferenceToPayload,
  toNumberOrNull,
  type JobPreferenceValues,
} from '@/features/profile/schema'
import { useUpdateJobPreferences } from '@/features/profile/api'
import { useSyncDefaults } from '@/features/profile/useSyncDefaults'
import { EMPLOYMENT_TYPES, WORK_MODES } from '@/types/api'
import type { EmploymentType, JobPreferenceRead, ProfileRead, WorkMode } from '@/types/api'

export interface JobPreferencesSectionProps {
  preferences: JobPreferenceRead
  profile: ProfileRead | undefined
}

const FORM_ID = 'profile-job-preferences-form'

/** Toggle one value inside an array field without mutating it. */
function toggle<T>(list: T[], value: T, checked: boolean): T[] {
  return checked ? [...list.filter((item) => item !== value), value] : list.filter((item) => item !== value)
}

export function JobPreferencesSection({ preferences, profile }: JobPreferencesSectionProps) {
  const updatePreferences = useUpdateJobPreferences()
  const defaults = React.useMemo(() => jobPreferenceDefaults(preferences), [preferences])

  const form = useForm<JobPreferenceValues>({
    resolver: zodResolver(jobPreferenceSchema),
    defaultValues: defaults,
  })
  const { register, control, handleSubmit, reset, watch, formState } = form
  const errors = formState.errors

  useSyncDefaults(defaults, formState.isDirty, reset)

  const currency = watch('currency')
  const minSalary = toNumberOrNull(watch('min_salary'))
  const desiredSalary = toNumberOrNull(watch('desired_salary'))

  const onSubmit = handleSubmit(async (values) => {
    try {
      const updated = await updatePreferences.mutateAsync(jobPreferenceToPayload(values))
      reset(jobPreferenceDefaults(updated))
      toast.success('Job preferences saved', { description: 'New matches will use these thresholds.' })
    } catch (error) {
      toast.error('Could not save job preferences', { description: errorMessage(error) })
    }
  })

  return (
    <SectionCard
      title="Job preferences"
      description="What to look for and what to ignore. The matcher and the automation scheduler both read these."
      formId={FORM_ID}
      isDirty={formState.isDirty}
      isSaving={updatePreferences.isPending}
      onReset={() => reset(defaults)}
    >
      <form id={FORM_ID} onSubmit={onSubmit} className="space-y-6" noValidate>
        <Field label="Desired titles" hint="Roles you actually want. Titles are scored against these.">
          <Controller
            control={control}
            name="desired_titles"
            render={({ field }) => (
              <TagInput
                value={field.value}
                onChange={field.onChange}
                placeholder="Software Engineer, Backend Engineer…"
                suggestions={profile?.current_designation ? [profile.current_designation] : []}
                suggestionsLabel="From your profile"
              />
            )}
          />
        </Field>

        <FieldGrid cols={3}>
          <Field
            label="Minimum salary"
            htmlFor="min_salary"
            error={errors.min_salary?.message}
            hint={minSalary !== null ? formatCurrency(minSalary, currency) : 'Jobs below this are deprioritised.'}
          >
            <Input id="min_salary" inputMode="numeric" {...register('min_salary')} />
          </Field>
          <Field
            label="Target salary"
            htmlFor="desired_salary"
            error={errors.desired_salary?.message}
            hint={desiredSalary !== null ? formatCurrency(desiredSalary, currency) : 'Used to answer “expected CTC”.'}
          >
            <Input id="desired_salary" inputMode="numeric" {...register('desired_salary')} />
          </Field>
          <Field label="Currency" htmlFor="currency" error={errors.currency?.message}>
            <Controller
              control={control}
              name="currency"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id="currency">
                    <SelectValue placeholder="Currency" />
                  </SelectTrigger>
                  <SelectContent>
                    {CURRENCIES.map((code) => (
                      <SelectItem key={code} value={code}>
                        {code}
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
            label="Notice period (days)"
            htmlFor="notice_period_days"
            error={errors.notice_period_days?.message}
          >
            <Input id="notice_period_days" inputMode="numeric" {...register('notice_period_days')} />
          </Field>
          <Field label="Experience min (years)" htmlFor="experience_min" error={errors.experience_min?.message}>
            <Input id="experience_min" inputMode="decimal" {...register('experience_min')} />
          </Field>
          <Field label="Experience max (years)" htmlFor="experience_max" error={errors.experience_max?.message}>
            <Input id="experience_max" inputMode="decimal" {...register('experience_max')} />
          </Field>
        </FieldGrid>

        <Field label="Preferred locations" hint="Add “Remote” to include fully remote roles.">
          <Controller
            control={control}
            name="preferred_locations"
            render={({ field }) => (
              <TagInput
                value={field.value}
                onChange={field.onChange}
                placeholder="Bangalore, Remote…"
                suggestions={profile?.city ? [profile.city, 'Remote'] : ['Remote']}
              />
            )}
          />
        </Field>

        <div className="grid gap-6 sm:grid-cols-2">
          <Controller
            control={control}
            name="work_modes"
            render={({ field }) => (
              <fieldset className="space-y-2">
                <legend className="text-sm font-medium leading-none">Work modes</legend>
                <div className="space-y-2 pt-1">
                  {WORK_MODES.map((mode: WorkMode) => (
                    <div key={mode} className="flex items-center gap-2">
                      <Checkbox
                        id={`work-mode-${mode}`}
                        checked={field.value.includes(mode)}
                        onCheckedChange={(checked) => field.onChange(toggle(field.value, mode, checked === true))}
                      />
                      <Label htmlFor={`work-mode-${mode}`} className="font-normal">
                        {WORK_MODE_LABELS[mode]}
                      </Label>
                    </div>
                  ))}
                </div>
              </fieldset>
            )}
          />

          <Controller
            control={control}
            name="employment_types"
            render={({ field }) => (
              <fieldset className="space-y-2">
                <legend className="text-sm font-medium leading-none">Employment types</legend>
                <div className="space-y-2 pt-1">
                  {EMPLOYMENT_TYPES.map((type: EmploymentType) => (
                    <div key={type} className="flex items-center gap-2">
                      <Checkbox
                        id={`employment-type-${type}`}
                        checked={field.value.includes(type)}
                        onCheckedChange={(checked) => field.onChange(toggle(field.value, type, checked === true))}
                      />
                      <Label htmlFor={`employment-type-${type}`} className="font-normal">
                        {EMPLOYMENT_TYPE_LABELS[type]}
                      </Label>
                    </div>
                  ))}
                </div>
              </fieldset>
            )}
          />
        </div>

        <Separator />

        <Field label="Preferred technologies" hint="Boosts the skill score when a posting mentions these.">
          <Controller
            control={control}
            name="preferred_technologies"
            render={({ field }) => (
              <TagInput
                value={field.value}
                onChange={field.onChange}
                placeholder="React, PostgreSQL…"
                suggestions={profile?.skills ?? []}
                suggestionsLabel="From your profile"
              />
            )}
          />
        </Field>

        <Field label="Excluded keywords" hint="Any posting containing one of these is skipped outright.">
          <Controller
            control={control}
            name="excluded_keywords"
            render={({ field }) => (
              <TagInput value={field.value} onChange={field.onChange} placeholder="unpaid, commission only…" />
            )}
          />
        </Field>

        <Controller
          control={control}
          name="min_match_score"
          render={({ field }) => (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="min_match_score">Minimum match score</Label>
                <span className="text-sm font-semibold tabular-nums">{field.value}</span>
              </div>
              <Slider
                id="min_match_score"
                min={0}
                max={100}
                step={1}
                value={[field.value]}
                onValueChange={([next]) => field.onChange(next ?? 0)}
                aria-label="Minimum match score"
              />
              <p className="text-xs text-muted-foreground">
                Jobs scoring below this never reach your queue. 75 is a good starting point.
              </p>
            </div>
          )}
        />

        <Field
          label="Only jobs posted within (hours)"
          htmlFor="only_posted_within_hours"
          error={errors.only_posted_within_hours?.message}
          hint="168 = one week. Leave empty to ignore posting age."
        >
          <Input
            id="only_posted_within_hours"
            inputMode="numeric"
            className="sm:max-w-xs"
            {...register('only_posted_within_hours')}
          />
        </Field>
      </form>
    </SectionCard>
  )
}
