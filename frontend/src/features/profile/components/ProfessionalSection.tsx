import { zodResolver } from '@hookform/resolvers/zod'
import { Sparkles } from 'lucide-react'
import * as React from 'react'
import { Controller, useFieldArray, useForm } from 'react-hook-form'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'
import { SimpleTooltip } from '@/components/ui/tooltip'
import { toast } from '@/components/ui/toaster'
import { errorMessage } from '@/lib/api'
import { formatCurrency } from '@/lib/utils'
import { RepeatableRow, RepeatableRows } from '@/features/profile/components/RepeatableRows'
import { Field, FieldGrid, SectionCard } from '@/features/profile/components/SectionCard'
import { TagInput } from '@/features/profile/components/TagInput'
import {
  professionalDefaults,
  professionalSchema,
  professionalToPayload,
  toNumberOrNull,
  type ProfessionalValues,
} from '@/features/profile/schema'
import { useUpdateProfile } from '@/features/profile/api'
import { useSyncDefaults } from '@/features/profile/useSyncDefaults'
import type { ParsedResume, ProfileRead } from '@/types/api'

export interface ProfessionalSectionProps {
  profile: ProfileRead
  resumeData: ParsedResume | null
}

const FORM_ID = 'profile-professional-form'

const emptyExperience = { company: '', title: '', start: '', end: '', description: '' }
const emptyEducation = { institution: '', degree: '', field: '', start: '', end: '', grade: '' }
const emptyCertification = { name: '', issuer: '', year: '' }
const emptyProject = { name: '', description: '', technologies: [] as string[], url: '' }

