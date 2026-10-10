/**
 * Interviews feature API — `/interviews/*`.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import type {
  InterviewCreate,
  InterviewListParams,
  InterviewRead,
  InterviewUpdate,
  PageResponse,
} from '@/types/api'

export function useInterviews(params: InterviewListParams = {}) {
  return useQuery({
    queryKey: qk.interviews.list(params),
    queryFn: () => api.get<PageResponse<InterviewRead>>('/interviews', { params: { ...params } }),
  })
}

export function useInterview(id: string | null | undefined) {
  return useQuery({
    queryKey: qk.interviews.detail(id ?? 'none'),
    queryFn: () => api.get<InterviewRead>(`/interviews/${id}`),
    enabled: Boolean(id),
  })
}

function useInterviewMutation<TVariables>(mutationFn: (variables: TVariables) => Promise<InterviewRead>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: (interview) => {
      queryClient.setQueryData(qk.interviews.detail(interview.id), interview)
      void queryClient.invalidateQueries({ queryKey: qk.interviews.all })
      void queryClient.invalidateQueries({ queryKey: qk.applications.detail(interview.application_id) })
      void queryClient.invalidateQueries({ queryKey: qk.dashboard.stats })
    },
  })
}

export function useCreateInterview() {
  return useInterviewMutation((payload: InterviewCreate) => api.post<InterviewRead>('/interviews', payload))
}

export function useUpdateInterview() {
  return useInterviewMutation(({ id, payload }: { id: string; payload: InterviewUpdate }) =>
    api.patch<InterviewRead>(`/interviews/${id}`, payload),
  )
}

/** Generates the AI preparation sheet and stores it on the interview. */
export function useGenerateInterviewPrep() {
  return useInterviewMutation((id: string) => api.post<InterviewRead>(`/interviews/${id}/prep`))
}

export function useDeleteInterview() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/interviews/${id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.interviews.all })
      void queryClient.invalidateQueries({ queryKey: qk.applications.all })
      void queryClient.invalidateQueries({ queryKey: qk.dashboard.stats })
    },
  })
}
