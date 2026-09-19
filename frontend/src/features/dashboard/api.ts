/**
 * Dashboard + analytics data layer.
 *
 * One react-query hook per endpoint, all keyed off the shared `qk` namespace so any
 * mutation elsewhere in the app can invalidate them. Nothing here formats or derives —
 * derivation lives in `./analytics.ts` so it stays unit-testable.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import type {
  ActivityItem,
  ApplicationRead,
  AutomationRunRead,
  AutomationStatus,
  ChartRange,
  DashboardCharts,
  DashboardStats,
  MatchingSummary,
  PageResponse,
  ReviewCounts,
} from '@/types/api'

/** The hero stats are the page's "is anything happening?" signal — keep them fresh. */
export const STATS_REFETCH_MS = 60_000
/** While a pipeline run is in flight we poll this fast. */
export const RUN_POLL_MS = 2_000
/** `GET /applications` caps `page_size` at 100; analytics derives from that slice. */
export const ANALYTICS_PAGE_SIZE = 100

export function useDashboardStats() {
  return useQuery({
    queryKey: qk.dashboard.stats,
    queryFn: () => api.get<DashboardStats>('/dashboard/stats'),
    refetchInterval: STATS_REFETCH_MS,
  })
}

export function useDashboardCharts(range: ChartRange) {
  return useQuery({
    queryKey: qk.dashboard.charts(range),
    queryFn: () => api.get<DashboardCharts>('/dashboard/charts', { params: { range } }),
    // Hold the previous window on screen while the new one loads — no skeleton flash.
    placeholderData: (previous) => previous,
  })
}

export function useDashboardActivity(limit = 20) {
  return useQuery({
    queryKey: qk.dashboard.activity(limit),
    queryFn: () => api.get<ActivityItem[]>('/dashboard/activity', { params: { limit } }),
  })
}

export function useAutomationStatus(options: { refetchInterval?: number } = {}) {
  return useQuery({
    queryKey: qk.automation.status,
    queryFn: () => api.get<AutomationStatus>('/automation/status'),
    refetchInterval: options.refetchInterval,
  })
}

export function useReviewCounts() {
  return useQuery({
    queryKey: qk.applications.reviewSummary,
    queryFn: () => api.get<ReviewCounts>('/applications/review-summary'),
  })
}

export function useMatchingSummary() {
  return useQuery({
    queryKey: qk.matching.summary,
    queryFn: () => api.get<MatchingSummary>('/matching/summary'),
  })
}

/**
 * The applications slice the analytics page derives its tables from.
 *
 * `GET /dashboard/charts` cannot answer "response rate *by source*" or "interview
 * conversion *by company priority*", so those two tables are computed client-side from
 * one page of applications. Enabled only where it is needed.
 */
export function useApplicationsForAnalytics(enabled = true) {
  return useQuery({
    queryKey: qk.applications.list({ scope: 'analytics', page_size: ANALYTICS_PAGE_SIZE }),
    queryFn: () =>
      api.get<PageResponse<ApplicationRead>>('/applications', {
        params: { page: 1, page_size: ANALYTICS_PAGE_SIZE, sort: 'recent' },
      }),
    enabled,
  })
}

/** Poll one pipeline run until it leaves `RUNNING` (used after "Run now"). */
export function useAutomationRun(runId: string | null) {
  return useQuery({
    queryKey: qk.automation.run(runId ?? 'none'),
    queryFn: () => api.get<AutomationRunRead>(`/automation/runs/${runId}`),
    enabled: Boolean(runId),
    refetchInterval: (query) => (query.state.data?.status === 'RUNNING' ? RUN_POLL_MS : false),
  })
}

/** `POST /automation/run` answers 202 with the RUNNING run; the caller then polls it. */
export function useStartAutomationRun() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: { dry_run?: boolean } = {}) =>
      api.post<AutomationRunRead>('/automation/run', payload),
    onSuccess: (run) => {
      queryClient.setQueryData(qk.automation.run(run.id), run)
      void queryClient.invalidateQueries({ queryKey: qk.automation.status })
    },
  })
}

/** Everything the dashboard shows changes once a run finishes. */
export function useRefreshDashboard() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    void queryClient.invalidateQueries({ queryKey: qk.automation.status })
    void queryClient.invalidateQueries({ queryKey: qk.applications.all })
    void queryClient.invalidateQueries({ queryKey: qk.matching.summary })
    void queryClient.invalidateQueries({ queryKey: qk.notifications.all })
  }
}