export function ProfessionalSection({ profile, resumeData }: ProfessionalSectionProps) {
  const updateProfile = useUpdateProfile()
  const defaults = React.useMemo(() => professionalDefaults(profile), [profile])

  const form = useForm<ProfessionalValues>({
    resolver: zodResolver(professionalSchema),
    defaultValues: defaults,
  })
  const { register, control, handleSubmit, reset, getValues, setValue, watch, formState } = form
  const errors = formState.errors

  useSyncDefaults(defaults, formState.isDirty, reset)

  const experience = useFieldArray({ control, name: 'previous_companies' })
  const education = useFieldArray({ control, name: 'education' })
  const certifications = useFieldArray({ control, name: 'certifications' })
  const projects = useFieldArray({ control, name: 'projects' })
  const achievements = useFieldArray({ control, name: 'achievements' })
  const skillYears = useFieldArray({ control, name: 'skill_experience' })

  const skills = watch('skills')
  const currentSalary = watch('current_salary')

  const importFromResume = () => {
    if (!resumeData) return
    const current = getValues()
    let filled = 0

    if (!current.summary.trim() && resumeData.summary) {
      setValue('summary', resumeData.summary, { shouldDirty: true })
      filled += 1
    }
    if (!current.years_of_experience.trim() && resumeData.total_experience_years != null) {
      setValue('years_of_experience', String(resumeData.total_experience_years), { shouldDirty: true })
      filled += 1
    }
    if (current.skills.length === 0 && resumeData.skills?.length) {
      setValue('skills', resumeData.skills, { shouldDirty: true })
      filled += 1
    }
    const latest = resumeData.experience?.[0]
    if (latest) {
      if (!current.current_designation.trim() && latest.title) {
        setValue('current_designation', latest.title, { shouldDirty: true })
        filled += 1
      }
      if (!current.current_company.trim() && latest.company) {
        setValue('current_company', latest.company, { shouldDirty: true })
        filled += 1
      }
    }
    if (current.previous_companies.length === 0 && resumeData.experience?.length) {
      setValue(
        'previous_companies',
        resumeData.experience.map((entry) => ({
          company: entry.company ?? '',
          title: entry.title ?? '',
          start: entry.start ?? '',
          end: entry.end ?? '',
          description: entry.description ?? '',
        })),
        { shouldDirty: true },
      )
      filled += 1
    }
    if (current.education.length === 0 && resumeData.education?.length) {
      setValue(
        'education',
        resumeData.education.map((entry) => ({
          institution: entry.institution ?? '',
          degree: entry.degree ?? '',
          field: entry.field ?? '',
          start: entry.start ?? '',
          end: entry.end ?? '',
          grade: entry.grade ?? '',
        })),
        { shouldDirty: true },
      )
      filled += 1
    }
    if (current.projects.length === 0 && resumeData.projects?.length) {
      setValue(
        'projects',
        resumeData.projects.map((entry) => ({
          name: entry.name ?? '',
          description: entry.description ?? '',
          technologies: entry.technologies ?? [],
          url: entry.url ?? '',
        })),
        { shouldDirty: true },
      )
      filled += 1
    }
    if (current.certifications.length === 0 && resumeData.certifications?.length) {
      setValue(
        'certifications',
        resumeData.certifications.map((entry) => ({
          name: entry.name ?? '',
          issuer: entry.issuer ?? '',
          year: entry.year == null ? '' : String(entry.year),
        })),
        { shouldDirty: true },
      )
      filled += 1
    }

    toast[filled > 0 ? 'success' : 'info'](
      filled > 0 ? `Imported ${filled} ${filled === 1 ? 'section' : 'sections'} from your resume` : 'Nothing to import',
      {
        description:
          filled > 0
            ? 'Only empty fields were touched. Review, then save the section.'
            : 'Everything here is already filled in.',
      },
    )
  }

  const onSubmit = handleSubmit(async (values) => {
    try {
      const updated = await updateProfile.mutateAsync(professionalToPayload(values))
      reset(professionalDefaults(updated))
      toast.success('Professional details saved')
    } catch (error) {
      toast.error('Could not save professional details', { description: errorMessage(error) })
    }
  })

  const salaryPreview = toNumberOrNull(currentSalary)

  return (
    <SectionCard
      title="Professional"
      description="Experience, skills and everything a form might ask about your background."
      formId={FORM_ID}
      isDirty={formState.isDirty}
      isSaving={updateProfile.isPending}
      onReset={() => reset(defaults)}
      headerAction={
        <SimpleTooltip
          side="bottom"
          label={
            resumeData
              ? 'Fills only the empty fields and lists, using your default resume.'
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
        <Field label="Headline" htmlFor="headline" error={errors.headline?.message} hint="One line, as it would appear under your name.">
          <Input id="headline" {...register('headline')} />
        </Field>

        <Field label="Professional summary" htmlFor="summary" error={errors.summary?.message}>
          <Textarea id="summary" rows={4} {...register('summary')} />
        </Field>

        <FieldGrid>
          <Field label="Current designation" htmlFor="current_designation" error={errors.current_designation?.message}>
            <Input id="current_designation" {...register('current_designation')} />
          </Field>
          <Field label="Current company" htmlFor="current_company" error={errors.current_company?.message}>
            <Input id="current_company" {...register('current_company')} />
          </Field>
        </FieldGrid>

        <FieldGrid>
          <Field
            label="Years of experience"
            htmlFor="years_of_experience"
            error={errors.years_of_experience?.message}
            hint="Decimals are fine, e.g. 2.5"
          >
            <Input id="years_of_experience" inputMode="decimal" {...register('years_of_experience')} />
          </Field>
          <Field
            label="Current salary (annual)"
            htmlFor="current_salary"
            error={errors.current_salary?.message}
            hint={salaryPreview !== null ? formatCurrency(salaryPreview) : 'Leave empty to keep it private.'}
          >
            <Input id="current_salary" inputMode="numeric" {...register('current_salary')} />
          </Field>
        </FieldGrid>

        <Separator />

        <Field label="Skills" hint="Used for matching. Type and press Enter, or pick a suggestion.">
          <Controller
            control={control}
            name="skills"
            render={({ field }) => (
              <TagInput
                value={field.value}
                onChange={field.onChange}
                placeholder="React, TypeScript, PostgreSQL…"
                suggestions={resumeData?.skills ?? []}
                suggestionsLabel="From your resume"
              />
            )}
          />
        </Field>

        <Field label="Technologies" hint="Tools and frameworks you'd list separately from core skills.">
          <Controller
            control={control}
            name="technologies"
            render={({ field }) => (
              <TagInput value={field.value} onChange={field.onChange} placeholder="Next.js, Tailwind CSS…" />
            )}
          />
        </Field>

        <RepeatableRows
          label="Skill experience"
          description="Years per skill. Forms that ask “how many years of X?” read this table."
          emptyLabel="No per-skill experience recorded yet."
          addLabel="Add skill"
          count={skillYears.fields.length}
          onAdd={() => skillYears.append({ skill: '', years: '' })}
        >
          {skillYears.fields.map((row, index) => (
            <div key={row.id} className="flex flex-wrap items-end gap-3 rounded-lg border border-border bg-muted/20 p-3">
              <Field label="Skill" className="min-w-[12rem] flex-1" htmlFor={`skill-${row.id}`}>
                <Input
                  id={`skill-${row.id}`}
                  list="profile-skill-suggestions"
                  {...register(`skill_experience.${index}.skill` as const)}
                />
              </Field>
              <Field
                label="Years"
                className="w-28"
                htmlFor={`skill-years-${row.id}`}
                error={errors.skill_experience?.[index]?.years?.message}
              >
                <Input
                  id={`skill-years-${row.id}`}
                  inputMode="decimal"
                  {...register(`skill_experience.${index}.years` as const)}
                />
              </Field>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="mb-1 text-muted-foreground hover:text-destructive"
                onClick={() => skillYears.remove(index)}
              >
                Remove
              </Button>
            </div>
          ))}
        </RepeatableRows>
        <datalist id="profile-skill-suggestions">
          {skills.map((skill) => (
            <option key={skill} value={skill} />
          ))}
        </datalist>

        <Separator />

        <RepeatableRows
          label="Work history"
          emptyLabel="No previous roles added yet."
          addLabel="Add role"
          count={experience.fields.length}
          onAdd={() => experience.append(emptyExperience)}
        >
          {experience.fields.map((row, index) => (
            <RepeatableRow
              key={row.id}
              title={`Role ${index + 1}`}
              removeLabel={`Remove role ${index + 1}`}
              onRemove={() => experience.remove(index)}
            >
              <FieldGrid>
                <Field label="Company" htmlFor={`exp-company-${row.id}`}>
                  <Input id={`exp-company-${row.id}`} {...register(`previous_companies.${index}.company` as const)} />
                </Field>
                <Field label="Title" htmlFor={`exp-title-${row.id}`}>
                  <Input id={`exp-title-${row.id}`} {...register(`previous_companies.${index}.title` as const)} />
                </Field>
              </FieldGrid>
              <FieldGrid>
                <Field label="Start" htmlFor={`exp-start-${row.id}`} hint="e.g. 2023-03">
                  <Input id={`exp-start-${row.id}`} {...register(`previous_companies.${index}.start` as const)} />
                </Field>
                <Field label="End" htmlFor={`exp-end-${row.id}`} hint="Leave empty or type “Present”.">
                  <Input id={`exp-end-${row.id}`} {...register(`previous_companies.${index}.end` as const)} />
                </Field>
              </FieldGrid>
              <Field label="What you did" htmlFor={`exp-desc-${row.id}`}>
                <Textarea id={`exp-desc-${row.id}`} rows={3} {...register(`previous_companies.${index}.description` as const)} />
              </Field>
            </RepeatableRow>
          ))}
        </RepeatableRows>

        <RepeatableRows
          label="Education"
          emptyLabel="No education added yet."
          addLabel="Add education"
          count={education.fields.length}
          onAdd={() => education.append(emptyEducation)}
        >
          {education.fields.map((row, index) => (
            <RepeatableRow
              key={row.id}
              title={`Education ${index + 1}`}
              removeLabel={`Remove education ${index + 1}`}
              onRemove={() => education.remove(index)}
            >
              <FieldGrid>
                <Field label="Institution" htmlFor={`edu-inst-${row.id}`}>
                  <Input id={`edu-inst-${row.id}`} {...register(`education.${index}.institution` as const)} />
                </Field>
                <Field label="Degree" htmlFor={`edu-degree-${row.id}`}>
                  <Input id={`edu-degree-${row.id}`} {...register(`education.${index}.degree` as const)} />
                </Field>
              </FieldGrid>
              <FieldGrid cols={3}>
                <Field label="Field of study" htmlFor={`edu-field-${row.id}`}>
                  <Input id={`edu-field-${row.id}`} {...register(`education.${index}.field` as const)} />
                </Field>
                <Field label="Start" htmlFor={`edu-start-${row.id}`}>
                  <Input id={`edu-start-${row.id}`} {...register(`education.${index}.start` as const)} />
                </Field>
                <Field label="End" htmlFor={`edu-end-${row.id}`}>
                  <Input id={`edu-end-${row.id}`} {...register(`education.${index}.end` as const)} />
                </Field>
              </FieldGrid>
              <Field label="Grade / GPA" htmlFor={`edu-grade-${row.id}`} className="sm:max-w-xs">
                <Input id={`edu-grade-${row.id}`} {...register(`education.${index}.grade` as const)} />
              </Field>
            </RepeatableRow>
          ))}
        </RepeatableRows>

        <RepeatableRows
          label="Certifications"
          emptyLabel="No certifications added yet."
          addLabel="Add certification"
          count={certifications.fields.length}
          onAdd={() => certifications.append(emptyCertification)}
        >
          {certifications.fields.map((row, index) => (
            <RepeatableRow
              key={row.id}
              title={`Certification ${index + 1}`}
              removeLabel={`Remove certification ${index + 1}`}
              onRemove={() => certifications.remove(index)}
            >
              <FieldGrid cols={3}>
                <Field label="Name" htmlFor={`cert-name-${row.id}`}>
                  <Input id={`cert-name-${row.id}`} {...register(`certifications.${index}.name` as const)} />
                </Field>
                <Field label="Issuer" htmlFor={`cert-issuer-${row.id}`}>
                  <Input id={`cert-issuer-${row.id}`} {...register(`certifications.${index}.issuer` as const)} />
                </Field>
                <Field label="Year" htmlFor={`cert-year-${row.id}`}>
                  <Input id={`cert-year-${row.id}`} inputMode="numeric" {...register(`certifications.${index}.year` as const)} />
                </Field>
              </FieldGrid>
            </RepeatableRow>
          ))}
        </RepeatableRows>

        <RepeatableRows
          label="Projects"
          emptyLabel="No projects added yet."
          addLabel="Add project"
          count={projects.fields.length}
          onAdd={() => projects.append(emptyProject)}
        >
          {projects.fields.map((row, index) => (
            <RepeatableRow
              key={row.id}
              title={`Project ${index + 1}`}
              removeLabel={`Remove project ${index + 1}`}
              onRemove={() => projects.remove(index)}
            >
              <FieldGrid>
                <Field label="Name" htmlFor={`proj-name-${row.id}`}>
                  <Input id={`proj-name-${row.id}`} {...register(`projects.${index}.name` as const)} />
                </Field>
                <Field label="URL" htmlFor={`proj-url-${row.id}`} error={errors.projects?.[index]?.url?.message}>
                  <Input id={`proj-url-${row.id}`} inputMode="url" {...register(`projects.${index}.url` as const)} />
                </Field>
              </FieldGrid>
              <Field label="Description" htmlFor={`proj-desc-${row.id}`}>
                <Textarea id={`proj-desc-${row.id}`} rows={2} {...register(`projects.${index}.description` as const)} />
              </Field>
              <Field label="Technologies">
                <Controller
                  control={control}
                  name={`projects.${index}.technologies` as const}
                  render={({ field }) => (
                    <TagInput value={field.value} onChange={field.onChange} placeholder="Add a technology" />
                  )}
                />
              </Field>
            </RepeatableRow>
          ))}
        </RepeatableRows>

        <RepeatableRows
          label="Achievements"
          emptyLabel="No achievements added yet."
          addLabel="Add achievement"
          count={achievements.fields.length}
          onAdd={() => achievements.append({ value: '' })}
        >
          {achievements.fields.map((row, index) => (
            <div key={row.id} className="flex items-start gap-2">
              <Input
                aria-label={`Achievement ${index + 1}`}
                placeholder="Cut deployment time by 50% by introducing Docker CI/CD."
                {...register(`achievements.${index}.value` as const)}
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="text-muted-foreground hover:text-destructive"
                onClick={() => achievements.remove(index)}
              >
                Remove
              </Button>
            </div>
          ))}
        </RepeatableRows>

        <Field label="Languages" hint="Spoken languages, not programming languages.">
          <Controller
            control={control}
            name="languages"
            render={({ field }) => (
              <TagInput value={field.value} onChange={field.onChange} placeholder="English, Hindi…" />
            )}
          />
        </Field>
      </form>
    </SectionCard>
  )
}
