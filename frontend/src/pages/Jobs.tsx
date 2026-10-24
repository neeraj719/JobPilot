import { Briefcase, RefreshCw, Search, Telescope } from 'lucide-react'
import * as React from 'react'
import { useNavigate } from 'react-router-dom'

import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Pagination } from '@/components/ui/pagination'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { toast } from '@/components/ui/toaster'
import { ReasonDialog } from '@/features/applications/components/ReasonDialog'
import { RefreshErrorBanner } from '@/features/applications/components/RefreshErrorBanner'
import { useStartApplication } from '@/features/applications/api'
import { useAnalyzeJob, useDiscoverJobs, useJob, useJobSources, useJobs, useQueueJob, useSkipJob } from '@/features/jobs/api'
import { JobCardItem } from '@/features/jobs/components/JobCardItem'
import { JobDetailSheet } from '@/features/jobs/components/JobDetailSheet'
import { JobFilters } from '@/features/jobs/components/JobFilters'
import { JOBS_PAGE_SIZE, toJobListParams, useJobFilters } from '@/features/jobs/filters'
import { JobGridSkeleton } from '@/features/jobs/components/JobsSkeletons'
import { useDebounce } from '@/hooks/useDebounce'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { errorMessage } from '@/lib/api'
import { formatNumber } from '@/lib/utils'
import type { JobCard, JobSortOption, UUID } from '@/types/api'

type BusyAction = 'apply' | 'queue' | 'analyze' | 'skip'

const SORT_LABELS: Record<JobSortOption, string> = {
  match: 'Best match',
  posted: 'Most recent',
  salary: 'Highest salary',
}

