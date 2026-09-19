import { CalendarClock, CheckCircle2, ExternalLink, Pencil, Timer, Trash2, User, Video, XCircle } from 'lucide-react'
import * as React from 'react'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { INTERVIEW_TYPE_LABELS } from '@/lib/utils'
import { formatApiDateTime, formatCountdown } from '@/features/automation/datetime'
import { InterviewPrepPanel } from '@/features/interviews/components/InterviewPrepPanel'
import {
  INTERVIEW_OUTCOMES,
  INTERVIEW_STATUS_LABELS,
  interviewStatusBadgeClass,
  isUpcoming,
  outcomeLabel,
} from '@/features/interviews/helpers'
import type { InterviewRead } from '@/types/api'

export interface InterviewDetailSheetProps {
  interview: InterviewRead | null
  open: boolean
  onOpenChange: (open: boolean) => void
  generating?: boolean
  updating?: boolean
  deleting?: boolean
  onGeneratePrep: (interview: InterviewRead) => void
  onEdit: (interview: InterviewRead) => void
  onComplete: (interview: InterviewRead, outcome: string) => void
  onCancel: (interview: InterviewRead) => void
  onDelete: (interview: InterviewRead) => void
}

/** Full detail for one round, with the preparation sheet and the lifecycle actions. */
export function InterviewDetailSheet({
  interview,
  open,
  onOpenChange,
  generating = false,
  updating = false,
  deleting = false,
  onGeneratePrep,
  onEdit,
  onComplete,
  onCancel,
  onDelete,
}: InterviewDetailSheetProps) {
  const [outcome, setOutcome] = React.useState<string>('PASSED')

  React.useEffect(() => {
    if (open) setOutcome(interview?.outcome ?? 'PASSED')
  }, [open, interview?.outcome])

  if (!interview) return null

  const link = interview.location_or_link && /^https?:\/\//i.test(interview.location_or_link)
  const countdown = isUpcoming(interview) ? formatCountdown(interview.scheduled_at) : null
  const recordedOutcome = outcomeLabel(interview.outcome)

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="flex w-full flex-col gap-0 overflow-y-auto p-0 sm:max-w-xl">
        <SheetHeader className="border-b border-border">
          <div className="flex flex-wrap items-center gap-2">
            <span className={interviewStatusBadgeClass(interview.status)}>
              {INTERVIEW_STATUS_LABELS[interview.status]}
            </span>
            <span className="rounded-md border border-border bg-muted/60 px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
              {INTERVIEW_TYPE_LABELS[interview.interview_type]}
            </span>
            <span className="rounded-md border border-border bg-muted/60 px-1.5 py-0.5 text-[11px] text-muted-foreground">
              Round {interview.round_number}
            </span>
            {recordedOutcome ? (
              <span className="rounded-md border border-border bg-muted/60 px-1.5 py-0.5 text-[11px] text-muted-foreground">
                {recordedOutcome}
              </span>
            ) : null}
          </div>
          <SheetTitle className="text-lg">{interview.company_name ?? 'Interview'}</SheetTitle>
          <SheetDescription>{interview.job_title ?? 'Unknown role'}</SheetDescription>
        </SheetHeader>

        <div className="space-y-5 p-6">
          <dl className="space-y-2 text-sm">
            <div className="flex items-start gap-2">
              <CalendarClock className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
              <dt className="sr-only">When</dt>
              <dd>
                {formatApiDateTime(interview.scheduled_at, 'Not scheduled yet')}
                {countdown ? <span className="ml-2 font-medium text-primary">{countdown}</span> : null}
              </dd>
            </div>
            {interview.duration_minutes ? (
              <div className="flex items-start gap-2 text-muted-foreground">
                <Timer className="mt-0.5 size-4 shrink-0" aria-hidden />
                <dt className="sr-only">Duration</dt>
                <dd>{interview.duration_minutes} minutes</dd>
              </div>
            ) : null}
            {interview.interviewer ? (
              <div className="flex items-start gap-2 text-muted-foreground">
                <User className="mt-0.5 size-4 shrink-0" aria-hidden />
                <dt className="sr-only">Interviewer</dt>
                <dd>{interview.interviewer}</dd>
              </div>
            ) : null}
            {interview.location_or_link ? (
              <div className="flex items-start gap-2 text-muted-foreground">
                <Video className="mt-0.5 size-4 shrink-0" aria-hidden />
                <dt className="sr-only">Where</dt>
                <dd className="min-w-0 break-words">
                  {link ? (
                    <a
                      href={interview.location_or_link}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="text-primary underline-offset-2 hover:underline"
                    >
                      {interview.location_or_link}
                    </a>
                  ) : (
                    interview.location_or_link
                  )}
                </dd>
              </div>
            ) : null}
          </dl>

          {interview.notes ? (
            <div className="rounded-lg border border-border bg-muted/30 p-3">
              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Notes</p>
              <p className="whitespace-pre-wrap text-sm">{interview.notes}</p>
            </div>
          ) : null}

          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => onEdit(interview)}>
              <Pencil />
              Edit
            </Button>
            {link ? (
              <Button asChild variant="outline" size="sm">
                <a href={interview.location_or_link ?? '#'} target="_blank" rel="noreferrer noopener">
                  <Video />
                  Join
                </a>
              </Button>
            ) : null}
            <Button asChild variant="ghost" size="sm">
              <Link to={`/applications/${interview.application_id}`}>
                <ExternalLink />
                Application
              </Link>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="ml-auto text-destructive hover:text-destructive"
              onClick={() => onDelete(interview)}
              loading={deleting}
            >
              <Trash2 />
              Delete
            </Button>
          </div>

          {interview.status !== 'COMPLETED' && interview.status !== 'CANCELLED' ? (
            <div className="space-y-2 rounded-lg border border-border p-3">
              <p className="text-sm font-medium">How did it go?</p>
              <div className="flex flex-wrap items-center gap-2">
                <Select value={outcome} onValueChange={setOutcome}>
                  <SelectTrigger className="h-9 min-w-[14rem] flex-1" aria-label="Interview outcome">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {INTERVIEW_OUTCOMES.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button size="sm" onClick={() => onComplete(interview, outcome)} loading={updating}>
                  <CheckCircle2 />
                  Mark completed
                </Button>
                <Button variant="ghost" size="sm" onClick={() => onCancel(interview)} disabled={updating}>
                  <XCircle />
                  Cancel round
                </Button>
              </div>
            </div>
          ) : null}

          <div className="space-y-2">
            <h3 className="text-sm font-semibold">Preparation</h3>
            <InterviewPrepPanel
              interview={interview}
              generating={generating}
              onGenerate={() => onGeneratePrep(interview)}
            />
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
