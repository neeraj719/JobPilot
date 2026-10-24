import { Building2, Download, Gauge, LayoutList, PieChart, Target, TrendingUp } from 'lucide-react'
import * as React from 'react'
import { toast } from 'sonner'

import { ErrorState } from '@/components/common/ErrorState'
import { StatCard } from '@/components/common/StatCard'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import {
  conversionByPriority,
  dailySeriesCsv,
  downloadCsv,
  responseRateBySource,
  timeToResponse,
} from '@/features/dashboard/analytics'
import { useApplicationsForAnalytics, useDashboardCharts, useDashboardStats } from '@/features/dashboard/api'
import {
  buildSourceSlices,
  sourceColorMap,
  statusChartColor,
  useChartTheme,
} from '@/features/dashboard/chart-theme'
import {
  MatchDistributionTable,
  PriorityConversionTable,
  SourceRateTable,
  StatusTable,
} from '@/features/dashboard/components/AnalyticsTables'
import { AnalyticsSkeleton } from '@/features/dashboard/components/DashboardSkeleton'
import {
  ApplicationsTrendChart,
  buildTrendSeries,
} from '@/features/dashboard/components/ApplicationsTrendChart'
import { ChartCard } from '@/features/dashboard/components/ChartCard'
import { FunnelChart, FunnelSummary, buildFunnelRows } from '@/features/dashboard/components/FunnelChart'
import { HorizontalBarChart } from '@/features/dashboard/components/HorizontalBarChart'
import { MatchDistributionChart } from '@/features/dashboard/components/MatchDistributionChart'
import { RangeToggle, rangeLabel, useRangeParam } from '@/features/dashboard/components/RangeToggle'
import { SourceDonut } from '@/features/dashboard/components/SourceDonut'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { formatNumber, formatPercent, statusLabel } from '@/lib/utils'

const TOP_COMPANIES = 8

