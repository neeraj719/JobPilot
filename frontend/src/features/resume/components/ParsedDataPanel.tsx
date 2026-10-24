import { zodResolver } from '@hookform/resolvers/zod'
import { ChevronDown, RefreshCw } from 'lucide-react'
import * as React from 'react'
import { Controller, useFieldArray, useForm } from 'react-hook-form'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'
import { toast } from '@/components/ui/toaster'
import { errorMessage } from '@/lib/api'
import { RepeatableRow, RepeatableRows } from '@/features/profile/components/RepeatableRows'
import { Field, FieldGrid } from '@/features/profile/components/SectionCard'
import { TagInput } from '@/features/profile/components/TagInput'
import { useReparseResume, useSaveParsedData } from '@/features/resume/api'
import { useSyncDefaults } from '@/features/profile/useSyncDefaults'
import { parsedResumeDefaults, parsedResumeSchema, toParsedResume, type ParsedResumeValues } from '@/features/resume/schema'
import type { ResumeRead } from '@/types/api'
import { AiRunButton } from '@/features/ai-providers/components/AiRunButton'
import type { WorkflowTarget } from '@/features/ai-providers/types'

export interface ParsedDataPanelProps {
  resume: ResumeRead
}

const FORM_ID = 'resume-parsed-data-form'

/** Raw extracted text if the backend ever starts returning it (`ResumeRead` has no field for it today). */
function rawText(resume: ResumeRead): string | null {
  const candidate = (resume as unknown as { extracted_text?: unknown }).extracted_text
  return typeof candidate === 'string' && candidate.trim() ? candidate : null
}

