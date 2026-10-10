import { Info, Lock, MessageSquareText, Save, Sparkles } from 'lucide-react'
import * as React from 'react'

import { EmptyState } from '@/components/common/EmptyState'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { SimpleTooltip } from '@/components/ui/tooltip'
import { AnswerField } from '@/features/applications/components/AnswerField'
import { questionLabel } from '@/features/applications/labels'
import { ANSWER_STATUS_LABELS, answerStatusColor, cn, formatPercent, humanizeEnum } from '@/lib/utils'
import type { AnswerSource, AnswerUpdate, ApplicationAnswerRead } from '@/types/api'

export interface AnswersTabProps {
  answers: ApplicationAnswerRead[]
  onSave: (updates: AnswerUpdate[]) => Promise<void> | void
  onRegenerate: () => Promise<void> | void
  saving?: boolean
  regenerating?: boolean
  readOnly?: boolean
}

const SOURCE_LABELS: Record<AnswerSource, string> = {
  PROFILE: 'Profile',
  RESUME: 'Resume',
  PREFERENCE: 'Preference',
  AI_GENERATED: 'AI generated',
  USER: 'You',
  DEFAULT: 'Default',
}

const SOURCE_CLASSES: Record<AnswerSource, string> = {
  PROFILE: 'border-info/20 bg-info/10 text-info',
  RESUME: 'border-info/20 bg-info/10 text-info',
  PREFERENCE: 'border-border bg-muted text-muted-foreground',
  AI_GENERATED: 'border-primary/20 bg-primary/10 text-primary',
  USER: 'border-success/20 bg-success/10 text-success',
  DEFAULT: 'border-border bg-muted text-muted-foreground',
}

/** Full question-by-question view with inline editing and a regenerate action. */
export function AnswersTab({
  answers,
  onSave,
  onRegenerate,
  saving = false,
  regenerating = false,
  readOnly = false,
}: AnswersTabProps) {
  const [drafts, setDrafts] = React.useState<Record<string, string>>({})

  // Keep the draft in sync with the server copy for every answer the user has not touched.
  const signature = answers.map((answer) => `${answer.id}:${answer.answer ?? ''}`).join('|')
  React.useEffect(() => {
    setDrafts({})
  }, [signature])

  const dirty = answers.filter((answer) => drafts[answer.id] !== undefined && drafts[answer.id] !== (answer.answer ?? ''))

  async function handleSave() {
    const updates: AnswerUpdate[] = dirty.map((answer) => ({ id: answer.id, answer: drafts[answer.id] ?? '' }))
    if (updates.length === 0) return
    await onSave(updates)
  }

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 space-y-0">
        <CardTitle className="text-base">
          Answers
          <span className="ml-2 text-sm font-normal text-muted-foreground">{answers.length}</span>
        </CardTitle>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void onRegenerate()} loading={regenerating} disabled={readOnly}>
            <Sparkles />
            Regenerate answers
          </Button>
          <Button size="sm" onClick={handleSave} loading={saving} disabled={readOnly || dirty.length === 0}>
            <Save />
            Save{dirty.length > 0 ? ` (${dirty.length})` : ''}
          </Button>
        </div>
      </CardHeader>

      <CardContent>
        {answers.length === 0 ? (
          <EmptyState
            icon={MessageSquareText}
            size="sm"
            title="No answers prepared yet"
            description="Start the automation, or use “Regenerate answers” to have JobPilot fill the form from your profile and resume."
          />
        ) : (
          <ul className="divide-y divide-border">
            {answers.map((answer) => {
              const source = answer.answer_source
              return (
                <li key={answer.id} className="space-y-2 py-4 first:pt-0 last:pb-0">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <Label htmlFor={`answer-${answer.id}`} className="flex flex-wrap items-center gap-1.5 text-sm">
                      {questionLabel(answer.question_text)}
                      {answer.required ? <span className="text-destructive">*</span> : null}
                      {answer.is_sensitive ? (
                        <SimpleTooltip label="Sensitive — JobPilot never guesses this" side="top">
                          <Lock className="size-3 text-muted-foreground" aria-label="Sensitive question" />
                        </SimpleTooltip>
                      ) : null}
                    </Label>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="rounded-md border border-border bg-muted/60 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                        {humanizeEnum(answer.field_type)}
                      </span>
                      {source ? (
                        <span
                          className={cn(
                            'rounded-md border px-1.5 py-0.5 text-[10px] font-medium',
                            SOURCE_CLASSES[source],
                          )}
                        >
                          {SOURCE_LABELS[source]}
                        </span>
                      ) : null}
                      <span
                        className={cn(
                          'rounded-full border px-1.5 py-0.5 text-[10px] font-medium',
                          answerStatusColor(answer.status),
                        )}
                      >
                        {ANSWER_STATUS_LABELS[answer.status]}
                      </span>
                      {answer.confidence !== null && answer.confidence !== undefined ? (
                        <span className="text-[10px] tabular-nums text-muted-foreground">
                          {formatPercent(answer.confidence)} confident
                        </span>
                      ) : null}
                      {answer.rationale ? (
                        <SimpleTooltip label={answer.rationale} side="left">
                          <span className="inline-flex cursor-help text-muted-foreground">
                            <Info className="size-3.5" aria-label="Why this answer" />
                          </span>
                        </SimpleTooltip>
                      ) : null}
                    </div>
                  </div>

                  <AnswerField
                    id={`answer-${answer.id}`}
                    fieldType={answer.field_type}
                    options={(answer.options ?? []).map(String)}
                    value={drafts[answer.id] ?? answer.answer ?? ''}
                    onChange={(value) => setDrafts((current) => ({ ...current, [answer.id]: value }))}
                    disabled={readOnly || saving}
                  />

                  {answer.mapped_profile_field ? (
                    <p className="text-[11px] text-muted-foreground">Mapped from {answer.mapped_profile_field}</p>
                  ) : null}
                </li>
              )
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
