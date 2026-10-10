/**
 * Company directory + company-priority hooks (`/companies`, `/companies/preferences`).
 *
 * Priority is a *queue ordering* signal only — the matching engine never inflates a score
 * because a company is P1. Both the board and the directory write through the same two
 * endpoints: `PUT` replaces the whole list, `POST` upserts a single row.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import type {
  BoardDetectRequest,
  BoardDetection,
  CompanyBoardResult,
  CompanyBoardUpdate,
  CompanyCreate,
  CompanyDetectResult,
  CompanyListParams,
  CompanyPreferenceRead,
  CompanyPreferenceUpsert,
  CompanyRead,
  CompanySuggestions,
  OkResponse,
  PageResponse,
} from '@/types/api'

export function useCompanies(params: CompanyListParams) {
  return useQuery({
    queryKey: qk.companies.list(params),
    queryFn: () => api.get<PageResponse<CompanyRead>>('/companies', { params: { ...params } }),
  })
}

/** Name suggestions for the "add company" input; disabled until the user types. */
export function useCompanySuggestions(query: string, enabled = true) {
  return useQuery({
    queryKey: qk.companies.list({ suggest: query }),
    queryFn: () => api.get<PageResponse<CompanyRead>>('/companies', { params: { q: query, page_size: 8 } }),
    enabled: enabled && query.trim().length >= 2,
    staleTime: 60_000,
  })
}

export function useCompanyPreferences() {
  return useQuery({
    queryKey: qk.companies.preferences,
    queryFn: () => api.get<CompanyPreferenceRead[]>('/companies/preferences'),
  })
}

/** Replace the whole priority list (the board's Save button). */
export function useReplaceCompanyPreferences() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (items: CompanyPreferenceUpsert[]) =>
      api.put<CompanyPreferenceRead[]>('/companies/preferences', { items }),
    onSuccess: (preferences) => {
      queryClient.setQueryData(qk.companies.preferences, preferences)
      void queryClient.invalidateQueries({ queryKey: qk.companies.all })
      void queryClient.invalidateQueries({ queryKey: qk.jobs.all })
    },
  })
}

/** Add or update one company priority (the directory's inline select). */
export function useUpsertCompanyPreference() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: CompanyPreferenceUpsert) =>
      api.post<CompanyPreferenceRead>('/companies/preferences', payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.companies.all })
      void queryClient.invalidateQueries({ queryKey: qk.jobs.all })
    },
  })
}

export function useDeleteCompanyPreference() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (preferenceId: string) => api.delete<OkResponse>(`/companies/preferences/${preferenceId}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.companies.all })
      void queryClient.invalidateQueries({ queryKey: qk.jobs.all })
    },
  })
}

/**
 * Add a company by name. With a `board_url` the board is verified server-side first;
 * without one (and `auto_detect`, the default) the server looks the board up and the
 * response carries the `detection`.
 */
export function useCreateCompany() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: CompanyCreate) => api.post<CompanyDetectResult>('/companies', payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.companies.all })
      void queryClient.invalidateQueries({ queryKey: qk.jobs.all })
    },
  })
}

/** Look a career board up by name / website without saving anything (`POST /companies/detect-board`). */
export function useDetectBoard() {
  return useMutation({
    mutationFn: (payload: BoardDetectRequest) => api.post<BoardDetection>('/companies/detect-board', payload),
  })
}

/** Re-run board detection for an existing company and save what is found. */
export function useDetectCompanyBoard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (companyId: string) => api.post<CompanyDetectResult>(`/companies/${companyId}/detect-board`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.companies.all })
      void queryClient.invalidateQueries({ queryKey: qk.jobs.all })
    },
  })
}

/** Known-board companies for the "Quick start" panel (`GET /companies/suggestions`). */
export function useQuickStartSuggestions(limit = 20) {
  return useQuery({
    queryKey: [...qk.companies.all, 'suggestions', limit] as const,
    queryFn: () => api.get<CompanySuggestions>('/companies/suggestions', { params: { limit } }),
    staleTime: 60_000,
  })
}

/**
 * Verify and save a company's public job board. The server fetches the board once and
 * answers 422 `board_not_found` when it does not exist or is empty.
 */
export function useSetCompanyBoard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ companyId, ...body }: CompanyBoardUpdate & { companyId: string }) =>
      api.put<CompanyBoardResult>(`/companies/${companyId}/board`, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.companies.all })
      void queryClient.invalidateQueries({ queryKey: qk.jobs.all })
    },
  })
}

/** Stop reading a company's job board. */
export function useClearCompanyBoard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (companyId: string) => api.delete<CompanyRead>(`/companies/${companyId}/board`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.companies.all })
    },
  })
}