export function ParsedDataPanel({ resume }: ParsedDataPanelProps) {
  const saveParsed = useSaveParsedData()
  const reparse = useReparseResume()
  const defaults = React.useMemo(() => parsedResumeDefaults(resume.parsed_data), [resume.parsed_data])
  const [showRaw, setShowRaw] = React.useState(false)

  const form = useForm<ParsedResumeValues>({
    resolver: zodResolver(parsedResumeSchema),
    defaultValues: defaults,
  })
  const { register, control, handleSubmit, reset, formState } = form
  const errors = formState.errors

  useSyncDefaults(defaults, formState.isDirty, reset)

  const experience = useFieldArray({ control, name: 'experience' })
  const education = useFieldArray({ control, name: 'education' })
  const projects = useFieldArray({ control, name: 'projects' })
  const certifications = useFieldArray({ control, name: 'certifications' })

  const onSubmit = handleSubmit(async (values) => {
    try {
      // Keep the fields this panel does not edit (headline, achievements, section order…,
      // set in the resume editor): the backend replaces the whole structure on save.
      const data = { ...(resume.parsed_data as Record<string, unknown>), ...toParsedResume(values) } as typeof resume.parsed_data
      const updated = await saveParsed.mutateAsync({ id: resume.id, data: data as ReturnType<typeof toParsedResume> })
      reset(parsedResumeDefaults(updated.parsed_data))
      toast.success(`Saved as version ${updated.current_version}`, {
        description: 'The previous version is kept in the history below.',
      })
    } catch (error) {
      toast.error('Could not save the extracted information', { description: errorMessage(error) })
    }
  })

  const onReparse = async (ai?: WorkflowTarget) => {
    if ((resume.current_version ?? 1) > 1 && !window.confirm('Re-running extraction reads your uploaded file again and replaces the information below, including edits and applied suggestions. The current version stays in the history so you can restore it. Continue?')) return
    try {
      const previous = resume.current_version ?? 1
      const updated = await reparse.mutateAsync({ id: resume.id, ai })
      const saved = (updated.current_version ?? 1) > previous
      toast[updated.parse_status === 'PARSED' ? 'success' : 'warning'](
        updated.parse_status === 'PARSED' ? 'Extraction re-run' : 'Extraction did not finish',
        {
          description:
            updated.parse_error ??
            (saved
              ? `Saved as version ${updated.current_version}. Version ${previous} is kept in the history.`
              : 'Nothing changed.'),
        },
      )
    } catch (error) {
      toast.error('Could not re-run extraction', { description: errorMessage(error) })
    }
  }

  const raw = rawText(resume)

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <CardTitle className="text-base">Extracted information</CardTitle>
          <CardDescription>
            What the parser read from <span className="font-medium">{resume.name}</span>. Editing it saves a new
            version — nothing is overwritten.
          </CardDescription>
        </div>
        <AiRunButton
          task="parse_resume"
          context="Your resume text"
          type="button"
          variant="outline"
          size="sm"
          onRun={(ai) => onReparse(ai)}
          loading={reparse.isPending}
          wrapperClassName="sm:items-end"
        >
          <RefreshCw aria-hidden />
          Re-run extraction
        </AiRunButton>
      </CardHeader>

      <CardContent className="space-y-6">
        {resume.parse_status === 'FAILED' ? (
          <Alert variant="warning">
            <AlertDescription>
              Automatic extraction failed{resume.parse_error ? `: ${resume.parse_error}` : '.'} You can still fill these
              fields in by hand — applications will use whatever is saved here.
            </AlertDescription>
          </Alert>
        ) : null}

        <form id={FORM_ID} onSubmit={onSubmit} className="space-y-6" noValidate>
          <FieldGrid cols={3}>
            <Field label="Name" htmlFor="parsed-name" error={errors.name?.message}>
              <Input id="parsed-name" {...register('name')} />
            </Field>
            <Field label="Email" htmlFor="parsed-email" error={errors.email?.message}>
              <Input id="parsed-email" type="email" {...register('email')} />
            </Field>
            <Field label="Phone" htmlFor="parsed-phone" error={errors.phone?.message}>
              <Input id="parsed-phone" {...register('phone')} />
            </Field>
          </FieldGrid>

          <Field label="Summary" htmlFor="parsed-summary" error={errors.summary?.message}>
            <Textarea id="parsed-summary" rows={4} {...register('summary')} />
          </Field>

          <Field
            label="Total experience (years)"
            htmlFor="parsed-years"
            className="sm:max-w-xs"
            error={errors.total_experience_years?.message}
          >
            <Input id="parsed-years" inputMode="decimal" {...register('total_experience_years')} />
          </Field>

          <Field label="Skills" hint="These drive the skill part of every match score.">
            <Controller
              control={control}
              name="skills"
              render={({ field }) => (
                <TagInput value={field.value} onChange={field.onChange} placeholder="Add a skill" />
              )}
            />
          </Field>

          <FieldGrid cols={3}>
            <Field label="LinkedIn" htmlFor="parsed-linkedin" error={errors.linkedin?.message}>
              <Input id="parsed-linkedin" inputMode="url" {...register('linkedin')} />
            </Field>
            <Field label="GitHub" htmlFor="parsed-github" error={errors.github?.message}>
              <Input id="parsed-github" inputMode="url" {...register('github')} />
            </Field>
            <Field label="Portfolio" htmlFor="parsed-portfolio" error={errors.portfolio?.message}>
              <Input id="parsed-portfolio" inputMode="url" {...register('portfolio')} />
            </Field>
          </FieldGrid>

          <Separator />

          <RepeatableRows
            label="Experience"
            emptyLabel="No roles were extracted."
            addLabel="Add role"
            count={experience.fields.length}
            onAdd={() =>
              experience.append({ company: '', title: '', start: '', end: '', description: '', technologies: [] })
            }
          >
            {experience.fields.map((row, index) => (
              <RepeatableRow
                key={row.id}
                title={`Role ${index + 1}`}
                removeLabel={`Remove role ${index + 1}`}
                onRemove={() => experience.remove(index)}
              >
                <FieldGrid>
                  <Field label="Company" htmlFor={`pexp-company-${row.id}`}>
                    <Input id={`pexp-company-${row.id}`} {...register(`experience.${index}.company` as const)} />
                  </Field>
                  <Field label="Title" htmlFor={`pexp-title-${row.id}`}>
                    <Input id={`pexp-title-${row.id}`} {...register(`experience.${index}.title` as const)} />
                  </Field>
                </FieldGrid>
                <FieldGrid>
                  <Field label="Start" htmlFor={`pexp-start-${row.id}`}>
                    <Input id={`pexp-start-${row.id}`} {...register(`experience.${index}.start` as const)} />
                  </Field>
                  <Field label="End" htmlFor={`pexp-end-${row.id}`}>
                    <Input id={`pexp-end-${row.id}`} {...register(`experience.${index}.end` as const)} />
                  </Field>
                </FieldGrid>
                <Field label="Description" htmlFor={`pexp-desc-${row.id}`}>
                  <Textarea id={`pexp-desc-${row.id}`} rows={3} {...register(`experience.${index}.description` as const)} />
                </Field>
                <Field label="Technologies">
                  <Controller
                    control={control}
                    name={`experience.${index}.technologies` as const}
                    render={({ field }) => (
                      <TagInput value={field.value} onChange={field.onChange} placeholder="Add a technology" />
                    )}
                  />
                </Field>
              </RepeatableRow>
            ))}
          </RepeatableRows>

          <RepeatableRows
            label="Education"
            emptyLabel="No education was extracted."
            addLabel="Add education"
            count={education.fields.length}
            onAdd={() => education.append({ institution: '', degree: '', field: '', start: '', end: '' })}
          >
            {education.fields.map((row, index) => (
              <RepeatableRow
                key={row.id}
                title={`Education ${index + 1}`}
                removeLabel={`Remove education ${index + 1}`}
                onRemove={() => education.remove(index)}
              >
                <FieldGrid>
                  <Field label="Institution" htmlFor={`pedu-inst-${row.id}`}>
                    <Input id={`pedu-inst-${row.id}`} {...register(`education.${index}.institution` as const)} />
                  </Field>
                  <Field label="Degree" htmlFor={`pedu-degree-${row.id}`}>
                    <Input id={`pedu-degree-${row.id}`} {...register(`education.${index}.degree` as const)} />
                  </Field>
                </FieldGrid>
                <FieldGrid cols={3}>
                  <Field label="Field" htmlFor={`pedu-field-${row.id}`}>
                    <Input id={`pedu-field-${row.id}`} {...register(`education.${index}.field` as const)} />
                  </Field>
                  <Field label="Start" htmlFor={`pedu-start-${row.id}`}>
                    <Input id={`pedu-start-${row.id}`} {...register(`education.${index}.start` as const)} />
                  </Field>
                  <Field label="End" htmlFor={`pedu-end-${row.id}`}>
                    <Input id={`pedu-end-${row.id}`} {...register(`education.${index}.end` as const)} />
                  </Field>
                </FieldGrid>
              </RepeatableRow>
            ))}
          </RepeatableRows>

          <RepeatableRows
            label="Projects"
            emptyLabel="No projects were extracted."
            addLabel="Add project"
            count={projects.fields.length}
            onAdd={() => projects.append({ name: '', description: '', technologies: [] })}
          >
            {projects.fields.map((row, index) => (
              <RepeatableRow
                key={row.id}
                title={`Project ${index + 1}`}
                removeLabel={`Remove project ${index + 1}`}
                onRemove={() => projects.remove(index)}
              >
                <Field label="Name" htmlFor={`pproj-name-${row.id}`}>
                  <Input id={`pproj-name-${row.id}`} {...register(`projects.${index}.name` as const)} />
                </Field>
                <Field label="Description" htmlFor={`pproj-desc-${row.id}`}>
                  <Textarea id={`pproj-desc-${row.id}`} rows={2} {...register(`projects.${index}.description` as const)} />
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
            label="Certifications"
            emptyLabel="No certifications were extracted."
            addLabel="Add certification"
            count={certifications.fields.length}
            onAdd={() => certifications.append({ name: '', issuer: '', year: '' })}
          >
            {certifications.fields.map((row, index) => (
              <RepeatableRow
                key={row.id}
                title={`Certification ${index + 1}`}
                removeLabel={`Remove certification ${index + 1}`}
                onRemove={() => certifications.remove(index)}
              >
                <FieldGrid cols={3}>
                  <Field label="Name" htmlFor={`pcert-name-${row.id}`}>
                    <Input id={`pcert-name-${row.id}`} {...register(`certifications.${index}.name` as const)} />
                  </Field>
                  <Field label="Issuer" htmlFor={`pcert-issuer-${row.id}`}>
                    <Input id={`pcert-issuer-${row.id}`} {...register(`certifications.${index}.issuer` as const)} />
                  </Field>
                  <Field label="Year" htmlFor={`pcert-year-${row.id}`}>
                    <Input id={`pcert-year-${row.id}`} inputMode="numeric" {...register(`certifications.${index}.year` as const)} />
                  </Field>
                </FieldGrid>
              </RepeatableRow>
            ))}
          </RepeatableRows>
        </form>

        {raw ? (
          <div className="rounded-lg border border-border">
            <button
              type="button"
              onClick={() => setShowRaw((open) => !open)}
              aria-expanded={showRaw}
              className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Raw extracted text
              <ChevronDown className={showRaw ? 'size-4 rotate-180 transition-transform' : 'size-4 transition-transform'} aria-hidden />
            </button>
            {showRaw ? (
              <pre className="max-h-80 overflow-auto whitespace-pre-wrap border-t border-border bg-muted/30 p-3 text-xs text-muted-foreground">
                {raw}
              </pre>
            ) : null}
          </div>
        ) : null}
      </CardContent>

      <CardFooter className="flex flex-wrap items-center justify-end gap-2 border-t bg-muted/30 py-3">
        {formState.isDirty ? (
          <span className="mr-auto text-xs text-warning">Unsaved changes</span>
        ) : (
          <span className="mr-auto text-xs text-muted-foreground">Version {resume.current_version}</span>
        )}
        <Button type="button" variant="ghost" size="sm" onClick={() => reset(defaults)} disabled={!formState.isDirty}>
          Discard
        </Button>
        <Button type="submit" form={FORM_ID} size="sm" loading={saveParsed.isPending} disabled={!formState.isDirty}>
          Save as new version
        </Button>
      </CardFooter>
    </Card>
  )
}
