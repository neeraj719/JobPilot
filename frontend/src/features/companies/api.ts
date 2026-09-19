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
  CompanyListParams,
  CompanyPreferenceRead,
  CompanyPreferenceUpsert,
  CompanyRead,
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
