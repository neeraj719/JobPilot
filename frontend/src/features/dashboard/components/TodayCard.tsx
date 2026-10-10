import { Link } from 'react-router-dom'
import type { LucideIcon } from 'lucide-react'
import { Briefcase, CalendarCheck, Inbox, MailOpen, Search, XCircle } from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn, formatNumber } from '@/lib/utils'
import type { DashboardPeriodStats } from '@/types/api'

interface TodayRow {
  key: keyof DashboardPeriodStats
  label: string
  icon: LucideIcon
  to?: string
  /** Muted when zero so the numbers that did move stand out. */
  emphasis?: 'good' | 'bad'
}

const ROWS: TodayRow[] = [
  { key: 'applications', label: 'Applications', icon: Briefcase, to: '/applications' },
  { key: 'responses', label: 'Responses', icon: MailOpen, to: '/emails', emphasis: 'good' },
  { key: 'interviews', label: 'Interviews', icon: CalendarCheck, to: '/interviews', emphasis: 'good' },
  { key: 'rejections', label: 'Rejections', icon: XCircle, emphasis: 'bad' },
  { key: 'pending', label: 'Pending', icon: Inbox, to: '/queue' },
  { key: 'jobs_found', label: 'Jobs found', icon: Search, to: '/jobs' },
]

/**
 * The spec's "Today" card: six counters, one line each, in a fixed order so the shape
 * of the card is the same every morning and the eye goes straight to what changed.
 */
export function TodayCard({
  stats,
  title = 'Today',
  description,
  className,
}: {
  stats: DashboardPeriodStats
  title?: string
  description?: string
  className?: string
}) {
  return (
    <Card className={cn('flex min-w-0 flex-col', className)}>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent className="flex-1">
        <dl className="divide-y divide-border">
          {ROWS.map((row) => {
            const value = stats[row.key] ?? 0
            const Icon = row.icon
            const content = (
              <>
                <dt className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Icon className="size-4 shrink-0" aria-hidden />
                  {row.label}
                </dt>
                <dd
                  className={cn(
                    'text-sm font-semibold tabular-nums',
                    value === 0 && 'text-muted-foreground',
                    value > 0 && row.emphasis === 'good' && 'text-success',
                    value > 0 && row.emphasis === 'bad' && 'text-destructive',
                  )}
                >
                  {formatNumber(value)}
                </dd>
              </>
            )
            return row.to ? (
              <Link
                key={row.key}
                to={row.to}
                className="-mx-2 flex items-center justify-between rounded-md px-2 py-2.5 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {content}
              </Link>
            ) : (
              <div key={row.key} className="flex items-center justify-between py-2.5">
                {content}
              </div>
            )
          })}
        </dl>
      </CardContent>
    </Card>
  )
}
