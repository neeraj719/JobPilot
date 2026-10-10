/**
 * Settings hooks: automation config, integrations (Gmail + platform accounts), AI status,
 * browser sessions and the password change.
 *
 * `qk` covers automation and integrations; the AI/browser status endpoints are read only
 * here, so their keys live in `settingsKeys` rather than in the shared key registry.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, reauthHeaders } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import type {
  AiStatus,
  AuthorizationUrlResponse,
  AutomationConfigRead,
  AutomationConfigUpdate,
  BrowserSessionRead,
  BrowserStatus,
  ChangePasswordRequest,
  ConnectedAccountCreate,
  ConnectedAccountRead,
  GmailStatus,
  IntegrationsOverview,
  OkResponse,
  RememberDeviceRequest,
  SessionRead,
  SessionsRevoked,
  SyncResult,
} from '@/types/api'

export const settingsKeys = {
  aiStatus: ['ai', 'status'] as const,
  browserStatus: ['browser', 'status'] as const,
  browserSessions: ['browser', 'sessions'] as const,
  /** Signed-in sessions of the user's own account (Settings → Security). */
  authSessions: ['auth', 'sessions'] as const,
}

/* ------------------------------------------------------------------ */
/* Automation config                                                   */
/* ------------------------------------------------------------------ */

export function useAutomationConfig() {
  return useQuery({
    queryKey: qk.automation.config,
    queryFn: () => api.get<AutomationConfigRead>('/automation/config'),
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

/* ------------------------------------------------------------------ */
/* Integrations                                                        */
/* ------------------------------------------------------------------ */

export function useIntegrations() {
  return useQuery({
    queryKey: qk.integrations.all,
    queryFn: () => api.get<IntegrationsOverview>('/integrations'),
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
      void queryClient.invalidateQueries({ queryKey: qk.integrations.all })
      void queryClient.invalidateQueries({ queryKey: qk.emails.all })
      void queryClient.invalidateQueries({ queryKey: qk.applications.all })
    },
  })
}

export function useDisconnectGmail() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.delete<GmailStatus>('/integrations/gmail'),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.integrations.all })
    },
  })
}

export function useConnectAccount() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: ConnectedAccountCreate) =>
      api.post<ConnectedAccountRead>('/integrations/accounts', payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.integrations.all })
    },
  })
}

export function useDisconnectAccount() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (accountId: string) => api.delete<OkResponse>(`/integrations/accounts/${accountId}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.integrations.all })
    },
  })
}

/* ------------------------------------------------------------------ */
/* AI + browser                                                        */
/* ------------------------------------------------------------------ */

export function useAiStatus() {
  return useQuery({
    queryKey: settingsKeys.aiStatus,
    queryFn: () => api.get<AiStatus>('/ai/status'),
    staleTime: 5 * 60_000,
  })
}

export function useBrowserStatus() {
  return useQuery({
    queryKey: settingsKeys.browserStatus,
    queryFn: () => api.get<BrowserStatus>('/browser/status'),
    staleTime: 5 * 60_000,
  })
}

export function useBrowserSessions() {
  return useQuery({
    queryKey: settingsKeys.browserSessions,
    queryFn: () => api.get<BrowserSessionRead[]>('/browser/sessions'),
  })
}

export function useRevokeBrowserSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (sessionId: string) => api.delete(`/browser/sessions/${sessionId}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: settingsKeys.browserSessions })
    },
  })
}

/* ------------------------------------------------------------------ */
/* Security                                                            */
/* ------------------------------------------------------------------ */

export function useChangePassword() {
  const queryClient = useQueryClient()
  return useMutation({
    // The current password doubles as the re-authentication proof, so an access token
    // older than 10 minutes does not need a second prompt. Nothing keeps it afterwards.
    mutationFn: (payload: ChangePasswordRequest) =>
      api.put<OkResponse>('/auth/me/password', payload, { headers: reauthHeaders(payload.current_password) }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: settingsKeys.authSessions })
    },
  })
}

/* ------------------------------------------------------------------ */
/* Sessions and devices                                                */
/* ------------------------------------------------------------------ */

/** Optional password for a sensitive action, asked for only after `reauth_required`. */
interface Reauth {
  password?: string
}

function reauthOptions({ password }: Reauth) {
  return password ? { headers: reauthHeaders(password) } : {}
}

export function useAuthSessions() {
  return useQuery({
    queryKey: settingsKeys.authSessions,
    queryFn: () => api.get<SessionRead[]>('/auth/sessions'),
  })
}

export function useRevokeAuthSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...reauth }: { id: string } & Reauth) =>
      api.delete<SessionsRevoked>(`/auth/sessions/${id}`, reauthOptions(reauth)),
    onSettled: () => {
      // Ids change whenever a device refreshes, so always re-read the list.
      void queryClient.invalidateQueries({ queryKey: settingsKeys.authSessions })
    },
  })
}

export function useRevokeOtherSessions() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (reauth: Reauth) => api.post<SessionsRevoked>('/auth/sessions/revoke-others', undefined, reauthOptions(reauth)),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: settingsKeys.authSessions })
    },
  })
}

export function useRememberThisDevice() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ remember, ...reauth }: RememberDeviceRequest & Reauth) =>
      api.post<SessionRead>('/auth/sessions/current/remember', { remember } satisfies RememberDeviceRequest, reauthOptions(reauth)),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: settingsKeys.authSessions })
    },
  })
}
