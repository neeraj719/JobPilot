import { ChevronRight, ScrollText } from 'lucide-react'
import * as React from 'react'
import { Link } from 'react-router-dom'

import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Pagination } from '@/components/ui/pagination'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { SkeletonRegion } from '@/components/common/skeletons'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { useAuditLog } from '@/features/automation/api'
import { formatApiClock, formatApiDate } from '@/features/automation/datetime'
import type { AuditLevel, AuditListParams, AuditLogRead } from '@/types/api'

const LEVEL_CLASS: Record<AuditLevel, string> = {
  INFO: 'text-muted-foreground',
  WARN: 'text-warning',
  ERROR: 'text-destructive',
}

const LEVEL_DOT: Record<AuditLevel, string> = {
  INFO: 'bg-info/60',
  WARN: 'bg-warning',
  ERROR: 'bg-destructive',
}

const ACTION_PREFIXES = [
  { value: 'all', label: 'All activity' },
  { value: 'application.', label: 'Applications' },
  { value: 'automation.', label: 'Automation' },
  { value: 'email.', label: 'Emails' },
  { value: 'job.', label: 'Jobs' },
  { value: 'auth.', label: 'Account' },
]

function AuditLine({ entry }: { entry: AuditLogRead }) {
  const [open, setOpen] = React.useState(false)
  const metadata = entry.metadata ?? entry.meta ?? {}
  const hasMetadata = Object.keys(metadata).length > 0

  return (
    <li className="group border-b border-border/60 last:border-b-0">
      <div className="flex items-start gap-2 px-1 py-1.5">
        <span className={cn('mt-[7px] size-1.5 shrink-0 rounded-full', LEVEL_DOT[entry.level])} aria-hidden />
        <time
          className="mt-px shrink-0 font-mono text-[11px] tabular-nums text-muted-foreground"
          dateTime={entry.created_at}
          title={formatApiDate(entry.created_at, 'd MMM yyyy, HH:mm:ss')}
        >
          {formatApiClock(entry.created_at)}
        </time>
        <div className="min-w-0 flex-1">
          <p className={cn('break-words text-sm leading-snug', LEVEL_CLASS[entry.level])}>
            <span className="font-medium text-foreground">{entry.message}</span>
          </p>
          <p className="flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
            <span className="font-mono">{entry.action}</span>
            <span aria-hidden>·</span>
            <span>{entry.actor.toLowerCase()}</span>
            {entry.application_id ? (
              <Link
                to={`/applications/${entry.application_id}`}
                className="text-primary underline-offset-2 hover:underline"
              >
                open application
              </Link>
            ) : null}
            {hasMetadata ? (
              <button
                type="button"
                onClick={() => setOpen((value) => !value)}
                aria-expanded={open}
                className="inline-flex items-center gap-0.5 text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
              >
                <ChevronRight className={cn('size-3 transition-transform', open && 'rotate-90')} aria-hidden />
                details
              </button>
            ) : null}
          </p>
          {open && hasMetadata ? (
            <pre className="mt-1.5 max-h-56 overflow-auto rounded-md border border-border bg-muted/50 p-2 text-[11px] leading-relaxed text-muted-foreground">
              {JSON.stringify(metadata, null, 2)}
            </pre>
          ) : null}
        </div>
      </div>
    </li>
  )
}

export interface AuditLogPanelProps {
  title: string
  description?: string
  /** Server-side filters. `page` is managed internally. */
  params: Omit<AuditListParams, 'page'>
  /** Show the level / prefix / search controls (used by the global panel). */
  showFilters?: boolean
  /** Poll while a run is in flight so the trail grows live. */
  refetchInterval?: number | false
  emptyDescription?: string
  className?: string
}

/**
 * The spec §27 audit trail: `09:32:11  Found job: Google — Software Engineer`, coloured
 * by level with expandable metadata. Used per-run and as the global activity feed.
 */
