/**
 * ATS optimizer react-query hooks (`/ats/*`).
 *
 * Analyses are polled while the model polishes their suggestions (`status === 'RUNNING'`);
 * the deterministic result is shown at once. Every write that changes a resume invalidates
 * the resume caches too, so My Resumes and the version history stay in step.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, saveBlob } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import type { PageResponse, UUID } from '@/types/api'
import type {
  AnalysisCreate,
  AnalysisListItem,
  ApplyResult,
  AtsAnalysis,
  AtsSummary,
  AutoOptimizeResult,
  BoardPostingRef,
  CompanyLookupResult,
  CompareResult,
  JdParseResult,
  JobTarget,
  JobTargetDetail,
  Methodology,
  SnapshotCreate,
  SnapshotResult,
  TailorResult,
  TargetCreate,
  TargetListParams,
  TargetUpdate,
  UndoResult,
} from '@/features/ats/types'

const POLL_MS = 1500

/* ------------------------------------------------------------------ methodology + JD */

export function useMethodology() {
  return useQuery({
    queryKey: qk.ats.methodology,
    queryFn: () => api.get<Methodology>('/ats/methodology'),
    staleTime: 60 * 60_000,
  })
}

export function useParseJd() {
  return useMutation({
    mutationFn: (body: { text: string; title?: string; company?: string; use_ai?: boolean }) =>
      api.post<JdParseResult>('/ats/jd/parse', body),
  })
}

export function useUploadJd() {
  return useMutation({
    mutationFn: ({ file, company, title, useAi }: { file: File; company?: string; title?: string; useAi?: boolean }) => {
      const form = new FormData()
      form.append('file', file)
      if (company) form.append('company', company)
      if (title) form.append('title', title)
      form.append('use_ai', String(Boolean(useAi)))
      return api.upload<JdParseResult>('/ats/jd/upload', form)
    },
  })
}

export function useFetchJd() {
  return useMutation({
    mutationFn: (body: { url?: string; board?: BoardPostingRef; use_ai?: boolean }) =>
      api.post<JdParseResult>('/ats/jd/fetch', body),
  })
}

export function useCompanyLookup() {
  return useMutation({
    mutationFn: ({ name, role }: { name: string; role?: string }) =>
      api.get<CompanyLookupResult>('/ats/companies/lookup', { params: { name, role: role || undefined } }),
  })
}

/* ------------------------------------------------------------------ analyses */

function isRunning(analysis: AtsAnalysis | undefined): boolean {
  return analysis?.status === 'RUNNING' || analysis?.status === 'PENDING'
}

export function useAnalysis(id: UUID | null | undefined) {
  return useQuery({
    queryKey: qk.ats.analysis(id ?? 'none'),
    queryFn: () => api.get<AtsAnalysis>(`/ats/analyses/${id}`),
    enabled: Boolean(id),
    refetchInterval: (query) => (isRunning(query.state.data as AtsAnalysis | undefined) ? POLL_MS : false),
  })
}

export function useAnalyses(params: { resume_id?: UUID; job_target_id?: UUID; limit?: number }) {
  return useQuery({
    queryKey: qk.ats.analyses(params),
    queryFn: () => api.get<AnalysisListItem[]>('/ats/analyses', { params }),
  })
}

function useResumeInvalidation() {
  const queryClient = useQueryClient()
  return (resumeId?: string) => {
    void queryClient.invalidateQueries({ queryKey: qk.resumes.all })
    void queryClient.invalidateQueries({ queryKey: qk.resumeStudio.all })
    if (resumeId) void queryClient.invalidateQueries({ queryKey: qk.resumes.versions(resumeId) })
    void queryClient.invalidateQueries({ queryKey: ['ats', 'analyses', 'list'] })
    void queryClient.invalidateQueries({ queryKey: qk.ats.summary })
  }
}

export function useCreateAnalysis() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: AnalysisCreate) => api.post<AtsAnalysis>('/ats/analyses', body),
    onSuccess: (analysis) => {
      queryClient.setQueryData(qk.ats.analysis(analysis.id), analysis)
      void queryClient.invalidateQueries({ queryKey: ['ats', 'analyses', 'list'] })
      void queryClient.invalidateQueries({ queryKey: ['ats', 'targets'] })
      void queryClient.invalidateQueries({ queryKey: qk.ats.summary })
    },
  })
}

export function useApplySuggestions(analysisId: UUID) {
  const queryClient = useQueryClient()
  const invalidate = useResumeInvalidation()
  return useMutation({
    mutationFn: (body: { suggestion_ids: UUID[]; edits?: Record<UUID, string> }) =>
      api.post<ApplyResult>(`/ats/analyses/${analysisId}/apply`, body),
    onSuccess: (result) => {
      queryClient.setQueryData(qk.ats.analysis(result.analysis.id), result.analysis)
      void queryClient.invalidateQueries({ queryKey: qk.ats.analysis(analysisId) })
      void queryClient.invalidateQueries({ queryKey: ['ats', 'targets'] })
      invalidate(result.resume.id)
    },
  })
}

export function useIgnoreSuggestions(analysisId: UUID) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { suggestion_ids: UUID[]; ignore?: boolean }) =>
      api.post<AtsAnalysis>(`/ats/analyses/${analysisId}/ignore`, body),
    onSuccess: (analysis) => queryClient.setQueryData(qk.ats.analysis(analysis.id), analysis),
  })
}

