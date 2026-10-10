/**
 * Automation feature API — react-query hooks for `/automation/*` and the audit trail
 * the Automation page renders next to each run.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import type {
  AuditListParams,
  AuditLogRead,
  AutomationConfigRead,
  AutomationConfigUpdate,
  AutomationRunRead,
  AutomationStatus,
  PageParams,
  PageResponse,
} from '@/types/api'

/** How often a RUNNING run is re-fetched while the pipeline works. */
export const RUN_POLL_INTERVAL_MS = 2_000

export function useAutomationStatus(options: { refetchInterval?: number | false } = {}) {
  return useQuery({
    queryKey: qk.automation.status,
    queryFn: () => api.get<AutomationStatus>('/automation/status'),
    refetchInterval: options.refetchInterval ?? false,
  })
}

export function useAutomationConfig() {
  return useQuery({
    queryKey: qk.automation.config,
    queryFn: () => api.get<AutomationConfigRead>('/automation/config'),
  })
}

export function useAutomationRuns(params: PageParams = {}) {
  return useQuery({
    queryKey: qk.automation.runs(params),
    queryFn: () => api.get<PageResponse<AutomationRunRead>>('/automation/runs', { params: { ...params } }),
  })
}

/**
 * One run. While the run is RUNNING the query re-polls every two seconds so the
 * stepper and the live `current_step` stay in sync with the background thread.
 */
export function useAutomationRun(runId: string | null | undefined, options: { poll?: boolean } = {}) {
  return useQuery({
    queryKey: qk.automation.run(runId ?? 'none'),
    queryFn: () => api.get<AutomationRunRead>(`/automation/runs/${runId}`),
    enabled: Boolean(runId),
    refetchInterval: (query) => {
      if (options.poll === false) return false
      const run = query.state.data as AutomationRunRead | undefined
      return run?.status === 'RUNNING' ? RUN_POLL_INTERVAL_MS : false
    },
  })
}

export function useUpdateAutomationConfig() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: AutomationConfigUpdate) => api.put<AutomationConfigRead>('/automation/config', payload),
    onSuccess: (config) => {
      queryClient.setQueryData(qk.automation.config, config)
      void queryClient.invalidateQueries({ queryKey: qk.automation.status })
    },
  })
}

export function useStartAutomationRun() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (dryRun: boolean) => api.post<AutomationRunRead>('/automation/run', { dry_run: dryRun }),
    onSuccess: (run) => {
      queryClient.setQueryData(qk.automation.run(run.id), run)
      void queryClient.invalidateQueries({ queryKey: ['automation'] })
    },
  })
}

export function useCancelAutomationRun() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (runId: string) => api.post<AutomationRunRead>(`/automation/runs/${runId}/cancel`),
    onSuccess: (run) => {
      queryClient.setQueryData(qk.automation.run(run.id), run)
      void queryClient.invalidateQueries({ queryKey: ['automation'] })
    },
  })
}

/** Audit trail — used both per-run (`automation_run_id`) and globally (`action_prefix`). */
export function useAuditLog(params: AuditListParams, options: { enabled?: boolean; refetchInterval?: number | false } = {}) {
  return useQuery({
    queryKey: qk.audit.list(params),
    queryFn: () => api.get<PageResponse<AuditLogRead>>('/audit', { params: { ...params } }),
    enabled: options.enabled ?? true,
    refetchInterval: options.refetchInterval ?? false,
  })
}
