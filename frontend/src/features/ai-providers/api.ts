/**
 * AI Model Settings hooks (`/api/v1/ai/...`). Keys live under `qk.aiProviders`.
 *
 * Nothing here calls a hosted provider on page load: model lists are requested with
 * `live=false` (registry + a recent cached live list) until the user tests a key or asks
 * for a refresh. Only the local Ollama server is probed live, because that is cheap and
 * never leaves the machine.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, reauthHeaders } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import type {
  AiSettingsRead,
  AiSettingsUpdate,
  ConnectionTestResult,
  CredentialRead,
  CredentialWrite,
  ModelsResponse,
  ProviderId,
  ProvidersResponse,
  UsageRange,
  UsageResponse,
} from '@/features/ai-providers/types'

export const aiKeys = {
  all: qk.aiProviders.all,
  providers: [...qk.aiProviders.all, 'providers'] as const,
  settings: qk.aiProviders.settings,
  models: qk.aiProviders.models,
  usage: (range: UsageRange) => qk.aiProviders.usage(range),
}

export function useAiProviders() {
  return useQuery({
    queryKey: aiKeys.providers,
    queryFn: () => api.get<ProvidersResponse>('/ai/providers'),
  })
}

export function useAiSettings() {
  return useQuery({
    queryKey: aiKeys.settings,
    queryFn: () => api.get<AiSettingsRead>('/ai/settings'),
  })
}

/** Registry + cached live list; `live` only for providers that are cheap to probe (Ollama). */
export function useProviderModels(provider: ProviderId | null | undefined, { enabled = true }: { enabled?: boolean } = {}) {
  const live = provider === 'ollama'
  return useQuery({
    queryKey: [...aiKeys.models(provider ?? 'none'), live ? 'live' : 'cached'] as const,
    queryFn: () => api.get<ModelsResponse>(`/ai/providers/${provider}/models`, { params: { live } }),
    enabled: Boolean(provider) && enabled,
    staleTime: 5 * 60_000,
  })
}

export function useRefreshModels() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (provider: ProviderId) =>
      api.get<ModelsResponse>(`/ai/providers/${provider}/models`, { params: { live: true, refresh: true } }),
    onSuccess: (data, provider) => {
      queryClient.setQueryData([...aiKeys.models(provider), provider === 'ollama' ? 'live' : 'cached'], data)
    },
  })
}

export function useUpdateAiSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: AiSettingsUpdate) => api.put<AiSettingsRead>('/ai/settings', payload),
    onSuccess: (settings) => {
      queryClient.setQueryData(aiKeys.settings, settings)
      void queryClient.invalidateQueries({ queryKey: ['ai', 'status'] })
    },
  })
}

function reauth(password?: string) {
  return password ? { headers: reauthHeaders(password) } : {}
}

export function useSaveCredential() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ provider, payload, password }: { provider: ProviderId; payload: CredentialWrite; password?: string }) =>
      api.put<CredentialRead>(`/ai/credentials/${provider}`, payload, reauth(password)),
    onSuccess: (_data, { provider }) => {
      void queryClient.invalidateQueries({ queryKey: aiKeys.providers })
      void queryClient.invalidateQueries({ queryKey: aiKeys.settings })
      void queryClient.invalidateQueries({ queryKey: aiKeys.models(provider) })
    },
  })
}

export function useDeleteCredential() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ provider, password }: { provider: ProviderId; password?: string }) =>
      api.delete<void>(`/ai/credentials/${provider}`, reauth(password)),
    onSuccess: (_data, { provider }) => {
      void queryClient.invalidateQueries({ queryKey: aiKeys.providers })
      void queryClient.invalidateQueries({ queryKey: aiKeys.settings })
      void queryClient.invalidateQueries({ queryKey: aiKeys.models(provider) })
    },
  })
}

export function useTestConnection() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ provider, model }: { provider: ProviderId; model?: string | null }) =>
      api.post<ConnectionTestResult>(`/ai/credentials/${provider}/test`, model ? { model } : {}),
    onSuccess: async (result, { provider }) => {
      void queryClient.invalidateQueries({ queryKey: aiKeys.providers })
      void queryClient.invalidateQueries({ queryKey: aiKeys.settings })
      if (result.ok && provider !== 'mock') {
        // The key works: fetch the live model list once (user-initiated).
        try {
          const live = await api.get<ModelsResponse>(`/ai/providers/${provider}/models`, { params: { live: true, refresh: true } })
          queryClient.setQueryData([...aiKeys.models(provider), provider === 'ollama' ? 'live' : 'cached'], live)
        } catch {
          /* the cached list stays */
        }
      }
    },
  })
}

export function useAiUsage(range: UsageRange) {
  return useQuery({
    queryKey: aiKeys.usage(range),
    queryFn: () => api.get<UsageResponse>('/ai/usage', { params: { range } }),
  })
}