export default function AnalyticsPage() {
  useDocumentTitle('Analytics')

  const [range, setRange] = useRangeParam('30d')
  const charts = useDashboardCharts(range)
  const stats = useDashboardStats()
  const applications = useApplicationsForAnalytics()

  const theme = useChartTheme()
  const chartsData = charts.data
  const chartsRefreshing = charts.isFetching && !charts.isLoading

  const trend = React.useMemo(
    () => buildTrendSeries(chartsData?.applications_per_day ?? [], chartsData?.responses_per_day ?? []),
    [chartsData],
  )
  const funnelRows = React.useMemo(() => buildFunnelRows(chartsData?.funnel ?? []), [chartsData])
  const sourceSlices = React.useMemo(() => buildSourceSlices(chartsData?.by_source, theme), [chartsData, theme])
  const sourceColors = React.useMemo(() => sourceColorMap(sourceSlices), [sourceSlices])
  const companyRows = React.useMemo(
    () => (chartsData?.by_company ?? []).slice(0, TOP_COMPANIES).map((row) => ({ label: row.name, value: row.count })),
    [chartsData],
  )
  const statusRows = React.useMemo(
    () =>
      (chartsData?.by_status ?? []).map((row) => ({
        label: statusLabel(row.status),
        value: row.count,
        color: statusChartColor(row.status, theme),
      })),
    [chartsData, theme],
  )

  const applicationItems = React.useMemo(() => applications.data?.items ?? [], [applications.data])
  const sourceRates = React.useMemo(() => responseRateBySource(applicationItems), [applicationItems])
  const priorityRates = React.useMemo(() => conversionByPriority(applicationItems), [applicationItems])
  const responseTime = React.useMemo(() => timeToResponse(applicationItems), [applicationItems])

  const derivedFromAll = (applications.data?.total ?? 0) <= applicationItems.length
  const derivedNote = derivedFromAll
    ? `Derived from all ${formatNumber(applicationItems.length)} applications.`
    : `Derived from the ${formatNumber(applicationItems.length)} most recent of ${formatNumber(applications.data?.total ?? 0)} applications.`

  const trendHasData = trend.some((point) => point.applications > 0 || point.responses > 0)

  const handleExport = () => {
    if (!chartsData) return
    const csv = dailySeriesCsv(chartsData.applications_per_day, chartsData.responses_per_day)
    downloadCsv(`jobpilot-applications-${range}-${chartsData.end_date ?? 'latest'}.csv`, csv)
    toast.success('CSV downloaded', { description: `Applications and responses per day, ${rangeLabel(range).toLowerCase()}.` })
  }

  // One header for the loading and loaded states (the range toggle works while charts load).
  const header = (
    <PageHeader
      title="Analytics"
      description="Funnel, response rates and where your applications actually go."
      actions={
        <>
          <RangeToggle value={range} onChange={setRange} />
          <Button variant="outline" size="sm" onClick={handleExport} disabled={!chartsData}>
            <Download aria-hidden />
            Export CSV
          </Button>
        </>
      }
    >
      <p className="text-xs text-muted-foreground">
        {rangeLabel(range)}
        {chartsData?.start_date && chartsData?.end_date
          ? ` · ${chartsData.start_date} to ${chartsData.end_date}`
          : ''}
        {' · every chart and table below uses this window unless it says otherwise.'}
      </p>
    </PageHeader>
  )

  if (charts.isLoading && !chartsData) {
    return (
      <PageContainer>
        {header}
        <AnalyticsSkeleton />
      </PageContainer>
    )
  }

  if (charts.isError && !chartsData) {
    return (
      <PageContainer>
        <PageHeader title="Analytics" description="Funnel, response rates and where your applications actually go." />
        <ErrorState error={charts.error} title="Analytics could not load" onRetry={() => void charts.refetch()} />
      </PageContainer>
    )
  }

  return (
    <PageContainer>
      {header}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          title="Response rate"
          value={formatPercent(stats.data?.response_rate ?? 0, 1)}
          loading={stats.isLoading}
          description={`${formatNumber(stats.data?.totals.responses ?? 0)} of ${formatNumber(stats.data?.totals.applications ?? 0)} applications`}
        />
        <StatCard
          title="Interview rate"
          value={formatPercent(stats.data?.interview_rate ?? 0, 1)}
          loading={stats.isLoading}
          description={`${formatNumber(stats.data?.totals.interviews ?? 0)} interviews`}
        />
        <StatCard
          title="Offer rate"
          value={formatPercent(stats.data?.offer_rate ?? 0, 1)}
          loading={stats.isLoading}
          description={`${formatNumber(stats.data?.totals.offers ?? 0)} offers`}
        />
        <StatCard
          title="Days to response"
          value={responseTime.averageDays === null ? '—' : responseTime.averageDays.toFixed(1)}
          loading={applications.isLoading}
          description={
            responseTime.sample === 0
              ? 'No answered applications yet'
              : `Median ${responseTime.medianDays?.toFixed(1) ?? '—'} · ${formatNumber(responseTime.sample)} answered`
          }
        />
      </div>

      <ChartCard
        title="Applications and responses per day"
        description="One scale for both series — they count the same kind of event."
        loading={charts.isLoading && !chartsData}
        refreshing={chartsRefreshing}
        error={charts.isError ? charts.error : undefined}
        onRetry={() => void charts.refetch()}
        empty={!trendHasData}
        emptyIcon={TrendingUp}
        emptyTitle="Nothing sent in this window"
        emptyDescription="Pick a longer range, or submit an application to start the series."
        height={320}
      >
        <ApplicationsTrendChart data={trend} height={320} />
      </ChartCard>

      <div className="grid items-start gap-4 lg:grid-cols-3">
        <ChartCard
          title="Pipeline"
          description="Conversion from one stage to the next."
          refreshing={chartsRefreshing}
          empty={funnelRows.length === 0}
          emptyIcon={LayoutList}
          emptyTitle="No pipeline yet"
          emptyDescription="Run discovery to populate the funnel."
          footer={<FunnelSummary rows={funnelRows} />}
        >
          <FunnelChart rows={funnelRows} />
        </ChartCard>

        <ChartCard
          title="By source"
          description="Submitted applications per platform."
          refreshing={chartsRefreshing}
          empty={sourceSlices.length === 0}
          emptyIcon={PieChart}
          emptyTitle="No submissions yet"
          emptyDescription="Platforms appear here once applications are sent."
        >
          <SourceDonut slices={sourceSlices} />
        </ChartCard>

        <ChartCard
          title="Top companies"
          description="Where the applications went."
          refreshing={chartsRefreshing}
          empty={companyRows.length === 0}
          emptyIcon={Building2}
          emptyTitle="No companies yet"
          emptyDescription="Companies appear after the first submitted application."
        >
          <HorizontalBarChart rows={companyRows} ariaLabel="Applications per company" labelWidth={116} />
        </ChartCard>
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-2">
        <ChartCard
          title="Match-score distribution"
          description="How the analysed jobs score against your resume."
          refreshing={chartsRefreshing}
          empty={(chartsData?.match_distribution ?? []).length === 0}
          emptyIcon={Gauge}
          emptyTitle="Nothing analysed yet"
          emptyDescription="Run matching to score the discovered jobs."
          footer={<MatchDistributionTable rows={chartsData?.match_distribution ?? []} />}
        >
          <MatchDistributionChart rows={chartsData?.match_distribution ?? []} />
        </ChartCard>

        <ChartCard
          title="Applications by status"
          description="Every application in the pipeline, including the ones not yet sent."
          refreshing={chartsRefreshing}
          empty={statusRows.length === 0}
          emptyIcon={LayoutList}
          emptyTitle="Nothing in the pipeline"
          emptyDescription="Queue a job to see it tracked here."
          footer={<StatusTable rows={chartsData?.by_status ?? []} />}
        >
          <HorizontalBarChart rows={statusRows} ariaLabel="Applications per status" labelWidth={128} />
        </ChartCard>
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-2">
        <ChartCard
          title="Response rate by source"
          description={`Which platforms actually reply. ${derivedNote}`}
          loading={applications.isLoading}
          refreshing={applications.isFetching && !applications.isLoading}
          error={applications.isError ? applications.error : undefined}
          onRetry={() => void applications.refetch()}
          empty={sourceRates.length === 0}
          emptyIcon={PieChart}
          emptyTitle="No submitted applications"
          emptyDescription="Response rates need at least one application that was actually sent."
          height={200}
        >
          <SourceRateTable rows={sourceRates} colors={sourceColors} />
        </ChartCard>

        <ChartCard
          title="Conversion by company priority"
          description={`Whether aiming at the P1 list pays off. ${derivedNote}`}
          loading={applications.isLoading}
          refreshing={applications.isFetching && !applications.isLoading}
          error={applications.isError ? applications.error : undefined}
          onRetry={() => void applications.refetch()}
          empty={priorityRates.length === 0}
          emptyIcon={Target}
          emptyTitle="No submitted applications"
          emptyDescription="Priorities compare once applications have been sent."
          height={200}
          footer={
            responseTime.sample > 0 ? (
              <p className="text-xs text-muted-foreground">
                Fastest reply {responseTime.fastestDays?.toFixed(1)} days · slowest{' '}
                {responseTime.slowestDays?.toFixed(1)} days. Measured from submission to the latest recorded
                response, so it is an upper bound on time-to-first-reply.
              </p>
            ) : null
          }
        >
          <PriorityConversionTable rows={priorityRates} />
        </ChartCard>
      </div>
    </PageContainer>
  )
}
