/**
 * Applications feature API — react-query hooks over `/applications*`.
 *
 * Shared by the Applications table, the Approval Center (`/applications/:id`) and the
 * queue page, so every mutation invalidates `qk.applications.all` (which covers the
 * list, the queue and the review summary) and the affected detail key.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import type {
  AnswerUpdate,
  ApplicationAnswerRead,
  ApplicationDetail,
  ApplicationEventRead,
  ApplicationListParams,
  ApplicationPatch,
  ApplicationRead,
  ApplicationStatus,
  CoverLetterRead,
  PageResponse,
  ResumeRead,
  ReviewSummary,
  UUID,
} from '@/types/api'

export interface ReviewCounts {
  pending_review: number
  requires_input: number
  ready_to_submit: number
}

function cleanParams(params: object): Record<string, string | number | boolean> {
  const out: Record<string, string | number | boolean> = {}
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    out[key] = value as string | number | boolean
  }
  return out
}

/* ------------------------------------------------------------------ */
/* queries                                                             */
/* ------------------------------------------------------------------ */

export function useApplications(params: ApplicationListParams) {
  const clean = cleanParams(params)
  return useQuery({
    queryKey: qk.applications.list(clean),
    queryFn: () => api.get<PageResponse<ApplicationRead>>('/applications', { params: clean }),
    placeholderData: (previous) => previous,
  })
}

export interface ApplicationDetailOptions {
  /** Poll while the automation is running, so the Approval Center feels live. */
  refetchInterval?: number | false
}

export function useApplication(id: UUID | null | undefined, options: ApplicationDetailOptions = {}) {
  return useQuery({
    queryKey: qk.applications.detail(id ?? 'none'),
    queryFn: () => api.get<ApplicationDetail>(`/applications/${id}`),
    enabled: Boolean(id),
    // Back off to 15s while the API is unhappy (e.g. rate limited) instead of hammering it.
    refetchInterval: (query) => {
      const base = options.refetchInterval ?? false
      if (base === false) return false
      return query.state.status === 'error' ? Math.max(base * 5, 15_000) : base
    },
    staleTime: 0,
  })
}

export function useApplicationEvents(id: UUID | null | undefined, enabled = true) {
  return useQuery({
    queryKey: qk.applications.events(id ?? 'none'),
    queryFn: () => api.get<ApplicationEventRead[]>(`/applications/${id}/events`),
    enabled: Boolean(id) && enabled,
  })
}

export function useApplicationReview(id: UUID | null | undefined, enabled = true) {
  return useQuery({
    queryKey: [...qk.applications.detail(id ?? 'none'), 'review'] as const,
    queryFn: () => api.get<ReviewSummary>(`/applications/${id}/review`),
    enabled: Boolean(id) && enabled,
  })
}

export function useReviewSummary(refetchInterval?: number | false) {
  return useQuery({
    queryKey: qk.applications.reviewSummary,
    queryFn: () => api.get<ReviewCounts>('/applications/review-summary'),
    refetchInterval: refetchInterval ?? false,
  })
}

/** Read-only list used by the "resume used" selector in the Approval Center. */
export function useResumeOptions(enabled = true) {
  return useQuery({
    queryKey: qk.resumes.all,
    queryFn: () => api.get<ResumeRead[]>('/resumes'),
    enabled,
    staleTime: 5 * 60_000,
  })
}

/* ------------------------------------------------------------------ */
/* mutations                                                           */
/* ------------------------------------------------------------------ */

/** Invalidate everything that can show this application. */
function useApplicationInvalidator() {
  const queryClient = useQueryClient()
  return (id?: UUID) => {
    void queryClient.invalidateQueries({ queryKey: qk.applications.all })
    void queryClient.invalidateQueries({ queryKey: qk.jobs.all })
    void queryClient.invalidateQueries({ queryKey: qk.dashboard.stats })
    if (id) void queryClient.invalidateQueries({ queryKey: qk.applications.detail(id) })
  }
}

export function useStartApplication() {
  const invalidate = useApplicationInvalidator()
  return useMutation({
    mutationFn: (id: UUID) => api.post<ApplicationRead>(`/applications/${id}/start`, { run_in_background: true }),
    onSuccess: (application) => invalidate(application.id),
  })
}