export default function JobsPage() {
  useDocumentTitle('Jobs')
  const navigate = useNavigate()
  const { filters, setFilter, reset, activeCount } = useJobFilters()

  // The search box is local so typing stays snappy; the URL follows 350ms later.
  const [searchDraft, setSearchDraft] = React.useState(filters.q)
  const debouncedSearch = useDebounce(searchDraft, 350)
  React.useEffect(() => {
    if (debouncedSearch !== filters.q) setFilter('q', debouncedSearch)
    // `setFilter`/`filters.q` would re-run this on every URL change; the draft is the trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch])
  React.useEffect(() => {
    setSearchDraft((draft) => (draft === filters.q ? draft : filters.q))
  }, [filters.q])

  const listParams = React.useMemo(() => toJobListParams(filters), [filters])
  const jobsQuery = useJobs(listParams)
  const sourcesQuery = useJobSources()

  const [detailJobId, setDetailJobId] = React.useState<UUID | null>(null)
  const detailQuery = useJob(detailJobId)

  const [skipTarget, setSkipTarget] = React.useState<JobCard | null>(null)
  const [busy, setBusy] = React.useState<{ id: UUID; action: BusyAction } | null>(null)

  const discover = useDiscoverJobs()
  const analyze = useAnalyzeJob()
  const queueJob = useQueueJob()
  const skipJob = useSkipJob()
  const startApplication = useStartApplication()

  async function handleDiscover() {
    try {
      const result = await discover.mutateAsync({})
      const failed = (result.sources ?? []).filter((source) => source.error)
      toast.success(
        `Discovery finished — ${formatNumber(result.jobs_found)} found, ${formatNumber(result.jobs_new)} new`,
        {
          description: `${formatNumber(result.duplicates_merged)} duplicates merged across ${
            result.sources?.length ?? 0
          } sources${failed.length > 0 ? ` · ${failed.length} source(s) errored` : ''}.`,
        },
      )
    } catch (error) {
      toast.error('Discovery failed', { description: errorMessage(error) })
    }
  }

  async function handleAnalyze(job: { id: UUID; title: string }) {
    setBusy({ id: job.id, action: 'analyze' })
    try {
      const match = await analyze.mutateAsync({ jobId: job.id })
      toast.success(`Scored ${match.match_score}% for "${job.title}"`, { description: match.explanation })
    } catch (error) {
      toast.error('Could not analyze this job', { description: errorMessage(error) })
    } finally {
      setBusy(null)
    }
  }

  async function handleQueue(job: { id: UUID; title: string }) {
    setBusy({ id: job.id, action: 'queue' })
    try {
      await queueJob.mutateAsync(job.id)
      toast.success('Added to your application queue', {
        description: job.title,
        action: { label: 'Open queue', onClick: () => navigate('/queue') },
      })
    } catch (error) {
      toast.error('Could not queue this job', { description: errorMessage(error) })
    } finally {
      setBusy(null)
    }
  }

  /** Queue the job, hand it to the runner, then jump into the Approval Center. */
  async function handleApply(job: { id: UUID; title: string }) {
    setBusy({ id: job.id, action: 'apply' })
    try {
      const application = await queueJob.mutateAsync(job.id)
      try {
        await startApplication.mutateAsync(application.id)
        toast.success('Application started', { description: `${job.title} — review the prepared answers.` })
      } catch (startError) {
        toast.warning('Queued, but automation could not start', { description: errorMessage(startError) })
      }
      setDetailJobId(null)
      navigate(`/applications/${application.id}`)
    } catch (error) {
      toast.error('Could not apply to this job', { description: errorMessage(error) })
    } finally {
      setBusy(null)
    }
  }

  async function handleSkipConfirm(reason?: string) {
    if (!skipTarget) return
    try {
      await skipJob.mutateAsync({ jobId: skipTarget.id, ...(reason ? { reason } : {}) })
      toast.success('Job skipped', { description: skipTarget.title })
      if (detailJobId === skipTarget.id) setDetailJobId(null)
    } catch (error) {
      toast.error('Could not skip this job', { description: errorMessage(error) })
    } finally {
      setSkipTarget(null)
    }
  }

  const page = jobsQuery.data
  const items = page?.items ?? []
  const showSkeleton = jobsQuery.isLoading && !page

  return (
    <PageContainer>
      <PageHeader
        title="Jobs"
        description="Every posting discovered across your platforms, deduplicated and scored against your resume."
        actions={
          <>
            <Button variant="outline" onClick={() => void jobsQuery.refetch()} loading={jobsQuery.isFetching}>
              {jobsQuery.isFetching ? null : <RefreshCw />}
              Refresh
            </Button>
            <Button onClick={handleDiscover} loading={discover.isPending}>
              <Telescope />
              Discover jobs
            </Button>
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[17rem_minmax(0,1fr)]">
        <JobFilters
          filters={filters}
          setFilter={setFilter}
          reset={reset}
          activeCount={activeCount}
          sources={sourcesQuery.data}
          className="lg:sticky lg:top-6 lg:self-start"
        />

        <div className="min-w-0 space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input
                value={searchDraft}
                onChange={(event) => setSearchDraft(event.target.value)}
                placeholder="Search title, company or description"
                aria-label="Search jobs"
                className="pl-9"
              />
            </div>
            <Select value={filters.sort} onValueChange={(value) => setFilter('sort', value as JobSortOption)}>
              <SelectTrigger className="sm:w-48" aria-label="Sort jobs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(SORT_LABELS) as JobSortOption[]).map((option) => (
                  <SelectItem key={option} value={option}>
                    {SORT_LABELS[option]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {page ? (
            <p className="text-sm text-muted-foreground" aria-live="polite">
              {formatNumber(page.total)} {page.total === 1 ? 'job' : 'jobs'}
              {activeCount > 0 ? ' matching your filters' : ''}
              {jobsQuery.isFetching ? <span className="sr-only"> · updating</span> : null}
            </p>
          ) : null}

          {jobsQuery.isError && page ? (
            <RefreshErrorBanner error={jobsQuery.error} onRetry={() => void jobsQuery.refetch()} />
          ) : null}

          {jobsQuery.isError && !page ? (
            <ErrorState error={jobsQuery.error} onRetry={() => void jobsQuery.refetch()} />
          ) : showSkeleton ? (
            <JobGridSkeleton count={6} />
          ) : items.length === 0 ? (
            <EmptyState
              icon={Briefcase}
              title={activeCount > 0 ? 'No jobs match these filters' : 'No jobs discovered yet'}
              description={
                activeCount > 0
                  ? 'Loosen a filter, or run discovery to pull fresh postings from your sources.'
                  : 'Run discovery to pull postings from Naukri, LinkedIn, Indeed and the rest of your enabled sources.'
              }
              action={
                activeCount > 0 ? (
                  <Button variant="outline" onClick={reset}>
                    Clear filters
                  </Button>
                ) : (
                  <Button onClick={handleDiscover} loading={discover.isPending}>
                    <Telescope />
                    Discover jobs
                  </Button>
                )
              }
            />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {items.map((job) => (
                <JobCardItem
                  key={job.id}
                  job={job}
                  onView={(selected) => setDetailJobId(selected.id)}
                  onApply={handleApply}
                  onQueue={handleQueue}
                  onAnalyze={handleAnalyze}
                  onSkip={(selected) => setSkipTarget(selected)}
                  onOpenApplication={(selected) => navigate(`/applications/${selected.application_id}`)}
                  busyJobId={busy?.id ?? null}
                  busyAction={busy?.action ?? null}
                />
              ))}
            </div>
          )}

          {page ? (
            <Pagination
              page={page.page}
              pageSize={page.page_size || JOBS_PAGE_SIZE}
              total={page.total}
              onPageChange={(next) => {
                setFilter('page', next)
                window.scrollTo({ top: 0, behavior: 'smooth' })
              }}
              disabled={jobsQuery.isFetching}
            />
          ) : null}
        </div>
      </div>

      <JobDetailSheet
        jobId={detailJobId}
        job={detailQuery.data}
        loading={detailQuery.isLoading}
        error={detailQuery.error}
        onRetry={() => void detailQuery.refetch()}
        onOpenChange={(open) => {
          if (!open) setDetailJobId(null)
        }}
        onApply={handleApply}
        onQueue={handleQueue}
        onAnalyze={handleAnalyze}
        onSkip={(job) =>
          setSkipTarget({
            ...job,
            missing_skills: job.missing_skills ?? [],
          })
        }
        onOpenApplication={(applicationId) => {
          setDetailJobId(null)
          navigate(`/applications/${applicationId}`)
        }}
        busy={busy !== null}
      />

      <ReasonDialog
        open={skipTarget !== null}
        onOpenChange={(open) => {
          if (!open) setSkipTarget(null)
        }}
        title="Skip this job?"
        description={
          skipTarget
            ? `"${skipTarget.title}" at ${skipTarget.company?.name ?? 'this company'} will be marked as skipped and hidden from your queue.`
            : undefined
        }
        placeholder="e.g. salary too low, wrong tech stack"
        confirmLabel="Skip job"
        variant="destructive"
        loading={skipJob.isPending}
        onConfirm={handleSkipConfirm}
      />
    </PageContainer>
  )
}
