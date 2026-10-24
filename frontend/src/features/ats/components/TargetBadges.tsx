import { differenceInCalendarDays } from 'date-fns'
import { BellRing, CalendarClock } from 'lucide-react'

import { cn, formatDate, toDate } from '@/lib/utils'
import { TARGET_STATUS_CLASSES, TARGET_STATUS_LABELS } from '@/features/ats/labels'
import type { JobTarget, JobTargetStatus } from '@/features/ats/types'

export function TargetStatusBadge({ status, className }: { status: JobTargetStatus; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium',
        TARGET_STATUS_CLASSES[status],
        className,
      )}
    >
      {/* Status dot + label (colour is never the only cue). */}
      <span className="size-1.5 shrink-0 rounded-full bg-current opacity-80" aria-hidden />
      {TARGET_STATUS_LABELS[status]}
    </span>
  )
}

const CLOSED: JobTargetStatus[] = ['REJECTED', 'ARCHIVED', 'OFFER']

/** Deadline and follow-up reminders that matter now (within a week, or overdue). */
export function TargetDueBadges({ target }: { target: Pick<JobTarget, 'deadline' | 'follow_up_at' | 'status'> }) {
  if (CLOSED.includes(target.status)) return null
  const today = new Date()
  const badges: { key: string; text: string; tone: 'warn' | 'late' | 'info'; icon: typeof BellRing; title: string }[] = []
  const deadline = toDate(target.deadline)
  if (deadline && !['APPLIED', 'INTERVIEW'].includes(target.status)) {
    const days = differenceInCalendarDays(deadline, today)
    if (days < 0) badges.push({ key: 'deadline', text: 'Deadline passed', tone: 'late', icon: CalendarClock, title: formatDate(deadline) })
    else if (days <= 7) badges.push({ key: 'deadline', text: days === 0 ? 'Due today' : `Due in ${days}d`, tone: 'warn', icon: CalendarClock, title: formatDate(deadline) })
  }
  const follow = toDate(target.follow_up_at)
  if (follow) {
    const days = differenceInCalendarDays(follow, today)
    if (days < 0) badges.push({ key: 'follow', text: 'Follow-up overdue', tone: 'late', icon: BellRing, title: formatDate(follow) })
    else if (days <= 3) badges.push({ key: 'follow', text: days === 0 ? 'Follow up today' : `Follow up in ${days}d`, tone: 'info', icon: BellRing, title: formatDate(follow) })
  }
  if (badges.length === 0) return null
  return (
    <>
      {badges.map(({ key, text, tone, icon: Icon, title }) => (
        <span
          key={key}
          title={title}
          className={cn(
            'inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium',
            tone === 'late'
              ? 'bg-destructive-soft text-destructive-soft-foreground'
              : tone === 'warn'
                ? 'bg-warning-soft text-warning-soft-foreground'
                : 'bg-info-soft text-info-soft-foreground',
          )}
        >
          <Icon className="size-3" aria-hidden />
          {text}
        </span>
      ))}
    </>
  )
}
