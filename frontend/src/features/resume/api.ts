/**
 * Resume react-query hooks (`/resumes`).
 *
 * Upload is multipart (`api.upload`); the download endpoint streams a file, so it is a
 * plain async helper rather than a query — nothing should cache a Blob.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, saveBlob } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import type {
  ParsedResume,
  ResumeApplyPlan,
  ResumeApplyRequest,
  ResumeApplyResult,
  ResumeRead,
  ResumeRecommendations,
  ResumeUpdate,
  ResumeVersionRead,
  ResumeVersionScore,
} from '@/types/api'

export const MAX_RESUME_BYTES = 10 * 1024 * 1024
export const ACCEPTED_RESUME_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/msword',
] as const

export interface ResumeUploadInput {
  file: File
  name?: string
  targetRole?: string
  setDefault?: boolean
}

/** `2464` -> `2.4 KB`. Local to this feature; `lib/utils` has no byte formatter. */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || Number.isNaN(bytes)) return '—'
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB']
  let value = bytes / 1024
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unitIndex]}`
}

export function useResumes() {
  return useQuery({
    queryKey: qk.resumes.all,
    queryFn: () => api.get<ResumeRead[]>('/resumes'),
  })
}

export function useResumeVersions(resumeId: string | null) {
  return useQuery({
    queryKey: qk.resumes.versions(resumeId ?? 'none'),
    queryFn: () => api.get<ResumeVersionRead[]>(`/resumes/${resumeId}/versions`),
    enabled: Boolean(resumeId),
  })
}

/**
 * Improvement advice for one resume. The server caches it for ten minutes, so a long
 * client stale time adds nothing; saving parsed data invalidates `['resumes', …]` and
 * with it this query.
 */
export function useResumeRecommendations(resumeId: string | null) {
  return useQuery({
    queryKey: qk.resumes.recommendations(resumeId ?? 'none'),
    queryFn: () => api.get<ResumeRecommendations>(`/resumes/${resumeId}/recommendations`),
    enabled: Boolean(resumeId),
    staleTime: 60_000,
  })
}

/** Re-run the analysis, bypassing the server cache, and swap the result in place. */
export function useRefreshRecommendations() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (resumeId: string) =>
      api.get<ResumeRecommendations>(`/resumes/${resumeId}/recommendations`, { params: { refresh: true } }),
    onSuccess: (data, resumeId) => {
      queryClient.setQueryData(qk.resumes.recommendations(resumeId), data)
      queryClient.setQueryData(qk.resumes.recommendationHistory(resumeId), data.version_history)
      void queryClient.invalidateQueries({ queryKey: qk.resumes.applyPlan(resumeId) })
    },
  })
}

/** Health and average match score per stored version, for the before/after chart. */
export function useRecommendationHistory(resumeId: string | null) {
  return useQuery({
    queryKey: qk.resumes.recommendationHistory(resumeId ?? 'none'),
    queryFn: () => api.get<ResumeVersionScore[]>(`/resumes/${resumeId}/recommendations/history`),
    enabled: Boolean(resumeId),
    staleTime: 60_000,
  })
}

export function useUploadResume() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ file, name, targetRole, setDefault }: ResumeUploadInput) => {
      const form = new FormData()
      form.append('file', file)
      if (name) form.append('name', name)
      if (targetRole) form.append('target_role', targetRole)
      form.append('set_default', String(Boolean(setDefault)))
      return api.upload<ResumeRead>('/resumes', form)
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.resumes.all })
      void queryClient.invalidateQueries({ queryKey: qk.profile.detail })
    },
  })
}

export function useUpdateResume() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...payload }: ResumeUpdate & { id: string }) =>
      api.patch<ResumeRead>(`/resumes/${id}`, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.resumes.all })
    },
  })
}

export function useSaveParsedData() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ParsedResume }) =>
      api.put<ResumeRead>(`/resumes/${id}/parsed-data`, data),
    onSuccess: (_resume, variables) => {
      void queryClient.invalidateQueries({ queryKey: qk.resumes.all })
      void queryClient.invalidateQueries({ queryKey: qk.resumes.versions(variables.id) })
    },
  })
}

export function useReparseResume() {
  const queryClient = useQueryClient()
  return useMutation({
    /** `ai`: the model picked for this re-parse (`GET /ai/choices`); omitted = the routing. */
    mutationFn: (input: string | { id: string; ai?: { provider: string; model: string } }) => {
      const { id, ai } = typeof input === 'string' ? { id: input, ai: undefined } : input
      return api.post<ResumeRead>(`/resumes/${id}/reparse`, ai ? { ai } : undefined)
    },
    onSuccess: (_resume, input) => {
      const id = typeof input === 'string' ? input : input.id
      void queryClient.invalidateQueries({ queryKey: qk.resumes.all })
      void queryClient.invalidateQueries({ queryKey: qk.resumes.versions(id) })
    },
  })
}

export function useDeleteResume() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/resumes/${id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.resumes.all })
    },
  })
}

/** Stream the stored file and hand it to the browser's downloader. */
export async function downloadResume(resume: Pick<ResumeRead, 'id' | 'original_filename'>): Promise<void> {
  const blob = await api.download(`/resumes/${resume.id}/download`)
  saveBlob(blob, resume.original_filename || 'resume')
}

/**
 * What "Apply suggestions" can change on this resume. Built from the (cached)
 * recommendations, so it is cheap; it goes stale whenever the resume or the analysis does.
 */
export function useApplyPlan(resumeId: string | null) {
  return useQuery({
    queryKey: qk.resumes.applyPlan(resumeId ?? 'none'),
    queryFn: () => api.get<ResumeApplyPlan>(`/resumes/${resumeId}/recommendations/apply-plan`),
    enabled: Boolean(resumeId),
    staleTime: 60_000,
  })
}

/**
 * Apply the selected changes and save a new version. The response carries the saved
 * resume and fresh recommendations, so both caches are written directly (no refetch);
 * only the plan and the version list are invalidated.
 */
export function useApplySuggestions(resumeId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ResumeApplyRequest) =>
      api.post<ResumeApplyResult>(`/resumes/${resumeId}/recommendations/apply`, body),
    onSuccess: (result) => {
      queryClient.setQueryData<ResumeRead[]>(qk.resumes.all, (list) =>
        list?.map((item) => (item.id === result.resume.id ? result.resume : item)),
      )
      queryClient.setQueryData(qk.resumes.recommendations(resumeId), result.recommendations)
      queryClient.setQueryData(qk.resumes.recommendationHistory(resumeId), result.recommendations.version_history)
      void queryClient.invalidateQueries({ queryKey: qk.resumes.applyPlan(resumeId) })
      void queryClient.invalidateQueries({ queryKey: qk.resumes.versions(resumeId) })
    },
  })
}
