import { AlertCircle, CheckCircle2, Lock, Pencil, Send, ShieldQuestion, X } from 'lucide-react'
import * as React from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { AnswerField } from '@/features/applications/components/AnswerField'
import { questionLabel } from '@/features/applications/labels'
import { ANSWER_STATUS_LABELS, answerStatusColor, cn, formatCurrency, humanizeEnum } from '@/lib/utils'
import type { ApplicationAnswerRead, ApplicationDetail, AnswerUpdate, ReviewField } from '@/types/api'

export interface ReviewPanelProps {
  application: ApplicationDetail
  editing: boolean
  onToggleEdit: () => void
  onSaveEdits: (updates: AnswerUpdate[]) => Promise<void> | void
  onApprove: () => void
  onSkip: () => void
  saving?: boolean
  approving?: boolean
}

/** Uploaded files are stored as absolute server paths — show only the file name. */
function displayValue(value: string | null): string {
  if (!value) return ''
  const looksLikePath = /^[A-Za-z]:[\\/]/.test(value) || value.includes('\\')
  if (!looksLikePath) return value
  return value.split(/[\\/]/).pop() || value
}

/** `1200000` -> `₹12.0 LPA`; anything non-numeric is passed through. */
function displaySalary(value: string | null | undefined): string {
  if (!value) return '—'
  const amount = Number(value.replace(/[^0-9.]/g, ''))
  return Number.isFinite(amount) && amount > 0 ? formatCurrency(amount) : value
}

function FieldRow({ field }: { field: ReviewField }) {
  return (
    <div className="flex flex-col gap-1 py-2.5 sm:flex-row sm:items-start sm:gap-4">
      <div className="flex min-w-0 items-center gap-1.5 sm:w-2/5">
        <span className="truncate text-sm font-medium" title={field.label}>
          {questionLabel(field.label)}
        </span>
        {field.required ? <span className="text-destructive">*</span> : null}
        {field.is_sensitive ? <Lock className="size-3 shrink-0 text-muted-foreground" aria-label="Sensitive" /> : null}
      </div>
      <div className="min-w-0 flex-1">
        <p
          className={cn('break-words text-sm', field.value ? '' : 'italic text-muted-foreground')}
          title={field.value ?? undefined}
        >
          {displayValue(field.value) || 'Not answered'}
        </p>
        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          <span
            className={cn(
              'inline-flex items-center rounded-full border px-1.5 py-0.5 text-[10px] font-medium',
              answerStatusColor(field.status),
            )}
          >
            {ANSWER_STATUS_LABELS[field.status]}
          </span>
          {field.source ? (
            <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
              {humanizeEnum(field.source)}
            </span>
          ) : null}
        </div>
      </div>
    </div>
  )
}

/**
 * The Approval Center's main panel: what will be sent, what is missing, and the three
 * decisions a human can take (approve, edit, skip).
 */
