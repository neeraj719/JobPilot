import { ArrowDown, ArrowUp, Cpu, Plus, Sparkles, Trash2, Trophy, Wand2, WandSparkles } from 'lucide-react'
import * as React from 'react'
import { useFieldArray, useFormContext, type FieldArrayPath } from 'react-hook-form'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/api'
import { AiModelChip } from '@/features/ai-providers/components/AiModelChip'
import type { WorkflowTarget } from '@/features/ai-providers/types'
import { choiceShortLabel, choiceTarget, useAiChoice } from '@/features/ai-providers/useAiChoice'

import { useAchievementBullet, useImproveText, useRewriteBullet } from '../../api'
import type { EditorValues } from '../../schema'
import type { BulletCandidate } from '../../types'
import { SuggestionPanel } from './SuggestionPanel'

type BulletPath = `experience.${number}.bullets` | `projects.${number}.bullets` | 'achievements'
type Action = 'rewrite' | 'achievement' | 'improve'

const ACTION_TITLE: Record<Action, string> = {
  rewrite: 'Rewrite suggestions',
  achievement: 'Achievement-oriented version',
  improve: 'Improved wording',
}

interface PanelState {
  index: number
  action: Action
  original: string
  loading: boolean
  error: string | null
  candidates: BulletCandidate[]
  note: string | null
  /** The model picked for this run (kept for Retry). */
  ai?: WorkflowTarget
  model?: { provider: string | null; model: string | null }
}

export interface BulletListFieldProps {
  name: BulletPath
  resumeId: string
  label: string
  addLabel?: string
  context?: { role?: string | null; company?: string | null }
  onAiApplied: () => void
  placeholder?: string
}

