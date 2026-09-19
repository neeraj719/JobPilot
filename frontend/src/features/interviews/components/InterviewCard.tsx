import { CalendarClock, ExternalLink, MapPin, Sparkles, Timer, User, Video } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { INTERVIEW_TYPE_LABELS, cn } from '@/lib/utils'
import { formatApiDateTime, formatCountdown } from '@/features/automation/datetime'
import {
  INTERVIEW_STATUS_LABELS,
  hasPrep,
  interviewStatusBadgeClass,
  outcomeLabel,
} from '@/features/interviews/helpers'
import type { InterviewRead } from '@/types/api'

function isLink(value: string | null): value is string {
  return Boolean(value && /^https?:\/\//i.test(value))
}

export interface InterviewCardProps {
  interview: InterviewRead
  onOpen: (interview: InterviewRead) => void
  /** Upcoming cards get the countdown and a highlighted border. */
  highlight?: boolean
}

/** One interview round: company, role, type, when, where and who. */
export function InterviewCard({ interview, onOpen, highlight = false }: InterviewCardProps) {
  const countdown = highlight ? formatCountdown(interview.scheduled_at) : null
  const link = isLink(interview.location_or_link)
  const prepReady = hasPrep(interview)
  const outcome = outcomeLabel(interview.outcome)

  return (
    <Card
      className={cn(
        'transition-shadow hover:shadow-md',
        highlight && 'border-primary/30',
      )}
    >
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <button
            type="button"
            onClick={() => onOpen(interview)}
            className="min-w-0 flex-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            <p className="truncate text-sm font-semibold">{interview.company_name ?? 'Unknown company'}</p>
            <p className="truncate text-sm text-muted-foreground">{interview.job_title ?? 'Unknown role'}</p>
          </button>
          <span className={interviewStatusBadgeClass(interview.status, 'shrink-0')}>
            {INTERVIEW_STATUS_LABELS[interview.status]}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <span className="rounded-md border border-border bg-muted/60 px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
            {INTERVIEW_TYPE_LABELS[interview.interview_type]}
          </span>
          <span className="rounded-md border border-border bg-muted/60 px-1.5 py-0.5 text-[11px] text-muted-foreground">
            Round {interview.round_number}
          </span>
          {prepReady ? (
            <span className="inline-flex items-center gap-1 rounded-md border border-success/25 bg-success/10 px-1.5 py-0.5 text-[11px] font-medium text-success">
              <Sparkles className="size-2.5" aria-hidden />
              Prep ready
            </span>
          ) : null}
          {outcome ? (
            <span className="rounded-md border border-border bg-muted/60 px-1.5 py-0.5 text-[11px] text-muted-foreground">
              {outcome}
            </span>
          ) : null}
        </div>

        <dl className="space-y-1 text-sm">
          <div className="flex items-center gap-2">
            <CalendarClock className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
            <dt className="sr-only">When</dt>
            <dd className="min-w-0 truncate">
              {formatApiDateTime(interview.scheduled_at, 'Not scheduled yet')}
              {countdown ? <span className="ml-1.5 font-medium text-primary">{countdown}</span> : null}
            </dd>
          </div>
          {interview.duration_minutes ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Timer className="size-3.5 shrink-0" aria-hidden />
              <dt className="sr-only">Duration</dt>
              <dd>{interview.duration_minutes} minutes</dd>
            </div>
          ) : null}
          {interview.interviewer ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <User className="size-3.5 shrink-0" aria-hidden />
              <dt className="sr-only">Interviewer</dt>
              <dd className="min-w-0 truncate">{interview.interviewer}</dd>
            </div>
          ) : null}
          {interview.location_or_link && !link ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <MapPin className="size-3.5 shrink-0" aria-hidden />
              <dt className="sr-only">Location</dt>
              <dd className="min-w-0 truncate">{interview.location_or_link}</dd>
            </div>
          ) : null}
        </dl>

        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Button variant="outline" size="sm" onClick={() => onOpen(interview)}>
            {prepReady ? 'Open prep' : 'Details'}
          </Button>
          {link ? (
            <Button asChild variant="ghost" size="sm">
              <a href={interview.location_or_link ?? '#'} target="_blank" rel="noreferrer noopener">
                <Video />
                Join
              </a>
            </Button>
          ) : null}
          <Button asChild variant="ghost" size="sm" className="ml-auto">
            <Link to={`/applications/${interview.application_id}`}>
              <ExternalLink />
              Application
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
