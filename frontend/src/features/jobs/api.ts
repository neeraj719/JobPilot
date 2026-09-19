/**
 * Jobs feature API — react-query hooks over `GET/POST /jobs*`.
 *
 * Every mutation invalidates `qk.jobs.all` so the list, the detail sheet and the
 * dashboard counters stay in step, plus `qk.applications.all` whenever an action
 * creates or changes an application row (queue / skip).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import type {
  AdapterInfo,
  DiscoverRequest,
  DiscoverResult,
  JobCard,
  JobDetail,
  JobListParams,
  JobMatchRead,
  PageResponse,
  QueuedApplicationRead,
  UUID,
} from '@/types/api'

/** Drop empty values so the query key (and URL) stay stable across renders. */
function cleanParams(params: JobListParams): Record<string, string | number | undefined> {
  const out: Record<string, string | number | undefined> = {}
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    out[key] = value as string | number
  }
  return out
}

export function useJobs(params: JobListParams) {
  const clean = cleanParams(params)
  return useQuery({
    queryKey: qk.jobs.list(clean),
    queryFn: () => api.get<PageResponse<JobCard>>('/jobs', { params: clean }),
    placeholderData: (previous) => previous,
  })
}

export function useJob(id: UUID | null | undefined) {
  return useQuery({
    queryKey: qk.jobs.detail(id ?? 'none'),
    queryFn: () => api.get<JobDetail>(`/jobs/${id}`),
    enabled: Boolean(id),
  })
}

export function useJobSources() {
  return useQuery({
    queryKey: qk.jobs.sources,
    queryFn: () => api.get<AdapterInfo[]>('/jobs/sources'),
    staleTime: 5 * 60_000,
  })
}

export function useDiscoverJobs() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: DiscoverRequest = {}) => api.post<DiscoverResult>('/jobs/discover', body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.jobs.all })
      void queryClient.invalidateQueries({ queryKey: qk.matching.summary })
      void queryClient.invalidateQueries({ queryKey: qk.dashboard.stats })
    },
  })
}

export function useAnalyzeJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ jobId, resumeId }: { jobId: UUID; resumeId?: UUID }) =>
      api.post<JobMatchRead>(`/jobs/${jobId}/analyze`, undefined, {
        params: resumeId ? { resume_id: resumeId } : undefined,
      }),
    onSuccess: (_match, variables) => {
      void queryClient.invalidateQueries({ queryKey: qk.jobs.all })
      void queryClient.invalidateQueries({ queryKey: qk.jobs.detail(variables.jobId) })
    },
  })
}

export function useQueueJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (jobId: UUID) => api.post<QueuedApplicationRead>(`/jobs/${jobId}/queue`),
    onSuccess: (_application, jobId) => {
      void queryClient.invalidateQueries({ queryKey: qk.jobs.all })
      void queryClient.invalidateQueries({ queryKey: qk.jobs.detail(jobId) })
      void queryClient.invalidateQueries({ queryKey: qk.applications.all })
    },
  })
}

export function useSkipJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ jobId, reason }: { jobId: UUID; reason?: string }) =>
      api.post<QueuedApplicationRead>(`/jobs/${jobId}/skip`, { reason: reason ?? null }),
    onSuccess: (_application, variables) => {
      void queryClient.invalidateQueries({ queryKey: qk.jobs.all })
      void queryClient.invalidateQueries({ queryKey: qk.jobs.detail(variables.jobId) })
      void queryClient.invalidateQueries({ queryKey: qk.applications.all })
    },
  })
}
