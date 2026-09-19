/**
 * Emails feature API — `/emails/*` plus the `/integrations` calls the inbox banner needs.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import type {
  ApplicationListParams,
  ApplicationRead,
  AuthorizationUrlResponse,
  EmailClassification,
  EmailListParams,
  EmailMessageRead,
  EmailSimulateRequest,
  IntegrationsOverview,
  PageResponse,
  SyncResult,
  UUID,
} from '@/types/api'

export function useEmails(params: EmailListParams) {
  return useQuery({
    queryKey: qk.emails.list(params),
    queryFn: () => api.get<PageResponse<EmailMessageRead>>('/emails', { params: { ...params } }),
  })
}

/** One email with its untruncated body. */
export function useEmail(id: string | null | undefined) {
  return useQuery({
    queryKey: qk.emails.detail(id ?? 'none'),
    queryFn: () => api.get<EmailMessageRead>(`/emails/${id}`),
    enabled: Boolean(id),
  })
}

export function useIntegrations() {
  return useQuery({
    queryKey: qk.integrations.all,
    queryFn: () => api.get<IntegrationsOverview>('/integrations'),
  })
}

/**
 * Query descriptor for the application pickers, so a single picker can fan out over
 * several statuses with `useQueries` while still sharing the react-query cache.
 */
export function applicationOptionsQuery(params: ApplicationListParams = {}) {
  const merged: ApplicationListParams = { page: 1, page_size: 50, ...params }
  return {
    queryKey: qk.applications.list(merged),
    queryFn: () => api.get<PageResponse<ApplicationRead>>('/applications', { params: { ...merged } }),
  }
}

/**
 * Applications for the "link this email to…" and "which application is this interview
 * for?" pickers. Shared by the emails and interviews pages (same owner).
 */
export function useApplicationOptions(params: ApplicationListParams = {}, options: { enabled?: boolean } = {}) {
  return useQuery({ ...applicationOptionsQuery(params), enabled: options.enabled ?? true })
}

/* ------------------------------------------------------------------ */
/* Mutations                                                           */
/* ------------------------------------------------------------------ */

function useEmailMutation<TVariables>(
  mutationFn: (variables: TVariables) => Promise<EmailMessageRead>,
  options: { touchesApplications?: boolean } = {},
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: (email) => {
      queryClient.setQueryData(qk.emails.detail(email.id), email)
      void queryClient.invalidateQueries({ queryKey: qk.emails.all })
      if (options.touchesApplications) {
        void queryClient.invalidateQueries({ queryKey: qk.applications.all })
        void queryClient.invalidateQueries({ queryKey: qk.interviews.all })
        void queryClient.invalidateQueries({ queryKey: qk.dashboard.stats })
      }
    },
  })
}

export function useMarkEmailRead() {
  return useEmailMutation((id: string) => api.post<EmailMessageRead>(`/emails/${id}/read`))
}

export function useLinkEmail() {
  return useEmailMutation(
    ({ id, applicationId }: { id: string; applicationId: UUID }) =>
      api.post<EmailMessageRead>(`/emails/${id}/link`, { application_id: applicationId }),
    { touchesApplications: true },
  )
}

export function useUnlinkEmail() {
  return useEmailMutation((id: string) => api.post<EmailMessageRead>(`/emails/${id}/unlink`), {
    touchesApplications: true,
  })
}

/** Manual override of the classifier — may move the linked application's status. */
export function useClassifyEmail() {
  return useEmailMutation(
    ({ id, classification }: { id: string; classification: EmailClassification }) =>
      api.post<EmailMessageRead>(`/emails/${id}/classify`, { classification }),
    { touchesApplications: true },
  )
}

/** Demo helper: inject a realistic message without a Gmail connection. */
export function useSimulateEmail() {
  return useEmailMutation((payload: EmailSimulateRequest) => api.post<EmailMessageRead>('/emails/simulate', payload), {
    touchesApplications: true,
  })
}

export function useConnectGmail() {
  return useMutation({
    mutationFn: () => api.post<AuthorizationUrlResponse>('/integrations/gmail/connect'),
  })
}

export function useSyncGmail() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<SyncResult>('/integrations/gmail/sync'),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.emails.all })
      void queryClient.invalidateQueries({ queryKey: qk.integrations.all })
      void queryClient.invalidateQueries({ queryKey: qk.applications.all })
      void queryClient.invalidateQueries({ queryKey: qk.interviews.all })
    },
  })
}
