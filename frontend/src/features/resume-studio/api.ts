/**
 * Resume studio hooks: templates, create/import, drafts, versions, diff, history, export
 * and the editor's AI writing help. Keys live under `qk.resumeStudio` (this stream's
 * namespace) and the shared `qk.resumes` keys are invalidated wherever a resume changes,
 * so the existing Resume components stay in sync.
 */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'

import { api, saveBlob } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import type { ResumeRead } from '@/types/api'

import type {
  BulletSuggestions,
  ExportFormat,
  HistoryPage,
  HistoryParams,
  ImprovedText,
  ResumeDiff,
  ResumeDraftRead,
  ResumeSummary,
  ResumeTemplate,
  StudioResume,
  StudioResumeRead,
  SummaryDraft,
  WritingField,
} from './types'

/** Every cache that shows resume data. */
export function invalidateResumeCaches(queryClient: QueryClient, id?: string) {
  void queryClient.invalidateQueries({ queryKey: qk.resumes.all })
  void queryClient.invalidateQueries({ queryKey: ['resume-studio', 'list'] })
  void queryClient.invalidateQueries({ queryKey: ['resume-studio', 'history'] })
  void queryClient.invalidateQueries({ queryKey: qk.resumeStudio.dashboard })
  if (id) {
    void queryClient.invalidateQueries({ queryKey: qk.resumes.versions(id) })
    void queryClient.invalidateQueries({ queryKey: qk.resumeStudio.draft(id) })
  }
}

export function useTemplates() {
  return useQuery({
    queryKey: qk.resumeStudio.templates,
    queryFn: () => api.get<ResumeTemplate[]>('/resumes/templates'),
    staleTime: 60 * 60_000,
  })
}

export function useStudioResumes(includeArchived: boolean) {
  return useQuery({
    queryKey: qk.resumeStudio.list(includeArchived),
    queryFn: () => api.get<StudioResumeRead[]>('/resumes', { params: { include_archived: includeArchived } }),
  })
}

export function useStudioResume(id: string | undefined) {
  return useQuery({
    queryKey: qk.resumes.detail(id ?? 'none'),
    queryFn: () => api.get<StudioResumeRead>(`/resumes/${id}`),
    enabled: Boolean(id),
  })
}

export function useResumeSummary() {
  return useQuery({
    queryKey: qk.resumeStudio.dashboard,
    queryFn: () => api.get<ResumeSummary>('/resumes/summary'),
  })
}

export function usePrefill(enabled: boolean) {
  return useQuery({
    queryKey: qk.resumeStudio.prefill,
    queryFn: () => api.get<StudioResume>('/resumes/prefill'),
    enabled,
    staleTime: 0,
  })
}

export function useDraft(id: string | undefined) {
  return useQuery({
    queryKey: qk.resumeStudio.draft(id ?? 'none'),
    queryFn: () => api.get<ResumeDraftRead>(`/resumes/${id}/draft`),
    enabled: Boolean(id),
    staleTime: 0,
    gcTime: 0,
  })
}

export function useHistory(params: HistoryParams) {
  return useInfiniteQuery({
    queryKey: qk.resumeStudio.history(params),
    queryFn: ({ pageParam }) =>
      api.get<HistoryPage>('/resumes/history', {
        params: { limit: 25, cursor: pageParam ?? undefined, resume_id: params.resume_id, change_source: params.change_source },
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  })
}

export function useVersionDiff(id: string | null, version: number | null, against: number | null) {
  return useQuery({
    queryKey: qk.resumeStudio.versionDiff(id ?? 'none', version ?? 0, against),
    queryFn: () =>
      api.get<ResumeDiff>(`/resumes/${id}/versions/${version}/diff`, { params: { against: against ?? undefined } }),
    enabled: Boolean(id && version),
  })
}

export function useResumeDiff(id: string | null, against: string | null) {
  return useQuery({
    queryKey: qk.resumeStudio.resumeDiff(id ?? 'none', against ?? 'none'),
    queryFn: () => api.get<ResumeDiff>(`/resumes/${id}/diff`, { params: { against: against ?? undefined } }),
    enabled: Boolean(id && against),
  })
}

/* ------------------------------------------------------------------ */
/* writes                                                              */
/* ------------------------------------------------------------------ */

export interface BuildInput {
  name: string
  target_role?: string | null
  template?: string
  parsed_data: StudioResume
  set_default?: boolean
}

export function useBuildResume() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: BuildInput) => api.post<StudioResumeRead>('/resumes/build', body),
    onSuccess: (resume) => invalidateResumeCaches(queryClient, resume.id),
  })
}

export function useImportText() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { text: string; name?: string; target_role?: string | null; template?: string }) =>
      api.post<StudioResumeRead>('/resumes/import/text', body),
    onSuccess: (resume) => invalidateResumeCaches(queryClient, resume.id),
  })
}

