import { zodResolver } from '@hookform/resolvers/zod'
import { Sparkles } from 'lucide-react'
import * as React from 'react'
import { useForm } from 'react-hook-form'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { SimpleTooltip } from '@/components/ui/tooltip'
import { toast } from '@/components/ui/toaster'
import { errorMessage } from '@/lib/api'
import { Field, FieldGrid, SectionCard } from '@/features/profile/components/SectionCard'
import { personalDefaults, personalSchema, personalToPayload, type PersonalValues } from '@/features/profile/schema'
import { useUpdateProfile } from '@/features/profile/api'
import { useSyncDefaults } from '@/features/profile/useSyncDefaults'
import type { ParsedResume, ProfileRead } from '@/types/api'

export interface PersonalSectionProps {
  profile: ProfileRead
  /** Parsed data of the default resume, used by "Import from resume". */
  resumeData: ParsedResume | null
}

const FORM_ID = 'profile-personal-form'

export function PersonalSection({ profile, resumeData }: PersonalSectionProps) {
  const updateProfile = useUpdateProfile()
  const defaults = React.useMemo(() => personalDefaults(profile), [profile])

  const form = useForm<PersonalValues>({
    resolver: zodResolver(personalSchema),
    defaultValues: defaults,
  })
  const { register, handleSubmit, reset, getValues, setValue, formState } = form

  useSyncDefaults(defaults, formState.isDirty, reset)

  const importFromResume = () => {
    if (!resumeData) return
    const current = getValues()
    const candidates: Partial<Record<keyof PersonalValues, string | null | undefined>> = {
      full_name: resumeData.name,
      email: resumeData.email,
      phone: resumeData.phone,
      linkedin_url: resumeData.links?.linkedin,
      github_url: resumeData.links?.github,
      portfolio_url: resumeData.links?.portfolio,
    }

    let filled = 0
    for (const [key, value] of Object.entries(candidates) as [keyof PersonalValues, string | null | undefined][]) {
      if (!value) continue
      if (current[key]?.trim()) continue
      setValue(key, value, { shouldDirty: true, shouldValidate: true })
      filled += 1
    }
    toast[filled > 0 ? 'success' : 'info'](
      filled > 0 ? `Filled ${filled} empty ${filled === 1 ? 'field' : 'fields'} from your resume` : 'Nothing to import',
      { description: filled > 0 ? 'Review the values, then save the section.' : 'Every field here already has a value.' },
    )
  }

  const onSubmit = handleSubmit(async (values) => {
    try {
      const updated = await updateProfile.mutateAsync(personalToPayload(values))
      reset(personalDefaults(updated))
      toast.success('Personal details saved')
    } catch (error) {
      toast.error('Could not save personal details', { description: errorMessage(error) })
    }
  })

  const errors = formState.errors

  return (
    <SectionCard
      title="Personal"
      description="Identity and contact facts. These are copied verbatim into application forms."
      formId={FORM_ID}
      isDirty={formState.isDirty}
      isSaving={updateProfile.isPending}
      onReset={() => reset(defaults)}
      headerAction={
        <SimpleTooltip
          side="bottom"
          label={
            resumeData
              ? 'Fills only the fields that are still empty, using your default resume.'
              : 'Upload and parse a resume first.'
          }
        >
          <span className="inline-flex">
            <Button type="button" variant="outline" size="sm" onClick={importFromResume} disabled={!resumeData}>
              <Sparkles aria-hidden />
              Import from resume
            </Button>
          </span>
        </SimpleTooltip>
      }
    >
      <form id={FORM_ID} onSubmit={onSubmit} className="space-y-6" noValidate>
        <FieldGrid cols={3}>
          <Field label="Full name" htmlFor="full_name" error={errors.full_name?.message}>
            <Input id="full_name" autoComplete="name" {...register('full_name')} />
          </Field>
          <Field label="First name" htmlFor="first_name" error={errors.first_name?.message}>
            <Input id="first_name" autoComplete="given-name" {...register('first_name')} />
          </Field>
          <Field label="Last name" htmlFor="last_name" error={errors.last_name?.message}>
            <Input id="last_name" autoComplete="family-name" {...register('last_name')} />
          </Field>
        </FieldGrid>

        <FieldGrid>
          <Field label="Email" htmlFor="email" error={errors.email?.message}>
            <Input id="email" type="email" autoComplete="email" {...register('email')} />
          </Field>
          <Field label="Phone" htmlFor="phone" error={errors.phone?.message} hint="Include the country code.">
            <Input id="phone" type="tel" autoComplete="tel" {...register('phone')} />
          </Field>
        </FieldGrid>

        <Field label="Address" htmlFor="address" error={errors.address?.message}>
          <Input id="address" autoComplete="street-address" {...register('address')} />
        </Field>

        <FieldGrid cols={3}>
          <Field label="City" htmlFor="city" error={errors.city?.message}>
            <Input id="city" autoComplete="address-level2" {...register('city')} />
          </Field>
          <Field label="State" htmlFor="state" error={errors.state?.message}>
            <Input id="state" autoComplete="address-level1" {...register('state')} />
          </Field>
          <Field label="Country" htmlFor="country" error={errors.country?.message}>
            <Input id="country" autoComplete="country-name" {...register('country')} />
          </Field>
        </FieldGrid>

        <FieldGrid cols={3}>
          <Field label="Postal code" htmlFor="postal_code" error={errors.postal_code?.message}>
            <Input id="postal_code" autoComplete="postal-code" {...register('postal_code')} />
          </Field>
          <Field label="LinkedIn" htmlFor="linkedin_url" error={errors.linkedin_url?.message}>
            <Input id="linkedin_url" inputMode="url" placeholder="https://linkedin.com/in/…" {...register('linkedin_url')} />
          </Field>
          <Field label="GitHub" htmlFor="github_url" error={errors.github_url?.message}>
            <Input id="github_url" inputMode="url" placeholder="https://github.com/…" {...register('github_url')} />
          </Field>
        </FieldGrid>

        <Field label="Portfolio" htmlFor="portfolio_url" error={errors.portfolio_url?.message}>
          <Input id="portfolio_url" inputMode="url" placeholder="https://…" {...register('portfolio_url')} />
        </Field>
      </form>
    </SectionCard>
  )
}
