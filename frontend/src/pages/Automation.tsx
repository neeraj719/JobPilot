import { Bot } from 'lucide-react'
import * as React from 'react'
import { useSearchParams } from 'react-router-dom'

import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { CardSkeleton } from '@/components/common/skeletons'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { toast } from '@/components/ui/toaster'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { errorMessage } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import { useQueryClient } from '@tanstack/react-query'
import {
  useAutomationConfig,
  useAutomationRun,
  useAutomationRuns,
  useAutomationStatus,
  useCancelAutomationRun,
  useStartAutomationRun,
  useUpdateAutomationConfig,
} from '@/features/automation/api'
import { AuditLogPanel } from '@/features/automation/components/AuditLogPanel'
import { AutomationConfigSheet } from '@/features/automation/components/AutomationConfigSheet'
import { AutomationStatusHeader } from '@/features/automation/components/AutomationStatusHeader'
import { RunPipeline } from '@/features/automation/components/RunPipeline'
import { RunsHistoryTable } from '@/features/automation/components/RunsHistoryTable'
import { RunSummary } from '@/features/automation/components/RunSummary'
import { RUN_STATUS_LABELS } from '@/features/automation/components/RunStatusBadge'
import type { AutomationConfigUpdate, AutomationRunStatus } from '@/types/api'

const RUNS_PAGE_SIZE = 10

