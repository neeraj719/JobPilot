import { Download, FileText, RefreshCw, Search } from 'lucide-react'
import * as React from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { DataTable, type DataTableColumn } from '@/components/common/DataTable'
import { MatchScore } from '@/components/common/MatchScore'
import { SourceBadge } from '@/components/common/SourceBadge'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Pagination } from '@/components/ui/pagination'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { toast } from '@/components/ui/toaster'
import { useApplications, useResumeOptions, useSetApplicationStatus } from '@/features/applications/api'
import { ApplicationStatusSelect } from '@/features/applications/components/ApplicationStatusSelect'
import { RefreshErrorBanner } from '@/features/applications/components/RefreshErrorBanner'
import { StatusChangeDialog } from '@/features/applications/components/StatusChangeDialog'
import { CompanyAvatar } from '@/features/jobs/components/CompanyAvatar'
import { useDebounce } from '@/hooks/useDebounce'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { errorMessage, saveBlob } from '@/lib/api'
import { APPLICATION_STATUS_LABELS, SOURCE_LABELS, formatDate, formatNumber, formatRelative } from '@/lib/utils'
import {
  APPLICATION_STATUSES,
  JOB_SOURCE_TYPES,
  type ApplicationListParams,
  type ApplicationRead,
  type ApplicationStatus,
  type JobSourceType,
} from '@/types/api'

const ANY = '__any__'
const PAGE_SIZE = 20

const SORT_OPTIONS = [
  { value: 'recent', label: 'Recently updated' },
  { value: 'applied', label: 'Applied date' },
  { value: 'score', label: 'Match score' },
  { value: 'company', label: 'Company' },
  { value: 'priority', label: 'Company priority' },
] as const

interface Filters {
  q: string
  status: ApplicationStatus | ''
  source: JobSourceType | ''
  company: string
  from: string
  to: string
  sort: string
  page: number
}

function readFilters(params: URLSearchParams): Filters {
  const page = Number(params.get('page') ?? '1')
  return {
    q: params.get('q') ?? '',
    status: (params.get('status') as ApplicationStatus | null) ?? '',
    source: (params.get('source') as JobSourceType | null) ?? '',
    company: params.get('company') ?? '',
    from: params.get('from') ?? '',
    to: params.get('to') ?? '',
    sort: params.get('sort') ?? 'recent',
    page: Number.isFinite(page) && page > 0 ? page : 1,
  }
}

