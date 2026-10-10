import {
  AlertTriangle,
  ArrowLeftRight,
  Bot,
  Briefcase,
  CheckCircle2,
  FileText,
  History,
  LogIn,
  Mail,
  PauseCircle,
  PlayCircle,
  Search,
  Send,
  Settings,
  Sparkles,
  SquarePen,
  StickyNote,
  User,
  type LucideIcon,
} from 'lucide-react'
import * as React from 'react'
import { Link } from 'react-router-dom'

import { EmptyState } from '@/components/common/EmptyState'
import { cn, formatDateTime, formatRelative, humanizeEnum, statusLabel } from '@/lib/utils'
import type { ActivityItem, ApplicationStatus } from '@/types/api'

/**
 * Audit rows the timeline hides by default.
 *
 * Every login and every per-job scoring pass is written to the audit log, and after a
 * seed or a sign-in they swamp everything a person actually wants to see. They stay one
 * click away rather than being dropped.
 */
const LOW_SIGNAL_ACTIONS = new Set(['auth.login', 'auth.refresh', 'auth.logout', 'job.analyzed', 'job.found'])

const EVENT_ICONS: Record<string, LucideIcon> = {
  CREATED: Briefcase,
  STATUS_CHANGED: ArrowLeftRight,
  AUTOMATION: Bot,
  ANSWERS_GENERATED: Sparkles,
  FORM_FILLED: SquarePen,
  PAUSED: PauseCircle,
  RESUMED: PlayCircle,
  APPROVED: CheckCircle2,
  SUBMITTED: Send,
  EMAIL_LINKED: Mail,
  NOTE: StickyNote,
  USER_ACTION: User,
  ERROR: AlertTriangle,
}

const AUDIT_PREFIX_ICONS: [string, LucideIcon][] = [
  ['auth.', LogIn],
  ['job.', Search],
  ['email.', Mail],
  ['application.', Briefcase],
  ['automation.', Bot],
  ['resume.', FileText],
  ['system.', Settings],
]

function iconFor(item: ActivityItem): LucideIcon {
  if (item.kind === 'EVENT') return EVENT_ICONS[item.action] ?? History
  const match = AUDIT_PREFIX_ICONS.find(([prefix]) => item.action.startsWith(prefix))
  return match?.[1] ?? History
}

function toneFor(item: ActivityItem): string {
  if (item.level === 'ERROR' || item.action === 'ERROR') return 'bg-destructive/10 text-destructive'
  if (item.level === 'WARN' || item.action === 'PAUSED') return 'bg-warning/15 text-warning'
  if (item.action === 'SUBMITTED' || item.action === 'APPROVED') return 'bg-success/10 text-success'
  if (item.kind === 'EVENT') return 'bg-primary/10 text-primary'
  return 'bg-muted text-muted-foreground'
}

/** `application.answers_generated` -> `Answers generated`. */
function titleFor(item: ActivityItem): string {
  if (item.kind === 'EVENT') {
    if (item.action === 'STATUS_CHANGED' && item.to_status) {
      const to = statusLabel(item.to_status as ApplicationStatus)
      const from = item.from_status ? statusLabel(item.from_status as ApplicationStatus) : null
      return from ? `${from} → ${to}` : `Status: ${to}`
    }
    return humanizeEnum(item.action)
  }
  const [, tail] = item.action.split('.')
  return humanizeEnum(tail ?? item.action)
}

export function filterActivity(items: ActivityItem[] | undefined, showAll: boolean): ActivityItem[] {
  if (!items) return []
  return showAll ? items : items.filter((item) => !LOW_SIGNAL_ACTIONS.has(item.action))
}

/**
 * The merged audit + application-event feed.
 *
 * One row per entry: what kind of thing happened (icon), what it was (title), the
 * server's own sentence, and when — relative, with the exact timestamp on hover. Rows
 * that carry a `link` become links to the application they belong to.
 */
export function ActivityTimeline({
  items,
  limit = 12,
  className,
}: {
  items: ActivityItem[]
  limit?: number
  className?: string
}) {
  const visible = React.useMemo(() => items.slice(0, limit), [items, limit])

  if (visible.length === 0) {
    return (
      <EmptyState
        size="sm"
        icon={History}
        title="No activity yet"
        description="Discovery, matching and submissions all show up here as they happen."
      />
    )
  }

  return (
    <ol className={cn('relative space-y-1', className)}>
      {visible.map((item, index) => {
        const Icon = iconFor(item)
        const isLast = index === visible.length - 1
        const body = (
          <>
            <div className="relative flex flex-col items-center">
              <span className={cn('flex size-8 shrink-0 items-center justify-center rounded-full', toneFor(item))}>
                <Icon className="size-4" aria-hidden />
              </span>
              {!isLast ? <span aria-hidden className="mt-1 w-px flex-1 bg-border" /> : null}
            </div>
            <div className="min-w-0 flex-1 pb-3">
              <div className="flex items-baseline justify-between gap-3">
                <p className="truncate text-sm font-medium">{titleFor(item)}</p>
                <time
                  className="shrink-0 text-xs text-muted-foreground"
                  dateTime={item.created_at}
                  title={formatDateTime(item.created_at)}
                >
                  {formatRelative(item.created_at)}
                </time>
              </div>
              {item.message ? <p className="line-clamp-2 text-sm text-muted-foreground">{item.message}</p> : null}
            </div>
          </>
        )

        return (
          <li key={item.id}>
            {item.link ? (
              <Link
                to={item.link}
                className="-mx-2 flex gap-3 rounded-md px-2 py-1 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {body}
              </Link>
            ) : (
              <div className="-mx-2 flex gap-3 px-2 py-1">{body}</div>
            )}
          </li>
        )
      })}
    </ol>
  )
}