export default function AutomationPage() {
  useDocumentTitle('Automation')
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [configOpen, setConfigOpen] = React.useState(false)
  const [runsPage, setRunsPage] = React.useState(1)

  const statusQuery = useAutomationStatus()
  const configQuery = useAutomationConfig()
  const runsQuery = useAutomationRuns({ page: runsPage, page_size: RUNS_PAGE_SIZE })

  const status = statusQuery.data
  const config = configQuery.data

  // ?run=<id> selects a run; without it we follow the latest one the API reports.
  const runParam = searchParams.get('run')
  const selectedRunId = runParam ?? status?.last_run?.id ?? runsQuery.data?.items[0]?.id ?? null
  const runQuery = useAutomationRun(selectedRunId)
  const run = runQuery.data ?? (status?.last_run?.id === selectedRunId ? status.last_run : null)
  const isRunning = run?.status === 'RUNNING' || Boolean(status?.running)

  const startRun = useStartAutomationRun()
  const cancelRun = useCancelAutomationRun()
  const updateConfig = useUpdateAutomationConfig()

  const selectRun = React.useCallback(
    (runId: string) => {
      setSearchParams(
        (params) => {
          const next = new URLSearchParams(params)
          next.set('run', runId)
          return next
        },
        { replace: true },
      )
    },
    [setSearchParams],
  )

  // Keep the status card live while the pipeline works, then settle back down.
  const statusRefetch = statusQuery.refetch
  React.useEffect(() => {
    if (!isRunning) return
    const timer = window.setInterval(() => void statusRefetch(), 3_000)
    return () => window.clearInterval(timer)
  }, [isRunning, statusRefetch])

  // Announce the outcome once the polled run leaves RUNNING, and refresh what it touched.
  const previousStatus = React.useRef<AutomationRunStatus | null>(null)
  React.useEffect(() => {
    const current = run?.status ?? null
    const previous = previousStatus.current
    previousStatus.current = current
    if (previous !== 'RUNNING' || !current || current === 'RUNNING') return

    const label = RUN_STATUS_LABELS[current] ?? current
    const stats = run?.stats
    const counter = (key: string) => stats?.[key] ?? 0
    const description = `${counter('queued')} queued · ${counter('submitted')} submitted`

    if (current === 'FAILED') toast.error(`Automation run ${label.toLowerCase()}`, { description: run?.error ?? description })
    else if (current === 'CANCELLED') toast.info('Automation run cancelled', { description })
    else toast.success(`Automation run ${label.toLowerCase()}`, { description })

    void queryClient.invalidateQueries({ queryKey: ['automation'] })
    void queryClient.invalidateQueries({ queryKey: qk.applications.all })
    void queryClient.invalidateQueries({ queryKey: qk.jobs.all })
    void queryClient.invalidateQueries({ queryKey: ['audit'] })
    void queryClient.invalidateQueries({ queryKey: qk.dashboard.stats })
  }, [run?.status, run?.error, run?.stats, queryClient])

  async function handleToggleEnabled(enabled: boolean) {
    try {
      await updateConfig.mutateAsync({ enabled })
      toast.success(enabled ? 'Automation enabled' : 'Automation paused', {
        description: enabled ? 'The daily run is scheduled again.' : 'Nothing will run on a schedule.',
      })
    } catch (error) {
      toast.error('Could not update automation', { description: errorMessage(error) })
    }
  }

  async function handleRun(dryRun: boolean) {
    try {
      const started = await startRun.mutateAsync(dryRun)
      selectRun(started.id)
      previousStatus.current = 'RUNNING'
      toast.success(dryRun ? 'Dry run started' : 'Automation run started', {
        description: dryRun
          ? 'Nothing will be submitted — this only shows what the pipeline would do.'
          : 'Watch the pipeline below; this can take up to a minute.',
      })
      void statusQuery.refetch()
    } catch (error) {
      toast.error('Could not start the run', { description: errorMessage(error) })
    }
  }

  async function handleCancel() {
    const target = run?.status === 'RUNNING' ? run.id : status?.last_run?.id
    if (!target) return
    try {
      await cancelRun.mutateAsync(target)
      toast.info('Cancelling the run', { description: 'The pipeline stops after the current step.' })
      void statusQuery.refetch()
    } catch (error) {
      toast.error('Could not cancel the run', { description: errorMessage(error) })
    }
  }

  async function handleSaveConfig(values: AutomationConfigUpdate) {
    try {
      await updateConfig.mutateAsync(values)
      setConfigOpen(false)
      toast.success('Automation settings saved')
    } catch (error) {
      toast.error('Could not save the settings', { description: errorMessage(error) })
    }
  }

  const headerLoading = statusQuery.isLoading || configQuery.isLoading
  const hasAnyRun = Boolean(selectedRunId)

  if (statusQuery.isError && configQuery.isError) {
    return (
      <PageContainer>
        <PageHeader title="Automation" description="Schedule the daily run and set the safety rails it must respect." />
        <ErrorState
          error={statusQuery.error}
          title="Automation is unavailable"
          onRetry={() => {
            void statusQuery.refetch()
            void configQuery.refetch()
          }}
        />
      </PageContainer>
    )
  }

  return (
    <PageContainer>
      <PageHeader
        title="Automation"
        description="Schedule the daily run, watch the pipeline work and read exactly what it did."
      />

      <AutomationStatusHeader
        status={status}
        config={config}
        activeRun={run}
        loading={headerLoading}
        togglePending={updateConfig.isPending}
        runPending={startRun.isPending && !startRun.variables}
        dryRunPending={startRun.isPending && Boolean(startRun.variables)}
        cancelPending={cancelRun.isPending}
        onToggleEnabled={(enabled) => void handleToggleEnabled(enabled)}
        onRunNow={() => void handleRun(false)}
        onDryRun={() => void handleRun(true)}
        onCancel={() => void handleCancel()}
        onEditConfig={() => setConfigOpen(true)}
      />

      {hasAnyRun ? (
        <>
          <RunSummary run={run} loading={runQuery.isLoading && !run} />

          <div className="grid gap-4 lg:grid-cols-5">
            <RunPipeline run={run} loading={runQuery.isLoading && !run} className="lg:col-span-3" />
            <AuditLogPanel
              className="lg:col-span-2"
              title="Run log"
              description="Everything this run recorded, newest first."
              params={{ automation_run_id: selectedRunId ?? undefined, page_size: 50 }}
              refetchInterval={isRunning ? 5_000 : false}
              emptyDescription="This run did not write any audit entries."
            />
          </div>
        </>
      ) : statusQuery.isLoading || runsQuery.isLoading ? (
        // Until we know whether a run exists, hold the run section's shape.
        <>
          <RunSummary run={undefined} loading />
          <div className="grid gap-4 lg:grid-cols-5">
            <RunPipeline run={undefined} loading className="lg:col-span-3" />
            <CardSkeleton lines={5} className="lg:col-span-2" />
          </div>
        </>
      ) : (
        <EmptyState
          icon={Bot}
          title="No automation runs yet"
          description="Press “Run now” above to search every enabled platform, match the results to your resume and prepare applications for your approval."
        />
      )}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle>Run history</CardTitle>
          <CardDescription>Select a run to inspect its pipeline and log.</CardDescription>
        </CardHeader>
        <CardContent>
          <RunsHistoryTable
            page={runsQuery.data}
            loading={runsQuery.isLoading}
            error={runsQuery.isError ? runsQuery.error : undefined}
            onRetry={() => void runsQuery.refetch()}
            selectedRunId={selectedRunId}
            onSelect={selectRun}
            pageNumber={runsPage}
            onPageChange={setRunsPage}
          />
        </CardContent>
      </Card>

      <AuditLogPanel
        title="Recent automation activity"
        description="Every action the automation took on your applications."
        params={{ action_prefix: 'application.', page_size: 25 }}
        showFilters
        emptyDescription="Once the automation touches an application, it shows up here."
      />

      <AutomationConfigSheet
        open={configOpen}
        onOpenChange={setConfigOpen}
        config={config}
        saving={updateConfig.isPending}
        onSubmit={handleSaveConfig}
      />
    </PageContainer>
  )
}
