import { Ban, ListChecks, MoreHorizontal, Play, RefreshCw, X } from 'lucide-react'
import * as React from 'react'
import { useNavigate } from 'react-router-dom'

import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { DataTable, type DataTableColumn } from '@/components/common/DataTable'
import { MatchScore } from '@/components/common/MatchScore'
import { PriorityBadge } from '@/components/common/PriorityBadge'
import { SourceBadge } from '@/components/common/SourceBadge'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Pagination } from '@/components/ui/pagination'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { toast } from '@/components/ui/toaster'
import { useReviewSummary, useSkipApplication, useStartApplication } from '@/features/applications/api'
import { AutomationBadge, automationSummary } from '@/features/applications/components/AutomationBadge'
import { ReasonDialog } from '@/features/applications/components/ReasonDialog'
import { RefreshErrorBanner } from '@/features/applications/components/RefreshErrorBanner'
import { CompanyAvatar } from '@/features/jobs/components/CompanyAvatar'
import { useQueue, useSetCompanyPriority } from '@/features/queue/api'
import { QueueSummary } from '@/features/queue/components/QueueSummary'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { errorMessage } from '@/lib/api'
import { APPLICATION_STATUS_LABELS, PRIORITY_LABELS, formatRelative } from '@/lib/utils'
import {
  COMPANY_PRIORITIES,
  type ApplicationStatus,
  type ApplicationType,
  type CompanyPriority,
  type QueueItem,
} from '@/types/api'

const ANY = '__any__'
const PAGE_SIZE = 20
const POLL_MS = 10_000

/** `humanizeEnum` would render `ATS_FORM` as "Ats form" — spell these out instead. */
const APPLICATION_TYPE_LABELS: Record<ApplicationType, string> = {
  EASY_APPLY: 'Easy apply',
  EXTERNAL_FORM: 'External form',
  ATS_FORM: 'ATS form',
  EMAIL: 'Email',
  UNKNOWN: 'Unknown form',
}

/** Statuses worth offering as a queue filter — the queue only ever holds these. */
const QUEUE_STATUSES: ApplicationStatus[] = ['QUEUED', 'IN_PROGRESS']