/** Bullets as an editable list, each with Rewrite / Make achievement-oriented / Improve wording. */
export function BulletListField({ name, resumeId, label, addLabel = 'Add bullet', context, onAiApplied, placeholder }: BulletListFieldProps) {
  const { control, register, getValues, setValue } = useFormContext<EditorValues>()
  const { fields, append, remove, move } = useFieldArray({ control, name: name as FieldArrayPath<EditorValues> })
  const [panel, setPanel] = React.useState<PanelState | null>(null)
  const rewrite = useRewriteBullet(resumeId)
  const achievement = useAchievementBullet(resumeId)
  const improve = useImproveText(resumeId)
  const rewriteChoice = useAiChoice('rewrite_bullet')
  const improveChoice = useAiChoice('improve_grammar')

  const textAt = (index: number) => String(getValues(`${name}.${index}.text` as never) ?? '').trim()

  /** Asks "which model?" first when the user has 2+ usable models (and asked to be asked). */
  const run = (index: number, action: Action) => {
    if (textAt(index).length < 3) return
    const choice = action === 'improve' ? improveChoice : rewriteChoice
    void choice.runWithModel((ai) => execute(index, action, ai))
  }

  const execute = async (index: number, action: Action, ai?: WorkflowTarget) => {
    const original = textAt(index)
    if (original.length < 3) return
    setPanel({ index, action, original, loading: true, error: null, candidates: [], note: null, ai })
    try {
      if (action === 'improve') {
        const result = await improve.mutateAsync({ text: original, field: name === 'achievements' ? 'achievement' : 'bullet', ai })
        const candidates: BulletCandidate[] = result.changed
          ? [{ text: result.text, source: result.source, has_placeholder: false, checks: { kept_details: true, no_new_numbers: true, no_new_claims: true } }]
          : []
        setPanel({
          index,
          action,
          original,
          loading: false,
          error: null,
          candidates,
          ai,
          model: { provider: result.ai_provider ?? null, model: result.ai_model ?? null },
          note: result.changed
            ? result.reason
              ? 'The AI version added facts that are not in your text, so only grammar fixes are shown.'
              : null
            : 'Nothing to fix: the wording already reads well.',
        })
      } else {
        const result =
          action === 'rewrite'
            ? await rewrite.mutateAsync({ text: original, role: context?.role, company: context?.company, ai })
            : await achievement.mutateAsync({ text: original, ai })
        setPanel({
          index,
          action,
          original,
          loading: false,
          error: null,
          candidates: result.candidates,
          note: result.note,
          ai,
          model: { provider: result.ai_provider ?? null, model: result.ai_model ?? null },
        })
      }
    } catch (error) {
      setPanel({ index, action, original, loading: false, error: errorMessage(error), candidates: [], note: null, ai })
    }
  }

  const apply = (index: number, text: string, candidate: BulletCandidate) => {
    setValue(`${name}.${index}.text` as never, text as never, { shouldDirty: true, shouldTouch: true })
    if (candidate.source === 'ai') onAiApplied()
    setPanel(null)
    // Focus the bullet so a [result] placeholder can be replaced straight away.
    window.requestAnimationFrame(() => {
      const el = document.getElementById(`${name}-${index}`) as HTMLTextAreaElement | null
      if (!el) return
      el.focus()
      const at = text.indexOf('[')
      if (at >= 0) el.setSelectionRange(at, text.indexOf(']', at) + 1 || text.length)
    })
  }

  return (
    <fieldset className="space-y-2">
      <legend className="text-xs font-medium text-muted-foreground">{label}</legend>
      <ol className="space-y-2">
        {fields.map((field, index) => (
          <li key={field.id}>
            <div className="flex items-start gap-1.5">
              <span className="mt-2.5 select-none text-muted-foreground" aria-hidden>
                •
              </span>
              <Textarea
                id={`${name}-${index}`}
                rows={2}
                className="min-h-[2.5rem] flex-1 resize-y text-sm"
                aria-label={`${label} ${index + 1}`}
                placeholder={placeholder}
                {...register(`${name}.${index}.text` as never)}
              />
              <div className="flex shrink-0 flex-col gap-0.5">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button type="button" variant="ghost" size="icon-sm" aria-label={`AI help for ${label.toLowerCase()} ${index + 1}`}>
                      <Sparkles className="text-ai" aria-hidden />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-64">
                    <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
                      Suggestions never add numbers, tools or claims you have not written.
                    </DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    {name !== 'achievements' ? (
                      <>
                        <DropdownMenuItem onSelect={() => void run(index, 'rewrite')}>
                          <WandSparkles aria-hidden /> Rewrite
                        </DropdownMenuItem>
                        <DropdownMenuItem onSelect={() => void run(index, 'achievement')}>
                          <Trophy aria-hidden /> Make achievement-oriented
                        </DropdownMenuItem>
                        {rewriteChoice.canChoose ? (
                          <DropdownMenuSub>
                            <DropdownMenuSubTrigger>
                              <Cpu aria-hidden /> Rewrite once with…
                            </DropdownMenuSubTrigger>
                            <DropdownMenuSubContent className="w-64">
                              {(rewriteChoice.data?.candidates ?? []).map((candidate) => (
                                <DropdownMenuItem
                                  key={candidate.id}
                                  disabled={!candidate.available}
                                  onSelect={() => void execute(index, 'rewrite', choiceTarget(candidate))}
                                  className="flex-col items-start gap-0"
                                >
                                  <span className="text-sm">{candidate.label}</span>
                                  <span className="text-2xs text-muted-foreground">
                                    {candidate.available ? choiceShortLabel(candidate) : candidate.unavailable_reason}
                                  </span>
                                </DropdownMenuItem>
                              ))}
                            </DropdownMenuSubContent>
                          </DropdownMenuSub>
                        ) : null}
                      </>
                    ) : null}
                    <DropdownMenuItem onSelect={() => void run(index, 'improve')}>
                      <Wand2 aria-hidden /> Improve wording
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
                <div className="flex">
                  <Button type="button" variant="ghost" size="icon-sm" aria-label="Move up" disabled={index === 0} onClick={() => move(index, index - 1)}>
                    <ArrowUp aria-hidden />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Move down"
                    disabled={index === fields.length - 1}
                    onClick={() => move(index, index + 1)}
                  >
                    <ArrowDown aria-hidden />
                  </Button>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Delete ${label.toLowerCase()} ${index + 1}`}
                  onClick={() => {
                    if (panel?.index === index) setPanel(null)
                    remove(index)
                  }}
                >
                  <Trash2 aria-hidden />
                </Button>
              </div>
            </div>
            {panel && panel.index === index ? (
              <SuggestionPanel
                title={ACTION_TITLE[panel.action]}
                original={panel.original}
                loading={panel.loading}
                error={panel.error}
                candidates={panel.candidates}
                note={
                  panel.note ??
                  (panel.action === 'achievement'
                    ? 'Replace [result] with the real outcome. JobPilot never fills in a number for you.'
                    : null)
                }
                onApply={(text, candidate) => apply(index, text, candidate)}
                onClose={() => setPanel(null)}
                onRetry={() => void execute(index, panel.action, panel.ai)}
              />
            ) : null}
            {panel && panel.index === index && !panel.loading && panel.model ? (
              <AiModelChip provider={panel.model.provider} model={panel.model.model} prefix="Answered by" className="mt-1.5" />
            ) : null}
          </li>
        ))}
      </ol>
      <Button type="button" variant="outline" size="sm" onClick={() => append({ text: '' } as never)}>
        <Plus aria-hidden />
        {addLabel}
      </Button>
    </fieldset>
  )
}