export function useImportLinkedin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ files, name, targetRole, template }: { files: File[]; name?: string; targetRole?: string | null; template?: string }) => {
      const form = new FormData()
      for (const file of files) form.append('files', file)
      if (name) form.append('name', name)
      if (targetRole) form.append('target_role', targetRole)
      if (template) form.append('template', template)
      return api.upload<StudioResumeRead>('/resumes/import/linkedin', form)
    },
    onSuccess: (resume) => invalidateResumeCaches(queryClient, resume.id),
  })
}

export function useUpdateStudioResume() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; name?: string; target_role?: string | null; is_default?: boolean; template?: string }) =>
      api.patch<StudioResumeRead>(`/resumes/${id}`, body),
    onSuccess: (resume) => {
      queryClient.setQueryData(qk.resumes.detail(resume.id), resume)
      invalidateResumeCaches(queryClient, resume.id)
    },
  })
}

export function useSaveDraft(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: StudioResume) => api.put<ResumeDraftRead>(`/resumes/${id}/draft`, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.resumeStudio.dashboard })
    },
  })
}

export function useDiscardDraft() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete<ResumeDraftRead>(`/resumes/${id}/draft`),
    onSuccess: (_data, id) => {
      void queryClient.invalidateQueries({ queryKey: qk.resumes.detail(id) })
      invalidateResumeCaches(queryClient, id)
    },
  })
}

export function useSaveVersion(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ data, note, changeSource }: { data: StudioResume; note?: string; changeSource?: 'USER' | 'AI' }) =>
      api.put<StudioResumeRead>(`/resumes/${id}/parsed-data`, { ...data, note: note || undefined, change_source: changeSource }),
    onSuccess: (resume) => {
      queryClient.setQueryData(qk.resumes.detail(resume.id), resume)
      void queryClient.invalidateQueries({ queryKey: qk.resumes.recommendations(resume.id) })
      void queryClient.invalidateQueries({ queryKey: qk.resumes.applyPlan(resume.id) })
      invalidateResumeCaches(queryClient, resume.id)
    },
  })
}

function resumeAction(path: string) {
  return function useAction() {
    const queryClient = useQueryClient()
    return useMutation({
      mutationFn: (id: string) => api.post<StudioResumeRead>(`/resumes/${id}/${path}`),
      onSuccess: (resume) => {
        queryClient.setQueryData(qk.resumes.detail(resume.id), resume)
        invalidateResumeCaches(queryClient, resume.id)
      },
    })
  }
}

export const useArchiveResume = resumeAction('archive')
export const useUnarchiveResume = resumeAction('unarchive')

export function useDuplicateResume() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name?: string }) => api.post<StudioResumeRead>(`/resumes/${id}/duplicate`, { name }),
    onSuccess: (resume) => invalidateResumeCaches(queryClient, resume.id),
  })
}

export function useDeleteStudioResume() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/resumes/${id}`),
    onSuccess: () => invalidateResumeCaches(queryClient),
  })
}

export function useRestoreVersion() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, version }: { id: string; version: number }) =>
      api.post<StudioResumeRead>(`/resumes/${id}/versions/${version}/restore`),
    onSuccess: (resume) => {
      queryClient.setQueryData(qk.resumes.detail(resume.id), resume)
      void queryClient.invalidateQueries({ queryKey: qk.resumes.recommendations(resume.id) })
      invalidateResumeCaches(queryClient, resume.id)
    },
  })
}

/** Download a rendered export (PDF or DOCX). */
export async function exportResume(
  resume: Pick<ResumeRead, 'id' | 'name'>,
  format: ExportFormat,
  options: { template?: string; version?: number } = {},
): Promise<void> {
  const blob = await api.download(`/resumes/${resume.id}/export`, {
    params: { format, template: options.template, version: options.version },
  })
  const suffix = options.version ? ` v${options.version}` : ''
  saveBlob(blob, `${resume.name}${suffix}.${format}`.replace(/[\\/:*?"<>|]+/g, '-'))
}

/* ------------------------------------------------------------------ */
/* AI writing help (nothing is saved; the editor applies to its draft) */
/* ------------------------------------------------------------------ */

export function useRewriteBullet(id: string) {
  return useMutation({
    mutationFn: (body: { text: string; role?: string | null; company?: string | null }) =>
      api.post<BulletSuggestions>(`/resumes/${id}/ai/rewrite-bullet`, body),
  })
}

export function useAchievementBullet(id: string) {
  return useMutation({
    mutationFn: (body: { text: string }) =>
      api.post<BulletSuggestions>(`/resumes/${id}/ai/responsibility-to-achievement`, body),
  })
}

export function useImproveText(id: string) {
  return useMutation({
    mutationFn: (body: { text: string; field: WritingField }) => api.post<ImprovedText>(`/resumes/${id}/ai/improve-text`, body),
  })
}

export function useDraftSummary(id: string) {
  return useMutation({
    mutationFn: (parsed: StudioResume | null) =>
      api.post<SummaryDraft>(`/resumes/${id}/ai/draft-summary`, parsed ? { parsed_data: parsed } : {}),
  })
}
