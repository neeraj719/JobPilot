import { ExternalLink, PlayCircle, ShieldAlert } from 'lucide-react'
import * as React from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { AnswerField } from '@/features/applications/components/AnswerField'
import { automationSummary, isManualStepPause } from '@/features/applications/components/AutomationBadge'
import { questionLabel } from '@/features/applications/labels'
import { canRememberAnswer } from '@/features/profile/standingAnswers'
import { cn } from '@/lib/utils'
import type { AnswerUpdate, ApplicationDetail } from '@/types/api'

export interface UserInputCardProps {
  application: ApplicationDetail
  onSaveAndContinue: (updates: AnswerUpdate[]) => Promise<void> | void
  onContinue: () => Promise<void> | void
  saving?: boolean
  resuming?: boolean
}

/**
 * Shown while the run is paused on the human: the questions the assistant refused to
 * guess, or a security step (CAPTCHA / OTP / sign-in) the user must complete themselves.
 *
 * JobPilot never works around a security check — it hands the user the page and waits.
 */
export function UserInputCard({
  application,
  onSaveAndContinue,
  onContinue,
  saving = false,
  resuming = false,
}: UserInputCardProps) {
  const pending = (application.answers ?? []).filter((answer) => answer.status === 'NEEDS_USER_INPUT')
  const [drafts, setDrafts] = React.useState<Record<string, string>>({})
  /** Answers to keep as standing answers ("Remember this answer"). */
  const [remember, setRemember] = React.useState<Record<string, boolean>>({})
  const summary = automationSummary(application)
  const manualStep = isManualStepPause(application.pause_reason)
  const applyUrl = application.job?.apply_url ?? application.external_url ?? application.job?.canonical_url ?? null

  const pendingKey = pending.map((answer) => answer.id).join('|')
  React.useEffect(() => {
    setDrafts((current) => {
      const next = { ...current }
      for (const answer of pending) {
        if (next[answer.id] === undefined) next[answer.id] = answer.answer ?? ''
      }
      return next
    })
    // Seed a draft for each newly surfaced question without clobbering typed text.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingKey])

  const allAnswered = pending.every((answer) => !answer.required || (drafts[answer.id] ?? '').trim().length > 0)

  async function handleSaveAndContinue() {
    const updates: AnswerUpdate[] = pending
      .filter((answer) => (drafts[answer.id] ?? '').trim().length > 0)
      .map((answer) => ({
        id: answer.id,
        answer: (drafts[answer.id] ?? '').trim(),
        ...(remember[answer.id] ? { save_as_standing: true } : {}),
      }))
    await onSaveAndContinue(updates)
  }

  return (
    <Card className={cn('border-warning/40 bg-warning/5')}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base text-warning">
          <ShieldAlert className="size-5" aria-hidden />
          {manualStep ? 'A step only you can complete' : 'Your input is required'}
        </CardTitle>
        <CardDescription className="text-foreground/80">{summary.detail}</CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {manualStep ? (
          <div className="space-y-3">
            <p className="text-sm leading-relaxed">
              The automation stopped at a security step — a CAPTCHA, a one-time code or a sign-in. JobPilot will not try
              to get around those checks. Open the application page, finish that step yourself, then come back and
              continue the run from where it paused.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              {applyUrl ? (
                <Button variant="outline" asChild>
                  <a href={applyUrl} target="_blank" rel="noreferrer noopener">
                    <ExternalLink />
                    Open application page
                  </a>
                </Button>
              ) : (
                <p className="text-sm text-muted-foreground">No application URL was recorded for this posting.</p>
              )}
              <Button onClick={() => void onContinue()} loading={resuming}>
                <PlayCircle />
                I have done it — continue
              </Button>
            </div>
          </div>
        ) : pending.length === 0 ? (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              No open questions are recorded. If you have resolved what paused the run, continue it below.
            </p>
            <Button onClick={() => void onContinue()} loading={resuming}>
              <PlayCircle />
              Continue automation
            </Button>
          </div>
        ) : (
          <>
            <ul className="space-y-4">
              {pending.map((answer) => (
                <li key={answer.id} className="space-y-2">
                  <Label htmlFor={`needs-${answer.id}`} className="flex flex-wrap items-center gap-1.5 text-sm">
                    {questionLabel(answer.question_text)}
                    {answer.required ? <span className="text-destructive">*</span> : null}
                  </Label>
                  {answer.rationale ? <p className="text-xs text-muted-foreground">{answer.rationale}</p> : null}
                  <AnswerField
                    id={`needs-${answer.id}`}
                    fieldType={answer.field_type}
                    options={(answer.options ?? []).map(String)}
                    value={drafts[answer.id] ?? ''}
                    onChange={(value) => setDrafts((current) => ({ ...current, [answer.id]: value }))}
                    disabled={saving || resuming}
                  />
                  {canRememberAnswer(answer.question_key, answer.field_type) ? (
                    <div className="flex items-center gap-2">
                      <Checkbox
                        id={`remember-${answer.id}`}
                        checked={Boolean(remember[answer.id])}
                        onCheckedChange={(checked) =>
                          setRemember((current) => ({ ...current, [answer.id]: checked === true }))
                        }
                        disabled={saving || resuming}
                      />
                      <Label htmlFor={`remember-${answer.id}`} className="text-xs font-normal text-muted-foreground">
                        Remember this answer for future applications
                      </Label>
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>

            <div className="flex flex-wrap items-center gap-2 border-t border-warning/25 pt-4">
              <Button onClick={() => void handleSaveAndContinue()} loading={saving || resuming} disabled={!allAnswered}>
                <PlayCircle />
                Save &amp; continue automation
              </Button>
              {!allAnswered ? (
                <span className="text-xs text-muted-foreground">Answer every required question to continue.</span>
              ) : null}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
