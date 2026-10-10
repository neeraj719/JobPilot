import { Building2, History, LayoutList, PieChart, RefreshCw, TrendingUp } from 'lucide-react'
import * as React from 'react'
import { Link } from 'react-router-dom'

import { ErrorState } from '@/components/common/ErrorState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  useDashboardActivity,
  useDashboardCharts,
  useDashboardStats,
  useAutomationStatus,
  useRefreshDashboard,
  useReviewCounts,
} from '@/features/dashboard/api'
import { buildSourceSlices, statusChartColor, useChartTheme } from '@/features/dashboard/chart-theme'
import { ActivityTimeline, filterActivity } from '@/features/dashboard/components/ActivityTimeline'
import {
  ApplicationsTrendChart,
  buildTrendSeries,
} from '@/features/dashboard/components/ApplicationsTrendChart'
import { AttentionPanel } from '@/features/dashboard/components/AttentionPanel'
import { AutomationCard } from '@/features/dashboard/components/AutomationCard'
import { ChartCard } from '@/features/dashboard/components/ChartCard'
import { DashboardSkeleton } from '@/features/dashboard/components/DashboardSkeleton'
import { FunnelChart, FunnelSummary, buildFunnelRows } from '@/features/dashboard/components/FunnelChart'
import { HeroStats } from '@/features/dashboard/components/HeroStats'
import { HorizontalBarChart } from '@/features/dashboard/components/HorizontalBarChart'
import { RangeToggle, rangeLabel, useRangeParam } from '@/features/dashboard/components/RangeToggle'
import { SourceDonut } from '@/features/dashboard/components/SourceDonut'
import { TodayCard } from '@/features/dashboard/components/TodayCard'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { formatRelative, statusLabel } from '@/lib/utils'

const ACTIVITY_FETCH_LIMIT = 60
const ACTIVITY_VISIBLE = 10
const TOP_COMPANIES = 8