export function useAutoOptimize(analysisId: UUID) {
  const queryClient = useQueryClient()
  const invalidate = useResumeInvalidation()
  return useMutation({
    mutationFn: (body: { mode: 'new_resume' | 'new_version'; name?: string }) =>
      api.post<AutoOptimizeResult>(`/ats/analyses/${analysisId}/auto-optimize`, body),
    onSuccess: (result) => {
      queryClient.setQueryData(qk.ats.analysis(result.analysis.id), result.analysis)
      void queryClient.invalidateQueries({ queryKey: ['ats', 'targets'] })
      invalidate(result.resume.id)
    },
  })
}

export function useUndoApply() {
  const queryClient = useQueryClient()
  const invalidate = useResumeInvalidation()
  return useMutation({
    mutationFn: (analysisId: UUID) => api.post<UndoResult>(`/ats/analyses/${analysisId}/undo`),
    onSuccess: (result) => {
      queryClient.setQueryData(qk.ats.analysis(result.analysis.id), result.analysis)
      invalidate(result.resume.id)
    },
  })
}

export function useRetryPolish(analysisId: UUID) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<AtsAnalysis>(`/ats/analyses/${analysisId}/polish`),
    onSuccess: (analysis) => queryClient.setQueryData(qk.ats.analysis(analysis.id), analysis),
  })
}

/* ------------------------------------------------------------------ targets */

export function useTargets(params: TargetListParams) {
  const clean = Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== '' && !(Array.isArray(v) && v.length === 0)))
  return useQuery({
    queryKey: qk.ats.targets(clean),
    queryFn: () => api.get<PageResponse<JobTarget>>('/ats/targets', { params: clean as Record<string, string | number | string[]> }),
    placeholderData: (previous) => previous,
  })
}

export function useTarget(id: UUID | null | undefined) {
  return useQuery({
    queryKey: qk.ats.target(id ?? 'none'),
    queryFn: () => api.get<JobTargetDetail>(`/ats/targets/${id}`),
    enabled: Boolean(id),
  })
}

function useTargetInvalidation() {
  const queryClient = useQueryClient()
  return (detail?: JobTargetDetail | JobTarget) => {
    if (detail && 'activity' in detail) queryClient.setQueryData(qk.ats.target(detail.id), detail)
    else if (detail) void queryClient.invalidateQueries({ queryKey: qk.ats.target(detail.id) })
    void queryClient.invalidateQueries({ queryKey: ['ats', 'targets'] })
    void queryClient.invalidateQueries({ queryKey: qk.ats.summary })
  }
}

export function useCreateTarget() {
  const invalidate = useTargetInvalidation()
  return useMutation({
    mutationFn: (body: TargetCreate) => api.post<JobTargetDetail>('/ats/targets', body),
    onSuccess: (detail) => invalidate(detail),
  })
}

export function useUpdateTarget(id: UUID) {
  const invalidate = useTargetInvalidation()
  return useMutation({
    mutationFn: (body: TargetUpdate) => api.patch<JobTargetDetail>(`/ats/targets/${id}`, body),
    onSuccess: (detail) => invalidate(detail),
  })
}

export function useDeleteTarget() {
  const invalidate = useTargetInvalidation()
  return useMutation({
    mutationFn: (id: UUID) => api.delete(`/ats/targets/${id}`),
    onSuccess: () => invalidate(),
  })
}

export function useAddSnapshot(id: UUID) {
  const invalidate = useTargetInvalidation()
  return useMutation({
    mutationFn: (body: SnapshotCreate) => api.post<SnapshotResult>(`/ats/targets/${id}/snapshot`, body),
    onSuccess: (result) => invalidate(result.target),
  })
}

export function useUploadSnapshot(id: UUID) {
  const invalidate = useTargetInvalidation()
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return api.upload<SnapshotResult>(`/ats/targets/${id}/snapshot/upload`, form)
    },
    onSuccess: (result) => invalidate(result.target),
  })
}

export function useRefreshTarget(id: UUID) {
  const invalidate = useTargetInvalidation()
  return useMutation({
    mutationFn: () => api.post<SnapshotResult>(`/ats/targets/${id}/refresh`),
    onSuccess: (result) => invalidate(result.target),
  })
}

export function useTailor(id: UUID) {
  const queryClient = useQueryClient()
  const invalidate = useResumeInvalidation()
  const invalidateTarget = useTargetInvalidation()
  return useMutation({
    mutationFn: (body: { source_resume_id?: UUID; name?: string }) => api.post<TailorResult>(`/ats/targets/${id}/tailor`, body),
    onSuccess: (result) => {
      queryClient.setQueryData(qk.ats.analysis(result.analysis.id), result.analysis)
      void queryClient.invalidateQueries({ queryKey: qk.ats.compare(id) })
      invalidateTarget(result.target)
      invalidate(result.resume.id)
    },
  })
}

export function useCompare(id: UUID | null | undefined, enabled = true) {
  return useQuery({
    queryKey: qk.ats.compare(id ?? 'none'),
    queryFn: () => api.get<CompareResult>(`/ats/targets/${id}/compare`),
    enabled: Boolean(id) && enabled,
  })
}

/**
 * Download the resume-builder's rendered export (plan contract 2:
 * `GET /resumes/{id}/export?format=pdf|docx`).
 */
export async function downloadResumeExport(resume: { id: UUID; name: string }, format: 'pdf' | 'docx'): Promise<void> {
  const blob = await api.download(`/resumes/${resume.id}/export`, { params: { format } })
  saveBlob(blob, `${resume.name}.${format}`.replace(/[\\/:*?"<>|]+/g, '-'))
}

export function useAtsSummary() {
  return useQuery({
    queryKey: qk.ats.summary,
    queryFn: () => api.get<AtsSummary>('/ats/summary'),
  })
}