export default function QueuePage() {
  useDocumentTitle('Application queue')
  const navigate = useNavigate()

  const [priority, setPriority] = React.useState<CompanyPriority | ''>('')
  const [status, setStatus] = React.useState<ApplicationStatus | ''>('')
  const [page, setPage] = React.useState(1)

  const params = React.useMemo(
    () => ({
      page,
      page_size: PAGE_SIZE,
      ...(priority ? { priority } : {}),
      ...(status ? { status } : {}),
    }),
    [page, priority, status],
  )

  // Poll only while something is actually moving, so an idle queue stays quiet.
  const [isLive, setIsLive] = React.useState(false)
  const queueQuery = useQueue(params, { refetchInterval: isLive ? POLL_MS : false })
  const summaryQuery = useReviewSummary(isLive ? POLL_MS : false)

  const items = React.useMemo(() => queueQuery.data?.items ?? [], [queueQuery.data])

  React.useEffect(() => {
    // Only a genuinely moving run justifies polling — an application parked on the user
    // also carries status IN_PROGRESS and would otherwise poll forever.
    const live = items.some(
      (item) =>
        item.application.automation_state === 'RUNNING' || item.application.automation_state === 'RETRYING',
    )
    setIsLive(live)
  }, [items])

  const startApplication = useStartApplication()
  const skipApplication = useSkipApplication()
  const setCompanyPriority = useSetCompanyPriority()

  const [startingId, setStartingId] = React.useState<string | null>(null)
  const [skipTarget, setSkipTarget] = React.useState<QueueItem | null>(null)
  const [blacklistTarget, setBlacklistTarget] = React.useState<QueueItem | null>(null)

  async function handleStart(item: QueueItem) {
    setStartingId(item.application.id)
    try {
      const updated = await startApplication.mutateAsync(item.application.id)
      const summary = automationSummary(updated)
      toast.success(`Automation started — ${summary.label}`, {
        description: `${item.application.job_title ?? 'Application'} at ${item.application.company_name ?? 'this company'}`,
        action: { label: 'Review', onClick: () => navigate(`/applications/${item.application.id}`) },
      })
    } catch (error) {
      toast.error('Could not start this application', { description: errorMessage(error) })
    } finally {
      setStartingId(null)
    }
  }

  async function handleSkip(reason?: string) {
    if (!skipTarget) return
    try {
      await skipApplication.mutateAsync({ id: skipTarget.application.id, ...(reason ? { reason } : {}) })
      toast.success('Removed from the queue', { description: skipTarget.application.job_title ?? undefined })
    } catch (error) {
      toast.error('Could not skip this application', { description: errorMessage(error) })
    } finally {
      setSkipTarget(null)
    }
  }

  async function handleBlacklist() {
    if (!blacklistTarget) return
    const name = blacklistTarget.application.company_name ?? blacklistTarget.job?.company?.name
    if (!name) {
      toast.error('This row has no company name to blacklist')
      setBlacklistTarget(null)
      return
    }
    try {
      await setCompanyPriority.mutateAsync({ companyName: name, priority: 'AVOID' })
      toast.success(`${name} marked as "Avoid"`, {
        description: 'Their open applications are skipped and new postings drop to the bottom of your queue.',
      })
    } catch (error) {
      toast.error('Could not blacklist this company', { description: errorMessage(error) })
    } finally {
      setBlacklistTarget(null)
    }
  }

  const columns: DataTableColumn<QueueItem>[] = [
    {
      id: 'priority',
      header: 'Priority',
      cell: (item, rowIndex) => (
        <div className="flex items-center gap-2">
          {/* The API's `position` is the stored queue_position; the rank is the row's
              place in the priority / score / freshness ordering the endpoint returns. */}
          <span className="w-5 text-xs tabular-nums text-muted-foreground">
            {(page - 1) * PAGE_SIZE + rowIndex + 1}
          </span>
          <PriorityBadge priority={item.application.priority} />
        </div>
      ),
    },
    {
      id: 'company',
      header: 'Company',
      cell: (item) => (
        <div className="flex items-center gap-2">
          <CompanyAvatar
            name={item.application.company_name ?? item.job?.company?.name}
            logoUrl={item.application.company_logo_url ?? item.job?.company?.logo_url}
            size="sm"
          />
          <div className="min-w-0">
            <p className="truncate font-medium">{item.application.company_name ?? item.job?.company?.name ?? '—'}</p>
            <p className="truncate text-xs text-muted-foreground">{item.application.location ?? item.job?.location ?? '—'}</p>
          </div>
        </div>
      ),
    },
    {
      id: 'position',
      header: 'Position',
      cell: (item) => (
        <div className="min-w-0">
          <p className="truncate font-medium">{item.application.job_title ?? item.job?.title ?? '—'}</p>
          <p className="truncate text-xs text-muted-foreground">
            {APPLICATION_TYPE_LABELS[item.application.application_type ?? item.job?.application_type ?? 'UNKNOWN']}
          </p>
        </div>
      ),
    },
    {
      id: 'match',
      header: 'Match',
      align: 'center',
      hideBelowMd: true,
      cell: (item) => <MatchScore score={item.application.match_score} size="sm" />,
    },
    {
      id: 'source',
      header: 'Source',
      hideBelowMd: true,
      cell: (item) => <SourceBadge source={item.application.source ?? item.job?.primary_source} />,
    },
    {
      id: 'status',
      header: 'Status',
      cell: (item) => (
        <div className="space-y-1">
          <AutomationBadge application={item.application} />
          {item.application.updated_at ? (
            <p className="text-[11px] text-muted-foreground">{formatRelative(item.application.updated_at)}</p>
          ) : null}
        </div>
      ),
    },
    {
      id: 'actions',
      header: <span className="sr-only">Actions</span>,
      align: 'right',
      cell: (item) => {
        const running =
          item.application.automation_state === 'RUNNING' || item.application.automation_state === 'RETRYING'
        return (
          <div className="flex items-center justify-end gap-1" onClick={(event) => event.stopPropagation()}>
            <Button variant="outline" size="sm" onClick={() => navigate(`/applications/${item.application.id}`)}>
              Review
            </Button>
            <Button
              size="sm"
              onClick={() => void handleStart(item)}
              loading={startingId === item.application.id}
              disabled={running || startingId !== null}
              title={running ? 'This application is already running' : 'Start the automated application'}
            >
              <Play />
              Start
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" aria-label="More queue actions">
                  <MoreHorizontal />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={() => setSkipTarget(item)}>
                  <X />
                  Skip this application
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onSelect={() => setBlacklistTarget(item)}
                  className="text-destructive focus:text-destructive"
                >
                  <Ban />
                  Blacklist company
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        )
      },
    },
  ]

  const total = queueQuery.data?.total ?? 0

  return (
    <PageContainer>
      <PageHeader
        title="Application queue"
        description="Ordered by company priority, then match score, then freshness — work top-down."
        actions={
          <Button variant="outline" onClick={() => void queueQuery.refetch()} loading={queueQuery.isFetching}>
            {queueQuery.isFetching ? null : <RefreshCw />}
            Refresh
          </Button>
        }
      />

      {queueQuery.isError && queueQuery.data ? (
        <RefreshErrorBanner error={queueQuery.error} onRetry={() => void queueQuery.refetch()} />
      ) : null}

      <QueueSummary counts={summaryQuery.data} loading={summaryQuery.isLoading} />

      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={priority || ANY}
          onValueChange={(value) => {
            setPriority(value === ANY ? '' : (value as CompanyPriority))
            setPage(1)
          }}
        >
          <SelectTrigger className="w-48" aria-label="Filter by company priority">
            <SelectValue placeholder="Any priority" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Any priority</SelectItem>
            {COMPANY_PRIORITIES.map((value) => (
              <SelectItem key={value} value={value}>
                {PRIORITY_LABELS[value]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={status || ANY}
          onValueChange={(value) => {
            setStatus(value === ANY ? '' : (value as ApplicationStatus))
            setPage(1)
          }}
        >
          <SelectTrigger className="w-48" aria-label="Filter by status">
            <SelectValue placeholder="Any status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Any status</SelectItem>
            {QUEUE_STATUSES.map((value) => (
              <SelectItem key={value} value={value}>
                {APPLICATION_STATUS_LABELS[value]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {priority || status ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setPriority('')
              setStatus('')
              setPage(1)
            }}
          >
            Clear filters
          </Button>
        ) : null}

        <p className="ml-auto text-sm text-muted-foreground" aria-live="polite">
          {total} in queue{isLive ? ' · live' : ''}
        </p>
      </div>

      <DataTable
        data={items}
        columns={columns}
        getRowId={(item) => item.application.id}
        loading={queueQuery.isLoading && !queueQuery.data}
        error={queueQuery.isError && !queueQuery.data ? queueQuery.error : undefined}
        onRetry={() => void queueQuery.refetch()}
        onRowClick={(item) => navigate(`/applications/${item.application.id}`)}
        emptyIcon={ListChecks}
        emptyTitle="Your queue is empty"
        emptyDescription="Queue a job from the Jobs page, or let the daily automation fill this for you."
        emptyAction={<Button onClick={() => navigate('/jobs')}>Browse jobs</Button>}
      />

      <Pagination
        page={page}
        pageSize={PAGE_SIZE}
        total={total}
        onPageChange={setPage}
        disabled={queueQuery.isFetching}
      />

      <ReasonDialog
        open={skipTarget !== null}
        onOpenChange={(open) => {
          if (!open) setSkipTarget(null)
        }}
        title="Skip this application?"
        description={
          skipTarget
            ? `${skipTarget.application.job_title ?? 'This role'} at ${
                skipTarget.application.company_name ?? 'this company'
              } leaves the queue. Nothing is submitted.`
            : undefined
        }
        placeholder="e.g. not interested after reading the description"
        confirmLabel="Skip"
        variant="destructive"
        loading={skipApplication.isPending}
        onConfirm={handleSkip}
      />

      <ConfirmDialog
        open={blacklistTarget !== null}
        onOpenChange={(open) => {
          if (!open) setBlacklistTarget(null)
        }}
        title={`Blacklist ${blacklistTarget?.application.company_name ?? 'this company'}?`}
        description="Their priority is set to Avoid: open applications are skipped and new postings sink to the bottom of your queue. You can change it again from the Companies page."
        confirmLabel="Blacklist company"
        variant="destructive"
        loading={setCompanyPriority.isPending}
        onConfirm={handleBlacklist}
      />
    </PageContainer>
  )
}