export function ReviewPanel({
  application,
  editing,
  onToggleEdit,
  onSaveEdits,
  onApprove,
  onSkip,
  saving = false,
  approving = false,
}: ReviewPanelProps) {
  const review = application.review
  const answers = application.answers ?? []
  const [drafts, setDrafts] = React.useState<Record<string, string>>({})

  React.useEffect(() => {
    if (!editing) return
    const next: Record<string, string> = {}
    for (const answer of answers) next[answer.id] = answer.answer ?? ''
    setDrafts(next)
    // Reset the draft whenever edit mode opens; `answers` identity changes on every poll.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing])

  const fields = review?.fields ?? []
  const missing = review?.missing ?? []
  const blockers = review?.blockers ?? []
  const sensitive = review?.sensitive ?? []
  const canSubmit = Boolean(review?.can_submit)

  function changed(answer: ApplicationAnswerRead): boolean {
    const draft = drafts[answer.id]
    return draft !== undefined && draft !== (answer.answer ?? '')
  }

  async function handleSave() {
    const updates: AnswerUpdate[] = answers
      .filter(changed)
      .map((answer) => ({ id: answer.id, answer: drafts[answer.id] ?? '' }))
    await onSaveEdits(updates)
  }

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 space-y-0">
        <CardTitle className="text-base">Review before submitting</CardTitle>
        <div className="flex items-center gap-2">
          {editing ? (
            <>
              <Button variant="ghost" size="sm" onClick={onToggleEdit} disabled={saving}>
                Cancel
              </Button>
              <Button size="sm" onClick={handleSave} loading={saving}>
                Save answers
              </Button>
            </>
          ) : (
            <Button variant="outline" size="sm" onClick={onToggleEdit} disabled={answers.length === 0}>
              <Pencil />
              Edit
            </Button>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <dt className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Company</dt>
            <dd className="text-sm font-medium">{review?.company || application.company_name || '—'}</dd>
          </div>
          <div>
            <dt className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Job</dt>
            <dd className="text-sm font-medium">{review?.job_title || application.job_title || '—'}</dd>
          </div>
          <div>
            <dt className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Resume</dt>
            <dd className="text-sm font-medium">{review?.resume_name || '—'}</dd>
          </div>
          <div>
            <dt className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Salary expectation</dt>
            <dd className="text-sm font-medium">{displaySalary(review?.salary_expectation)}</dd>
          </div>
          <div>
            <dt className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Location</dt>
            <dd className="text-sm font-medium">{review?.location || '—'}</dd>
          </div>
        </dl>

        <section className="space-y-1">
          <h3 className="text-sm font-semibold">Application fields</h3>
          {editing ? (
            answers.length === 0 ? (
              <p className="text-sm text-muted-foreground">No answers have been prepared yet.</p>
            ) : (
              <div className="divide-y divide-border">
                {answers.map((answer) => (
                  <div key={answer.id} className="space-y-2 py-3">
                    <Label htmlFor={`edit-${answer.id}`} className="flex items-center gap-1.5 text-sm">
                      {questionLabel(answer.question_text)}
                      {answer.required ? <span className="text-destructive">*</span> : null}
                      {answer.is_sensitive ? (
                        <Lock className="size-3 text-muted-foreground" aria-label="Sensitive" />
                      ) : null}
                    </Label>
                    <AnswerField
                      id={`edit-${answer.id}`}
                      fieldType={answer.field_type}
                      options={(answer.options ?? []).map(String)}
                      value={drafts[answer.id] ?? ''}
                      onChange={(value) => setDrafts((current) => ({ ...current, [answer.id]: value }))}
                      disabled={saving}
                    />
                  </div>
                ))}
              </div>
            )
          ) : fields.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nothing has been prepared yet. Start the automation to fill this application.
            </p>
          ) : (
            <div className="divide-y divide-border">
              {fields.map((field) => (
                <FieldRow key={field.key} field={field} />
              ))}
            </div>
          )}
        </section>

        {missing.length > 0 ? (
          <section className="rounded-lg border border-warning/25 bg-warning/5 p-3">
            <h3 className="flex items-center gap-1.5 text-sm font-semibold text-warning">
              <AlertCircle className="size-4" aria-hidden />
              Potential missing information
            </h3>
            <ul className="mt-1.5 list-inside list-disc space-y-0.5 text-sm text-muted-foreground">
              {missing.map((item) => (
                <li key={item}>{questionLabel(item, item)}</li>
              ))}
            </ul>
          </section>
        ) : null}

        {sensitive.length > 0 ? (
          <section className="rounded-lg border border-border bg-muted/40 p-3">
            <h3 className="flex items-center gap-1.5 text-sm font-semibold">
              <ShieldQuestion className="size-4 text-muted-foreground" aria-hidden />
              Sensitive questions — please double-check these yourself
            </h3>
            <ul className="mt-1.5 list-inside list-disc space-y-0.5 text-sm text-muted-foreground">
              {sensitive.map((item) => (
                <li key={item}>{questionLabel(item, item)}</li>
              ))}
            </ul>
          </section>
        ) : null}

        {blockers.length > 0 ? (
          <section className="rounded-lg border border-destructive/25 bg-destructive/5 p-3">
            <h3 className="flex items-center gap-1.5 text-sm font-semibold text-destructive">
              <AlertCircle className="size-4" aria-hidden />
              Blocking this submission
            </h3>
            <ul className="mt-1.5 list-inside list-disc space-y-0.5 text-sm text-destructive/90">
              {blockers.map((item) => (
                <li key={item}>{questionLabel(item, item)}</li>
              ))}
            </ul>
          </section>
        ) : null}

        <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
          <Button onClick={onApprove} disabled={!canSubmit || editing} loading={approving}>
            <Send />
            Approve &amp; submit
          </Button>
          <Button variant="ghost" onClick={onSkip} disabled={approving}>
            <X />
            Skip this application
          </Button>
          {canSubmit ? (
            <span className="inline-flex items-center gap-1 text-xs text-success">
              <CheckCircle2 className="size-3.5" aria-hidden />
              Everything required is answered.
            </span>
          ) : (
            <span className="text-xs text-muted-foreground">
              Submission stays disabled until every blocker above is resolved.
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