function csvCell(value: unknown): string {
  const text = value === null || value === undefined ? '' : String(value)
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

export default function ApplicationsPage() {
  useDocumentTitle('Applications')
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = React.useMemo(() => readFilters(searchParams), [searchParams])

  const patch = React.useCallback(
    (next: Partial<Filters>) => {
      setSearchParams(
        (current) => {
          const params = new URLSearchParams(current)
          for (const [key, value] of Object.entries(next)) {
            if (value === '' || value === undefined || value === null) params.delete(key)
            else params.set(key, String(value))
          }
          if (next.page === undefined) params.delete('page')
          if (params.get('page') === '1') params.delete('page')
          if (params.get('sort') === 'recent') params.delete('sort')
          return params
        },
        { replace: true },
      )
    },
    [setSearchParams],
  )

  const [searchDraft, setSearchDraft] = React.useState(filters.q)
  const debouncedSearch = useDebounce(searchDraft, 350)
  React.useEffect(() => {
    if (debouncedSearch !== filters.q) patch({ q: debouncedSearch })
    // Only the debounced draft should drive this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch])
  React.useEffect(() => {
    setSearchDraft((draft) => (draft === filters.q ? draft : filters.q))
  }, [filters.q])

  const listParams = React.useMemo<ApplicationListParams>(
    () => ({
      page: filters.page,
      page_size: PAGE_SIZE,
      sort: filters.sort,
      ...(filters.q ? { q: filters.q } : {}),
      ...(filters.status ? { status: filters.status } : {}),
      ...(filters.source ? { source: filters.source } : {}),
      ...(filters.company ? { company: filters.company } : {}),
      ...(filters.from ? { from: new Date(`${filters.from}T00:00:00`).toISOString() } : {}),
      ...(filters.to ? { to: new Date(`${filters.to}T23:59:59`).toISOString() } : {}),
    }),
    [filters],
  )

  const applicationsQuery = useApplications(listParams)
  const resumesQuery = useResumeOptions()
  const setStatus = useSetApplicationStatus()

  const resumeNames = React.useMemo(() => {
    const map = new Map<string, string>()
    for (const resume of resumesQuery.data ?? []) map.set(resume.id, resume.name)
    return map
  }, [resumesQuery.data])

  const [statusTarget, setStatusTarget] = React.useState<{ row: ApplicationRead; status: ApplicationStatus } | null>(null)

  async function handleStatusConfirm(status: ApplicationStatus, note?: string) {
    if (!statusTarget) return
    try {
      await setStatus.mutateAsync({ id: statusTarget.row.id, status, ...(note ? { note } : {}) })
      toast.success(`Status set to ${APPLICATION_STATUS_LABELS[status]}`, {
        description: `${statusTarget.row.job_title ?? 'Application'} at ${statusTarget.row.company_name ?? 'this company'}`,
      })
    } catch (error) {
      toast.error('Could not change the status', { description: errorMessage(error) })
    } finally {
      setStatusTarget(null)
    }
  }

  function handleExport() {
    const rows = applicationsQuery.data?.items ?? []
    if (rows.length === 0) {
      toast.error('Nothing to export on this page')
      return
    }
    const header = [
      'Company',
      'Position',
      'Source',
      'Applied date',
      'Resume used',
      'Match score',
      'Status',
      'Last update',
      'Next action',
      'Next action due',
    ]
    const body = rows.map((row) =>
      [
        row.company_name ?? '',
        row.job_title ?? '',
        row.source ?? '',
        row.applied_at ? formatDate(row.applied_at, 'yyyy-MM-dd', '') : '',
        row.resume_id ? (resumeNames.get(row.resume_id) ?? row.resume_id) : '',
        row.match_score ?? '',
        APPLICATION_STATUS_LABELS[row.status] ?? row.status,
        row.last_update_at ? formatDate(row.last_update_at, 'yyyy-MM-dd', '') : '',
        row.next_action ?? '',
        row.next_action_due ? formatDate(row.next_action_due, 'yyyy-MM-dd', '') : '',
      ]
        .map(csvCell)
        .join(','),
    )
    const csv = `${header.join(',')}\n${body.join('\n')}\n`
    saveBlob(new Blob([csv], { type: 'text/csv;charset=utf-8' }), `jobpilot-applications-page-${filters.page}.csv`)
    toast.success(`Exported ${rows.length} ${rows.length === 1 ? 'row' : 'rows'}`)
  }

  const columns: DataTableColumn<ApplicationRead>[] = [
    {
      id: 'company',
      header: 'Company',
      cell: (row) => (
        <div className="flex items-center gap-2">
          <CompanyAvatar name={row.company_name} logoUrl={row.company_logo_url} size="sm" />
          <div className="min-w-0">
            <p className="truncate font-medium">{row.company_name ?? '—'}</p>
            <p className="truncate text-xs text-muted-foreground">{row.location ?? '—'}</p>
          </div>
        </div>
      ),
    },
    { id: 'position', header: 'Position', cell: (row) => <span className="font-medium">{row.job_title ?? '—'}</span> },
    { id: 'source', header: 'Source', hideBelowMd: true, cell: (row) => <SourceBadge source={row.source} /> },
    {
      id: 'applied',
      header: 'Applied',
      hideBelowMd: true,
      cell: (row) => <span className="whitespace-nowrap text-sm">{formatDate(row.applied_at, 'd MMM yyyy', 'Not yet')}</span>,
    },
    {
      id: 'resume',
      header: 'Resume used',
      hideBelowMd: true,
      cell: (row) => (
        <span className="text-sm text-muted-foreground">
          {row.resume_id ? (resumeNames.get(row.resume_id) ?? 'Resume') : '—'}
        </span>
      ),
    },
    {
      id: 'match',
      header: 'Match',
      align: 'center',
      hideBelowMd: true,
      cell: (row) => <MatchScore score={row.match_score} size="sm" />,
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => (
        <div onClick={(event) => event.stopPropagation()}>
          <ApplicationStatusSelect
            value={row.status}
            disabled={setStatus.isPending}
            aria-label={`Status of ${row.job_title ?? 'application'}`}
            onChange={(status) => {
              if (status !== row.status) setStatusTarget({ row, status })
            }}
          />
        </div>
      ),
    },
    {
      id: 'last_update',
      header: 'Last update',
      hideBelowMd: true,
      cell: (row) => (
        <span className="whitespace-nowrap text-sm text-muted-foreground">
          {formatRelative(row.last_update_at ?? row.updated_at)}
        </span>
      ),
    },
    {
      id: 'next_action',
      header: 'Next action',
      hideBelowMd: true,
      cell: (row) =>
        row.next_action ? (
          <div className="min-w-0">
            <p className="truncate text-sm">{row.next_action}</p>
            {row.next_action_due ? (
              <p className="text-xs text-muted-foreground">Due {formatDate(row.next_action_due)}</p>
            ) : null}
          </div>
        ) : (
          <span className="text-sm text-muted-foreground">—</span>
        ),
    },
  ]

  const page = applicationsQuery.data
  const total = page?.total ?? 0
  const hasFilters = Boolean(filters.q || filters.status || filters.source || filters.company || filters.from || filters.to)

  return (
    <PageContainer>
      <PageHeader
        title="Applications"
        description="Every application JobPilot prepared or submitted for you, with its live status."
        actions={
          <>
            <Button variant="outline" onClick={handleExport} disabled={!page || total === 0}>
              <Download />
              Export CSV
            </Button>
            <Button
              variant="outline"
              onClick={() => void applicationsQuery.refetch()}
              disabled={applicationsQuery.isFetching}
            >
              <RefreshCw className={applicationsQuery.isFetching ? 'animate-spin' : undefined} />
              Refresh
            </Button>
          </>
        }
      />

      <div className="space-y-3 rounded-lg border border-border bg-card p-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="relative sm:col-span-2 lg:col-span-1">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden
            />
            <Input
              value={searchDraft}
              onChange={(event) => setSearchDraft(event.target.value)}
              placeholder="Search role, company or notes"
              aria-label="Search applications"
              className="pl-9"
            />
          </div>

          <Select
            value={filters.status || ANY}
            onValueChange={(value) => patch({ status: value === ANY ? '' : (value as ApplicationStatus) })}
          >
            <SelectTrigger aria-label="Filter by status">
              <SelectValue placeholder="Any status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY}>Any status</SelectItem>
              {APPLICATION_STATUSES.map((status) => (
                <SelectItem key={status} value={status}>
                  {APPLICATION_STATUS_LABELS[status]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select
            value={filters.source || ANY}
            onValueChange={(value) => patch({ source: value === ANY ? '' : (value as JobSourceType) })}
          >
            <SelectTrigger aria-label="Filter by source">
              <SelectValue placeholder="Any source" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY}>Any source</SelectItem>
              {JOB_SOURCE_TYPES.map((source) => (
                <SelectItem key={source} value={source}>
                  {SOURCE_LABELS[source]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Input
            value={filters.company}
            onChange={(event) => patch({ company: event.target.value })}
            placeholder="Company"
            aria-label="Filter by company"
          />
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1.5">
            <Label htmlFor="applications-from" className="text-xs text-muted-foreground">
              Applied from
            </Label>
            <Input
              id="applications-from"
              type="date"
              value={filters.from}
              onChange={(event) => patch({ from: event.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="applications-to" className="text-xs text-muted-foreground">
              Applied to
            </Label>
            <Input
              id="applications-to"
              type="date"
              value={filters.to}
              onChange={(event) => patch({ to: event.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="applications-sort" className="text-xs text-muted-foreground">
              Sort by
            </Label>
            <Select value={filters.sort} onValueChange={(value) => patch({ sort: value })}>
              <SelectTrigger id="applications-sort">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SORT_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-end justify-between gap-2">
            {hasFilters ? (
              <Button variant="ghost" size="sm" onClick={() => setSearchParams(new URLSearchParams(), { replace: true })}>
                Clear filters
              </Button>
            ) : (
              <span />
            )}
            <p className="text-sm text-muted-foreground" aria-live="polite">
              {formatNumber(total)} total
            </p>
          </div>
        </div>
      </div>

      {applicationsQuery.isError && page ? (
        <RefreshErrorBanner error={applicationsQuery.error} onRetry={() => void applicationsQuery.refetch()} />
      ) : null}

      <DataTable
        data={page?.items}
        columns={columns}
        getRowId={(row) => row.id}
        loading={applicationsQuery.isLoading && !page}
        error={applicationsQuery.isError && !page ? applicationsQuery.error : undefined}
        onRetry={() => void applicationsQuery.refetch()}
        onRowClick={(row) => navigate(`/applications/${row.id}`)}
        emptyIcon={FileText}
        emptyTitle={hasFilters ? 'No applications match these filters' : 'No applications yet'}
        emptyDescription={
          hasFilters
            ? 'Try a wider date range or clear the filters.'
            : 'Queue a job from the Jobs page and JobPilot will prepare the application for you.'
        }
        emptyAction={<Button onClick={() => navigate('/jobs')}>Browse jobs</Button>}
      />

      <Pagination
        page={filters.page}
        pageSize={PAGE_SIZE}
        total={total}
        onPageChange={(next) => patch({ page: next })}
        disabled={applicationsQuery.isFetching}
      />

      <StatusChangeDialog
        open={statusTarget !== null}
        onOpenChange={(open) => {
          if (!open) setStatusTarget(null)
        }}
        status={statusTarget?.status ?? null}
        subject={
          statusTarget ? `${statusTarget.row.job_title ?? 'Application'} at ${statusTarget.row.company_name ?? '—'}` : undefined
        }
        loading={setStatus.isPending}
        onConfirm={handleStatusConfirm}
      />
    </PageContainer>
  )
}
