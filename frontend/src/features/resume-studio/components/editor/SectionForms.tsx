import { ArrowDown, ArrowUp, ChevronDown, ChevronRight, Plus, Sparkles, Trash2, Wand2 } from 'lucide-react'
import * as React from 'react'
import { Controller, useFieldArray, useFormContext, useWatch } from 'react-hook-form'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/api'
import { cn } from '@/lib/utils'

import { AiModelChip } from '@/features/ai-providers/components/AiModelChip'
import { AiRunButton } from '@/features/ai-providers/components/AiRunButton'
import type { WorkflowTarget } from '@/features/ai-providers/types'

import { useDraftSummary, useImproveText } from '../../api'
import { toStudioResume, type EditorValues } from '../../schema'
import type { BulletCandidate } from '../../types'
import { TagInput } from '../TagInput'
import { BulletListField } from './BulletListField'
import { SuggestionPanel } from './SuggestionPanel'

interface FieldProps {
  name: string
  label: string
  placeholder?: string
  className?: string
  hint?: string
  type?: string
}

function TextField({ name, label, placeholder, className, hint, type }: FieldProps) {
  const { register, getFieldState, formState } = useFormContext<EditorValues>()
  const state = getFieldState(name as never, formState) as { error?: { message?: string } }
  const id = `f-${name.replace(/\./g, '-')}`
  return (
    <div className={cn('space-y-1', className)}>
      <Label htmlFor={id} className="text-xs">
        {label}
      </Label>
      <Input id={id} type={type} placeholder={placeholder} aria-invalid={Boolean(state.error)} {...register(name as never)} className="h-9" />
      {state.error ? (
        <p className="text-xs text-destructive">{state.error.message}</p>
      ) : hint ? (
        <p className="text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  )
}

/* ------------------------------------------------------------------ header */

export function HeaderFields() {
  return (
    <div className="grid gap-3 2xl:grid-cols-2">
      <TextField name="name" label="Full name" placeholder="Your name" />
      <TextField name="headline" label="Headline" placeholder="e.g. Full Stack Developer" />
      <TextField name="email" label="Email" type="email" />
      <TextField name="phone" label="Phone" />
      <TextField name="location" label="Location" placeholder="City, Country" />
      <TextField name="total_experience_years" label="Years of experience" hint="Used by matching; not printed." />
      <TextField name="linkedin" label="LinkedIn URL" />
      <TextField name="github" label="GitHub URL" />
      <TextField name="portfolio" label="Portfolio / website" className="2xl:col-span-2" />
    </div>
  )
}

/* ------------------------------------------------------------------ summary */

interface TextPanel {
  title: string
  loading: boolean
  error: string | null
  candidates: BulletCandidate[]
  note: string | null
  original: string
  retry: () => void
  /** The model that answered (`ai_provider` / `ai_model`), when one did. */
  model?: { provider: string | null; model: string | null }
}

export function SummaryFields({ resumeId, onAiApplied }: { resumeId: string; onAiApplied: () => void }) {
  const { register, getValues, setValue } = useFormContext<EditorValues>()
  const draft = useDraftSummary(resumeId)
  const improve = useImproveText(resumeId)
  const [panel, setPanel] = React.useState<TextPanel | null>(null)

  const runDraft = async (ai?: WorkflowTarget) => {
    const original = getValues('summary').trim()
    const retry = () => void runDraft(ai)
    setPanel({ title: 'Summary from your facts', loading: true, error: null, candidates: [], note: null, original: original || '(empty)', retry })
    try {
      const result = await draft.mutateAsync({ parsed: toStudioResume(getValues()), ai })
      setPanel({
        title: 'Summary from your facts',
        loading: false,
        error: null,
        original: original || '(empty)',
        retry,
        model: { provider: result.ai_provider ?? null, model: result.ai_model ?? null },
        candidates: result.text
          ? [{ text: result.text, source: result.source, has_placeholder: false, checks: { kept_details: true, no_new_numbers: true, no_new_claims: true } }]
          : [],
        note: result.text
          ? 'Built only from your experience, skills and target role. Edit it to sound like you.'
          : 'Add a role with a title, or a few skills, first: the summary is built only from facts you entered.',
      })
    } catch (error) {
      setPanel({ title: 'Summary from your facts', loading: false, error: errorMessage(error), candidates: [], note: null, original, retry })
    }
  }

  const runImprove = async (ai?: WorkflowTarget) => {
    const original = getValues('summary').trim()
    if (!original) return
    const retry = () => void runImprove(ai)
    setPanel({ title: 'Improved wording', loading: true, error: null, candidates: [], note: null, original, retry })
    try {
      const result = await improve.mutateAsync({ text: original, field: 'summary', ai })
      setPanel({
        title: 'Improved wording',
        loading: false,
        error: null,
        original,
        retry,
        model: { provider: result.ai_provider ?? null, model: result.ai_model ?? null },
        candidates: result.changed
          ? [{ text: result.text, source: result.source, has_placeholder: false, checks: { kept_details: true, no_new_numbers: true, no_new_claims: true } }]
          : [],
        note: result.reason
          ? 'The AI version added facts that are not in your text, so only grammar fixes are shown.'
          : result.changed
            ? 'Grammar, clarity and tone only — the facts are unchanged.'
            : 'Nothing to fix.',
      })
    } catch (error) {
      setPanel({ title: 'Improved wording', loading: false, error: errorMessage(error), candidates: [], note: null, original, retry })
    }
  }

  return (
    <div className="space-y-2">
      <Label htmlFor="f-summary" className="text-xs">
        Summary
      </Label>
      <Textarea id="f-summary" rows={5} placeholder="2–3 sentences: your role, experience and strongest skills." {...register('summary')} />
      <div className="flex flex-wrap items-start gap-2">
        <AiRunButton task="draft_summary" type="button" variant="outline" size="sm" onRun={(ai) => runDraft(ai)}>
          <Sparkles aria-hidden /> Draft from my facts
        </AiRunButton>
        <AiRunButton task="improve_grammar" type="button" variant="outline" size="sm" showModel={false} onRun={(ai) => runImprove(ai)}>
          <Wand2 aria-hidden /> Improve wording
        </AiRunButton>
      </div>
      {panel?.model && !panel.loading ? <AiModelChip provider={panel.model.provider} model={panel.model.model} prefix="Answered by" /> : null}
      {panel ? (
        <SuggestionPanel
          title={panel.title}
          original={panel.original}
          loading={panel.loading}
          error={panel.error}
          candidates={panel.candidates}
          note={panel.note}
          onApply={(text, candidate) => {
            setValue('summary', text, { shouldDirty: true })
            if (candidate.source === 'ai') onAiApplied()
            setPanel(null)
          }}
          onClose={() => setPanel(null)}
          onRetry={panel.retry}
        />
      ) : null}
    </div>
  )
}

/* ------------------------------------------------------------------ tags */

export function TagsField({ name, label, placeholder }: { name: 'skills' | 'languages'; label: string; placeholder: string }) {
  const { control } = useFormContext<EditorValues>()
  return (
    <div className="space-y-1">
      <Label className="text-xs" htmlFor={`f-${name}`}>
        {label}
      </Label>
      <Controller
        control={control}
        name={name}
        render={({ field }) => (
          <TagInput id={`f-${name}`} label={label} value={field.value} onChange={field.onChange} placeholder={placeholder} />
        )}
      />
    </div>
  )
}

/* ------------------------------------------------------------------ entries */

function EntryShell({
  title,
  subtitle,
  index,
  count,
  onMove,
  onRemove,
  children,
  defaultOpen,
}: {
  title: string
  subtitle?: string
  index: number
  count: number
  onMove: (to: number) => void
  onRemove: () => void
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = React.useState(Boolean(defaultOpen))
  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="flex items-center gap-1 p-2">
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-1 py-1 text-left hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <ChevronDown className="size-4 shrink-0" aria-hidden /> : <ChevronRight className="size-4 shrink-0" aria-hidden />}
          <span className="min-w-0">
            <span className="block truncate text-sm font-medium">{title}</span>
            {subtitle ? <span className="block truncate text-xs text-muted-foreground">{subtitle}</span> : null}
          </span>
        </button>
        <Button type="button" variant="ghost" size="icon-sm" aria-label="Move up" disabled={index === 0} onClick={() => onMove(index - 1)}>
          <ArrowUp aria-hidden />
        </Button>
        <Button type="button" variant="ghost" size="icon-sm" aria-label="Move down" disabled={index === count - 1} onClick={() => onMove(index + 1)}>
          <ArrowDown aria-hidden />
        </Button>
        <Button type="button" variant="ghost" size="icon-sm" aria-label={`Delete ${title}`} onClick={onRemove}>
          <Trash2 aria-hidden />
        </Button>
      </div>
      {open ? <div className="space-y-3 border-t border-border p-3">{children}</div> : null}
    </div>
  )
}

export function ExperienceFields({ resumeId, onAiApplied }: { resumeId: string; onAiApplied: () => void }) {
  const { control } = useFormContext<EditorValues>()
  const { fields, append, remove, move } = useFieldArray({ control, name: 'experience' })
  const values = useWatch({ control, name: 'experience' })
  return (
    <div className="space-y-2">
      {fields.map((field, index) => {
        const entry = values?.[index]
        const title = [entry?.title, entry?.company].filter(Boolean).join(' at ') || 'New role'
        const dates = [entry?.start, entry?.end].filter(Boolean).join(' – ')
        return (
          <EntryShell
            key={field.id}
            title={title}
            subtitle={dates}
            index={index}
            count={fields.length}
            onMove={(to) => move(index, to)}
            onRemove={() => remove(index)}
            defaultOpen={fields.length === 1 || !entry?.company}
          >
            <div className="grid gap-3 2xl:grid-cols-2">
              <TextField name={`experience.${index}.title`} label="Job title" />
              <TextField name={`experience.${index}.company`} label="Company" />
              <TextField name={`experience.${index}.start`} label="Start" placeholder="2023-03 or Mar 2023" />
              <TextField name={`experience.${index}.end`} label="End" placeholder="Present" />
              <TextField name={`experience.${index}.location`} label="Location" className="2xl:col-span-2" />
            </div>
            <BulletListField
              name={`experience.${index}.bullets`}
              resumeId={resumeId}
              label="Bullet"
              context={{ role: entry?.title, company: entry?.company }}
              onAiApplied={onAiApplied}
              placeholder="What you did, with which tools, and the result"
            />
            <EntryTags name={`experience.${index}.technologies`} />
          </EntryShell>
        )
      })}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => append({ company: '', title: '', start: '', end: '', location: '', url: '', bullets: [{ text: '' }], technologies: [] })}
      >
        <Plus aria-hidden /> Add role
      </Button>
    </div>
  )
}

function EntryTags({ name }: { name: `experience.${number}.technologies` | `projects.${number}.technologies` }) {
  const { control } = useFormContext<EditorValues>()
  return (
    <div className="space-y-1">
      <Label className="text-xs">Technologies</Label>
      <Controller
        control={control}
        name={name}
        render={({ field }) => (
          <TagInput label="Technologies" value={field.value ?? []} onChange={field.onChange} placeholder="Type and press Enter" />
        )}
      />
    </div>
  )
}

export function ProjectFields({ resumeId, onAiApplied }: { resumeId: string; onAiApplied: () => void }) {
  const { control } = useFormContext<EditorValues>()
  const { fields, append, remove, move } = useFieldArray({ control, name: 'projects' })
  const values = useWatch({ control, name: 'projects' })
  return (
    <div className="space-y-2">
      {fields.map((field, index) => (
        <EntryShell
          key={field.id}
          title={values?.[index]?.name || 'New project'}
          index={index}
          count={fields.length}
          onMove={(to) => move(index, to)}
          onRemove={() => remove(index)}
          defaultOpen={!values?.[index]?.name}
        >
          <div className="grid gap-3 2xl:grid-cols-2">
            <TextField name={`projects.${index}.name`} label="Project name" />
            <TextField name={`projects.${index}.url`} label="Link" />
          </div>
          <BulletListField name={`projects.${index}.bullets`} resumeId={resumeId} label="Bullet" onAiApplied={onAiApplied} />
          <EntryTags name={`projects.${index}.technologies`} />
        </EntryShell>
      ))}
      <Button type="button" variant="outline" size="sm" onClick={() => append({ name: '', url: '', bullets: [{ text: '' }], technologies: [] })}>
        <Plus aria-hidden /> Add project
      </Button>
    </div>
  )
}

export function EducationFields() {
  const { control } = useFormContext<EditorValues>()
  const { fields, append, remove, move } = useFieldArray({ control, name: 'education' })
  const values = useWatch({ control, name: 'education' })
  return (
    <div className="space-y-2">
      {fields.map((field, index) => (
        <EntryShell
          key={field.id}
          title={[values?.[index]?.degree, values?.[index]?.institution].filter(Boolean).join(' – ') || 'New education'}
          index={index}
          count={fields.length}
          onMove={(to) => move(index, to)}
          onRemove={() => remove(index)}
          defaultOpen={!values?.[index]?.institution}
        >
          <div className="grid gap-3 2xl:grid-cols-2">
            <TextField name={`education.${index}.institution`} label="School / university" className="2xl:col-span-2" />
            <TextField name={`education.${index}.degree`} label="Degree" />
            <TextField name={`education.${index}.field`} label="Field of study" />
            <TextField name={`education.${index}.start`} label="Start" />
            <TextField name={`education.${index}.end`} label="End" />
          </div>
        </EntryShell>
      ))}
      <Button type="button" variant="outline" size="sm" onClick={() => append({ institution: '', degree: '', field: '', start: '', end: '' })}>
        <Plus aria-hidden /> Add education
      </Button>
    </div>
  )
}

export function CertificationFields() {
  const { control } = useFormContext<EditorValues>()
  const { fields, append, remove } = useFieldArray({ control, name: 'certifications' })
  return (
    <div className="space-y-2">
      {fields.map((field, index) => (
        <div key={field.id} className="flex items-end gap-2 rounded-lg border border-border p-2">
          <div className="grid flex-1 gap-2 2xl:grid-cols-[2fr_1.5fr_0.7fr]">
            <TextField name={`certifications.${index}.name`} label="Certification" />
            <TextField name={`certifications.${index}.issuer`} label="Issuer" />
            <TextField name={`certifications.${index}.year`} label="Year" />
          </div>
          <Button type="button" variant="ghost" size="icon-sm" aria-label="Delete certification" onClick={() => remove(index)}>
            <Trash2 aria-hidden />
          </Button>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" onClick={() => append({ name: '', issuer: '', year: '' })}>
        <Plus aria-hidden /> Add certification
      </Button>
    </div>
  )
}

export function AchievementFields({ resumeId, onAiApplied }: { resumeId: string; onAiApplied: () => void }) {
  return (
    <BulletListField
      name="achievements"
      resumeId={resumeId}
      label="Achievement"
      addLabel="Add achievement"
      onAiApplied={onAiApplied}
      placeholder="An award, a result or recognition you can back up"
    />
  )
}
