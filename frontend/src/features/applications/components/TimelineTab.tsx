import {
  AlertTriangle,
  Bot,
  CalendarClock,
  CheckCircle2,
  CircleDot,
  FileText,
  Mail,
  MessageSquare,
  PauseCircle,
  PlayCircle,
  Send,
  Sparkles,
  StickyNote,
  UserCheck,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import { EmptyState } from '@/components/common/EmptyState'
import { StatusBadge } from '@/components/common/StatusBadge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { TimelineSkeleton } from '@/features/applications/components/ApplicationSkeletons'
import {
  EMAIL_CLASSIFICATION_LABELS,
  INTERVIEW_TYPE_LABELS,
  cn,
  emailClassificationColor,
  formatDateTime,
  formatRelative,
  humanizeEnum,
} from '@/lib/utils'
import type {
  ApplicationEventRead,
  ApplicationEventType,
  EmailMessageRead,
  InterviewRead,
} from '@/types/api'

const EVENT_ICONS: Record<ApplicationEventType, LucideIcon> = {
  CREATED: CircleDot,
  STATUS_CHANGED: CheckCircle2,
  AUTOMATION: Bot,
  ANSWERS_GENERATED: Sparkles,
  FORM_FILLED: FileText,
  PAUSED: PauseCircle,
  RESUMED: PlayCircle,
  APPROVED: UserCheck,
  SUBMITTED: Send,
  EMAIL_LINKED: Mail,
  NOTE: StickyNote,
  USER_ACTION: MessageSquare,
  ERROR: AlertTriangle,
}

const EVENT_TONES: Partial<Record<ApplicationEventType, string>> = {
  ERROR: 'border-destructive/30 bg-destructive/10 text-destructive',
  PAUSED: 'border-warning/30 bg-warning/10 text-warning',
  SUBMITTED: 'border-success/30 bg-success/10 text-success',
  APPROVED: 'border-success/30 bg-success/10 text-success',
}

export interface TimelineTabProps {
  events: ApplicationEventRead[] | undefined
  emails: EmailMessageRead[]
  interviews: InterviewRead[]
  loading?: boolean
}

function EventRow({ event }: { event: ApplicationEventRead }) {
  const Icon = EVENT_ICONS[event.event_type] ?? CircleDot
  return (
    <li className="relative flex gap-3 pb-5 last:pb-0">
      <span
        className={cn(
          'z-10 flex size-7 shrink-0 items-center justify-center rounded-full border bg-card',
          EVENT_TONES[event.event_type] ?? 'border-border text-muted-foreground',
        )}
      >
        <Icon className="size-3.5" aria-hidden />
      </span>
      <div className="min-w-0 flex-1 space-y-1 pt-0.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">{humanizeEnum(event.event_type)}</span>
          <span className="rounded-md border border-border bg-muted/60 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            {humanizeEnum(event.actor)}
          </span>
          <span className="text-xs text-muted-foreground" title={formatDateTime(event.created_at)}>
            {formatRelative(event.created_at)}
          </span>
        </div>
        {event.message ? <p className="break-words text-sm text-muted-foreground">{event.message}</p> : null}
        {event.from_status || event.to_status ? (
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            {event.from_status ? <StatusBadge status={event.from_status} /> : null}
            {event.from_status && event.to_status ? <span className="text-muted-foreground">→</span> : null}
            {event.to_status ? <StatusBadge status={event.to_status} /> : null}
          </div>
        ) : null}
      </div>
    </li>
  )
}

/** Events, linked emails and interviews for one application, newest last. */
export function TimelineTab({ events, emails, interviews, loading = false }: TimelineTabProps) {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Activity</CardTitle>
        </CardHeader>
        <CardContent>
          {loading && !events ? (
            <TimelineSkeleton rows={4} />
          ) : !events || events.length === 0 ? (
            <EmptyState size="sm" icon={CircleDot} title="No activity recorded yet" />
          ) : (
            <ol className="relative">
              <span className="absolute left-3.5 top-2 h-[calc(100%-1rem)] w-px bg-border" aria-hidden />
              {events.map((event) => (
                <EventRow key={event.id} event={event} />
              ))}
            </ol>
          )}
        </CardContent>
      </Card>

      {emails.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Linked emails</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="divide-y divide-border">
              {emails.map((email) => (
                <li key={email.id} className="flex flex-wrap items-start justify-between gap-2 py-3 first:pt-0 last:pb-0">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{email.subject}</p>
                    <p className="truncate text-xs text-muted-foreground">{email.sender}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span
                      className={cn(
                        'rounded-full border px-2 py-0.5 text-[10px] font-medium',
                        emailClassificationColor(email.classification),
                      )}
                    >
                      {EMAIL_CLASSIFICATION_LABELS[email.classification]}
                    </span>
                    <span className="text-xs text-muted-foreground" title={formatDateTime(email.received_at)}>
                      {formatRelative(email.received_at)}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      {interviews.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Interviews</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="divide-y divide-border">
              {interviews.map((interview) => (
                <li key={interview.id} className="flex flex-wrap items-center justify-between gap-2 py-3 first:pt-0 last:pb-0">
                  <div className="flex min-w-0 items-center gap-2">
                    <CalendarClock className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">
                        {INTERVIEW_TYPE_LABELS[interview.interview_type]} · Round {interview.round_number}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {interview.scheduled_at ? formatDateTime(interview.scheduled_at) : 'Not scheduled'}
                        {interview.interviewer ? ` · ${interview.interviewer}` : ''}
                      </p>
                    </div>
                  </div>
                  <span className="rounded-full border border-border bg-muted/60 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                    {humanizeEnum(interview.status)}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