export function AuditLogPanel({
  title,
  description,
  params,
  showFilters = false,
  refetchInterval = false,
  emptyDescription = 'Nothing has been recorded yet.',
  className,
}: AuditLogPanelProps) {
  const [page, setPage] = React.useState(1)
  const [level, setLevel] = React.useState<'all' | AuditLevel>('all')
  const [prefix, setPrefix] = React.useState(params.action_prefix ?? 'all')
  const [search, setSearch] = React.useState('')

  const effectivePrefix = showFilters ? (prefix === 'all' ? undefined : prefix) : params.action_prefix
  const queryParams: AuditListParams = {
    ...params,
    action_prefix: effectivePrefix,
    page,
    page_size: params.page_size ?? 25,
  }

  const { data, isLoading, isError, error, refetch } = useAuditLog(queryParams, { refetchInterval })

  // Server-side paging plus these two cheap client-side filters over the current page.
  const entries = React.useMemo(() => {
    const items = data?.items ?? []
    const needle = search.trim().toLowerCase()
    return items.filter((entry) => {
      if (level !== 'all' && entry.level !== level) return false
      if (!needle) return true
      return entry.message.toLowerCase().includes(needle) || entry.action.toLowerCase().includes(needle)
    })
  }, [data?.items, level, search])

  React.useEffect(() => {
    setPage(1)
  }, [params.automation_run_id, params.application_id, prefix])

  return (
    <Card className={className}>
      <CardHeader className="gap-3 pb-3">
        <div className="space-y-1">
          <CardTitle>{title}</CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </div>
        {showFilters ? (
          <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_9rem_8rem]">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Filter this page…"
              aria-label="Filter the activity shown on this page"
            />
            <Select value={prefix} onValueChange={setPrefix}>
              <SelectTrigger aria-label="Activity type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ACTION_PREFIXES.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={level} onValueChange={(value) => setLevel(value as 'all' | AuditLevel)}>
              <SelectTrigger aria-label="Severity">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Any level</SelectItem>
                <SelectItem value="INFO">Info</SelectItem>
                <SelectItem value="WARN">Warning</SelectItem>
                <SelectItem value="ERROR">Error</SelectItem>
              </SelectContent>
            </Select>
          </div>
        ) : null}
      </CardHeader>

      <CardContent className="space-y-3">
        {isLoading ? (
          <SkeletonRegion label="Loading activity">
            {/* Same rows as `AuditLine`: level dot, time, message over the action line. */}
            <ul className="pr-1" aria-hidden>
              {Array.from({ length: 6 }, (_, index) => (
                <li key={index} className="border-b border-border/60 last:border-b-0">
                  <div className="flex items-start gap-2 px-1 py-1.5">
                    <Skeleton className="mt-[7px] size-1.5 shrink-0 rounded-full" />
                    <Skeleton className="mt-1 h-3 w-12 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="flex h-[1.203rem] items-center">
                        <Skeleton className={index % 2 ? 'h-3.5 w-1/2' : 'h-3.5 w-3/4'} />
                      </div>
                      <div className="flex h-[1.031rem] items-center">
                        <Skeleton className="h-2.5 w-28" />
                      </div>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </SkeletonRegion>
        ) : isError ? (
          <ErrorState error={error} size="sm" onRetry={() => void refetch()} />
        ) : entries.length === 0 ? (
          <EmptyState
            size="sm"
            icon={ScrollText}
            title="No activity"
            description={
              (data?.items.length ?? 0) > 0 ? 'Nothing on this page matches your filters.' : emptyDescription
            }
          />
        ) : (
          <ul className="max-h-[28rem] overflow-y-auto pr-1">
            {entries.map((entry) => (
              <AuditLine key={entry.id} entry={entry} />
            ))}
          </ul>
        )}

        {data ? (
          <Pagination
            page={page}
            pageSize={data.page_size}
            total={data.total}
            onPageChange={setPage}
            disabled={isLoading}
          />
        ) : null}
      </CardContent>
    </Card>
  )
}