export default function DashboardPage() {
  useDocumentTitle('Dashboard')

  const [range, setRange] = useRangeParam('30d')
  const [showAllActivity, setShowAllActivity] = React.useState(false)

  const stats = useDashboardStats()
  const charts = useDashboardCharts(range)
  const activity = useDashboardActivity(ACTIVITY_FETCH_LIMIT)
  const review = useReviewCounts()
  const automation = useAutomationStatus({ refetchInterval: 60_000 })
  const refreshDashboard = useRefreshDashboard()

  const theme = useChartTheme()

  const chartsData = charts.data
  const chartsRefreshing = charts.isFetching && !charts.isLoading

  const trend = React.useMemo(
    () => buildTrendSeries(chartsData?.applications_per_day ?? [], chartsData?.responses_per_day ?? []),
    [chartsData],
  )
  const funnelRows = React.useMemo(() => buildFunnelRows(chartsData?.funnel ?? []), [chartsData])
  const sourceSlices = React.useMemo(() => buildSourceSlices(chartsData?.by_source, theme), [chartsData, theme])
  const companyRows = React.useMemo(
    () =>
      (chartsData?.by_company ?? [])
        .slice(0, TOP_COMPANIES)
        .map((row) => ({ label: row.name, value: row.count })),
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
  const activityItems = React.useMemo(
    () => filterActivity(activity.data, showAllActivity),
    [activity.data, showAllActivity],
  )

  const trendHasData = trend.some((point) => point.applications > 0 || point.responses > 0)

  if (stats.isLoading) {
    return (
      <PageContainer>
        <PageHeader
          title="Dashboard"
          description="Today at a glance: what was found, what was sent and what needs you."
        />
        <DashboardSkeleton />
      </PageContainer>
    )
  }

  if (stats.isError) {
    return (
      <PageContainer>
        <PageHeader
          title="Dashboard"
          description="Today at a glance: what was found, what was sent and what needs you."
        />
        <ErrorState
          error={stats.error}
          title="The dashboard could not load"
          onRetry={() => void stats.refetch()}
        />
      </PageContainer>
    )
  }

  return (
    <PageContainer>
      <PageHeader
        title="Dashboard"
        description="Today at a glance: what was found, what was sent and what needs you."
        actions={
          <>
            <span className="hidden text-xs text-muted-foreground sm:inline">
              Updated {formatRelative(stats.dataUpdatedAt)}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={refreshDashboard}
              loading={stats.isFetching && !stats.isLoading}
            >
              {!(stats.isFetching && !stats.isLoading) ? <RefreshCw aria-hidden /> : null}
              Refresh
            </Button>
          </>
        }
      />

      <HeroStats stats={stats.data} review={review.data} />

      <div className="grid gap-4 lg:grid-cols-3">
        <AttentionPanel items={stats.data?.attention ?? []} />
        {stats.data ? (
          <TodayCard stats={stats.data.today} description="Everything that moved since midnight." />
        ) : null}
        <AutomationCard status={automation.data} />
      </div>

      {/* One filter row, above everything it scopes — every chart below uses this window. */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-6">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Trends</h2>
          <p className="text-sm text-muted-foreground">
            {rangeLabel(range)}
            {chartsData?.start_date && chartsData?.end_date
              ? ` · ${chartsData.start_date} to ${chartsData.end_date}`
              : ''}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <RangeToggle value={range} onChange={setRange} />
          <Button asChild variant="ghost" size="sm">
            <Link to={`/analytics?range=${range}`}>Full analytics</Link>
          </Button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <ChartCard
          className="lg:col-span-2"
          title="Applications and responses per day"
          description="Both series count events per day, so they share one scale."
          loading={charts.isLoading}
          refreshing={chartsRefreshing}
          error={charts.isError ? charts.error : undefined}
          onRetry={() => void charts.refetch()}
          empty={!trendHasData}
          emptyIcon={TrendingUp}
          emptyTitle="Nothing sent in this window"
          emptyDescription="Pick a longer range, or queue and submit an application to start the series."
          height={260}
        >
          <ApplicationsTrendChart data={trend} />
        </ChartCard>

        <ChartCard
          title="Pipeline"
          description="Where every discovered job ends up."
          loading={charts.isLoading}
          refreshing={chartsRefreshing}
          error={charts.isError ? charts.error : undefined}
          onRetry={() => void charts.refetch()}
          empty={funnelRows.length === 0}
          emptyIcon={LayoutList}
          emptyTitle="No pipeline yet"
          emptyDescription="Run discovery to populate the funnel."
          height={260}
          footer={<FunnelSummary rows={funnelRows} />}
        >
          <FunnelChart rows={funnelRows} />
        </ChartCard>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <ChartCard
          title="By source"
          description="Submitted applications per platform."
          loading={charts.isLoading}
          refreshing={chartsRefreshing}
          error={charts.isError ? charts.error : undefined}
          onRetry={() => void charts.refetch()}
          empty={sourceSlices.length === 0}
          emptyIcon={PieChart}
          emptyTitle="No submissions yet"
          emptyDescription="Once applications are sent, this shows which platforms they went through."
          height={240}
        >
          <SourceDonut slices={sourceSlices} />
        </ChartCard>

        <ChartCard
          title="Top companies"
          description={`Most-applied companies, ${rangeLabel(range).toLowerCase()}.`}
          loading={charts.isLoading}
          refreshing={chartsRefreshing}
          error={charts.isError ? charts.error : undefined}
          onRetry={() => void charts.refetch()}
          empty={companyRows.length === 0}
          emptyIcon={Building2}
          emptyTitle="No companies yet"
          emptyDescription="Companies appear here after the first application is submitted."
        >
          <HorizontalBarChart rows={companyRows} ariaLabel="Applications per company" labelWidth={116} />
        </ChartCard>

        <ChartCard
          title="Status breakdown"
          description="Every application in the pipeline, including the ones not yet sent."
          loading={charts.isLoading}
          refreshing={chartsRefreshing}
          error={charts.isError ? charts.error : undefined}
          onRetry={() => void charts.refetch()}
          empty={statusRows.length === 0}
          emptyIcon={LayoutList}
          emptyTitle="Nothing in the pipeline"
          emptyDescription="Queue a job to see it tracked here."
        >
          <HorizontalBarChart rows={statusRows} ariaLabel="Applications per status" labelWidth={128} />
        </ChartCard>
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2 text-base">
              <History className="size-4 text-muted-foreground" aria-hidden />
              Recent activity
            </CardTitle>
            <CardDescription>
              {showAllActivity
                ? 'Everything in the audit log, newest first.'
                : 'Application and automation events. Sign-ins and per-job scoring are hidden.'}
            </CardDescription>
          </div>
          <Button variant="ghost" size="sm" onClick={() => setShowAllActivity((value) => !value)}>
            {showAllActivity ? 'Key events only' : 'Show everything'}
          </Button>
        </CardHeader>
        <CardContent>
          {activity.isError ? (
            <ErrorState
              size="sm"
              error={activity.error}
              title="Activity could not load"
              onRetry={() => void activity.refetch()}
            />
          ) : activity.isLoading ? (
            <div className="space-y-3" aria-busy="true">
              {Array.from({ length: 5 }, (_, index) => (
                <div key={index} className="flex animate-pulse items-center gap-3">
                  <div className="size-8 shrink-0 rounded-full bg-muted" />
                  <div className="flex-1 space-y-2">
                    <div className="h-3 w-1/3 rounded bg-muted" />
                    <div className="h-3 w-2/3 rounded bg-muted" />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <ActivityTimeline items={activityItems} limit={ACTIVITY_VISIBLE} />
          )}
        </CardContent>
      </Card>
    </PageContainer>
  )
}
