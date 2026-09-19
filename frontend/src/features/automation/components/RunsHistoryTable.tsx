import { History } from 'lucide-react'

import { DataTable } from '@/components/common/DataTable'
import { Pagination } from '@/components/ui/pagination'
import { cn } from '@/lib/utils'
import { RunStatusBadge } from '@/features/automation/components/RunStatusBadge'
import { durationBetween, formatApiDateTime, formatApiRelative, formatDuration } from '@/features/automation/datetime'
import { statCount } from '@/features/automation/stats'
import type { AutomationRunRead, PageResponse } from '@/types/api'

export interface RunsHistoryTableProps {
  page: PageResponse<AutomationRunRead> | undefined
  loading?: boolean
  error?: unknown
  onRetry?: () => void
  selectedRunId: string | null
  onSelect: (runId: string) => void
  pageNumber: number
  onPageChange: (page: number) => void
}

/** Run history — clicking a row selects it (mirrored into the `?run=` query param). */
export function RunsHistoryTable({
  page,
  loading = false,
  error,
  onRetry,
  selectedRunId,
  onSelect,
  pageNumber,
  onPageChange,
}: RunsHistoryTableProps) {
  return (
    <div className="space-y-3">
      <DataTable<AutomationRunRead>
        data={page?.items}
        loading={loading}
        error={error}
        onRetry={onRetry}
        getRowId={(run) => run.id}
        onRowClick={(run) => onSelect(run.id)}
        emptyIcon={History}
        emptyTitle="No automation runs yet"
        emptyDescription="Use “Run now” above to start the pipeline — the run and every step it takes will show up here."
        columns={[
          {
            id: 'started',
            header: 'Started',
            cell: (run) => (
              <div className="min-w-0">
                <p
                  className={cn(
                    'truncate text-sm font-medium',
                    run.id === selectedRunId && 'text-primary',
                  )}
                >
                  {formatApiDateTime(run.started_at)}
                </p>
                <p className="text-xs text-muted-foreground">{formatApiRelative(run.started_at)}</p>
              </div>
            ),
          },
          {
            id: 'trigger',
            header: 'Trigger',
            hideBelowMd: true,
            cell: (run) => (
              <span className="text-sm text-muted-foreground">
                {run.trigger === 'MANUAL' ? 'Manual' : 'Scheduled'}
              </span>
            ),
          },
          {
            id: 'status',
            header: 'Status',
            cell: (run) => <RunStatusBadge status={run.status} />,
          },
          {
            id: 'duration',
            header: 'Duration',
            align: 'right',
            hideBelowMd: true,
            cell: (run) => (
              <span className="text-sm tabular-nums text-muted-foreground">
                {run.finished_at ? formatDuration(durationBetween(run.started_at, run.finished_at)) : '—'}
              </span>
            ),
          },
          {
            id: 'found',
            header: 'Found',
            align: 'right',
            cell: (run) => <span className="text-sm tabular-nums">{statCount(run.stats, 'jobs_found')}</span>,
          },
          {
            id: 'queued',
            header: 'Queued',
            align: 'right',
            cell: (run) => <span className="text-sm tabular-nums">{statCount(run.stats, 'queued')}</span>,
          },
          {
            id: 'submitted',
            header: 'Submitted',
            align: 'right',
            cell: (run) => <span className="text-sm tabular-nums">{statCount(run.stats, 'submitted')}</span>,
          },
        ]}
      />
      {page ? (
        <Pagination
          page={pageNumber}
          pageSize={page.page_size}
          total={page.total}
          onPageChange={onPageChange}
          disabled={loading}
        />
      ) : null}
    </div>
  )
}