export function useGenerateAnswers() {
  const invalidate = useApplicationInvalidator()
  return useMutation({
    mutationFn: (id: UUID) => api.post<ApplicationAnswerRead[]>(`/applications/${id}/answers/generate`),
    onSuccess: (_answers, id) => invalidate(id),
  })
}

export function useUpdateAnswers() {
  const invalidate = useApplicationInvalidator()
  return useMutation({
    mutationFn: ({ id, answers }: { id: UUID; answers: AnswerUpdate[] }) =>
      api.put<ApplicationAnswerRead[]>(`/applications/${id}/answers`, { answers }),
    onSuccess: (_answers, variables) => invalidate(variables.id),
  })
}

export function useApproveApplication() {
  const invalidate = useApplicationInvalidator()
  return useMutation({
    mutationFn: (id: UUID) => api.post<ApplicationRead>(`/applications/${id}/approve`),
    onSuccess: (application) => invalidate(application.id),
  })
}

export function useResumeAutomation() {
  const invalidate = useApplicationInvalidator()
  return useMutation({
    mutationFn: ({ id, answers }: { id: UUID; answers?: AnswerUpdate[] }) =>
      api.post<ApplicationRead>(`/applications/${id}/resume-automation`, {
        ...(answers && answers.length > 0 ? { answers } : {}),
        run_in_background: true,
      }),
    onSuccess: (application) => invalidate(application.id),
  })
}

export function useSkipApplication() {
  const invalidate = useApplicationInvalidator()
  return useMutation({
    mutationFn: ({ id, reason }: { id: UUID; reason?: string }) =>
      api.post<ApplicationRead>(`/applications/${id}/skip`, { reason: reason ?? null }),
    onSuccess: (application) => invalidate(application.id),
  })
}

export function useWithdrawApplication() {
  const invalidate = useApplicationInvalidator()
  return useMutation({
    mutationFn: ({ id, reason }: { id: UUID; reason?: string }) =>
      api.post<ApplicationRead>(`/applications/${id}/withdraw`, { reason: reason ?? null }),
    onSuccess: (application) => invalidate(application.id),
  })
}

export function useSetApplicationStatus() {
  const invalidate = useApplicationInvalidator()
  return useMutation({
    mutationFn: ({ id, status, note }: { id: UUID; status: ApplicationStatus; note?: string }) =>
      api.patch<ApplicationRead>(`/applications/${id}/status`, { status, note: note ?? null }),
    onSuccess: (application) => {
      invalidate(application.id)
    },
  })
}

export function usePatchApplication() {
  const invalidate = useApplicationInvalidator()
  return useMutation({
    mutationFn: ({ id, patch }: { id: UUID; patch: ApplicationPatch }) =>
      api.patch<ApplicationRead>(`/applications/${id}`, patch),
    onSuccess: (application) => invalidate(application.id),
  })
}

export function useGenerateCoverLetter() {
  const invalidate = useApplicationInvalidator()
  return useMutation({
    mutationFn: (id: UUID) => api.post<CoverLetterRead>(`/applications/${id}/cover-letter`),
    onSuccess: (_result, id) => invalidate(id),
  })
}

export function useSaveCoverLetter() {
  const invalidate = useApplicationInvalidator()
  return useMutation({
    mutationFn: ({ id, content }: { id: UUID; content: string }) =>
      api.put<CoverLetterRead>(`/applications/${id}/cover-letter`, { content }),
    onSuccess: (_result, variables) => invalidate(variables.id),
  })
}

/* ------------------------------------------------------------------ */
/* screenshots                                                         */
/* ------------------------------------------------------------------ */

/**
 * Automation screenshots are behind the auth header, so `<img src>` cannot fetch them
 * directly — pull the PNG as a Blob and hand the component an object URL.
 */
export function useScreenshot(applicationId: UUID | null | undefined, name: string | null | undefined) {
  return useQuery({
    queryKey: ['applications', applicationId ?? 'none', 'screenshot', name ?? 'none'] as const,
    queryFn: () => api.download(`/browser/screenshots/${applicationId}/${name}`),
    enabled: Boolean(applicationId && name),
    staleTime: 10 * 60_000,
    retry: false,
  })
}
