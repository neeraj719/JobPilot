/**
 * Workspace hooks: the user's modules (launcher, switcher, route guards), workspace
 * preferences, and the admin's per-user module switch.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import { useAuthStore } from '@/stores/auth'

import type {
  AdminCatalogModule,
  AdminCatalogUpdate,
  AdminUserModules,
  AdminUserRef,
  ModuleUpdate,
  WorkspaceModule,
  WorkspacePreferences,
  WorkspacePreferencesUpdate,
} from './types'

/**
 * The user's visible modules, in their order. `summary` adds the launcher card numbers
 * (slower; only the launcher asks). The list depends on the session's active role, so the
 * key carries it: switching role refetches.
 */
export function useWorkspaceModules({ summary = false }: { summary?: boolean } = {}) {
  const activeRole = useAuthStore((state) => state.activeRole)
  return useQuery({
    queryKey: [...qk.workspace.modules(summary), activeRole ?? ''] as const,
    queryFn: () => api.get<WorkspaceModule[]>('/workspace/modules', { params: { summary } }),
    staleTime: summary ? 30_000 : 60_000,
  })
}

export function useOpenModule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (code: string) => api.post<WorkspaceModule>(`/workspace/modules/${encodeURIComponent(code)}/open`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.workspace.preferences })
    },
  })
}

export function useUpdateModule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ code, ...payload }: ModuleUpdate & { code: string }) =>
      api.put<WorkspaceModule>(`/workspace/modules/${encodeURIComponent(code)}`, payload),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['workspace', 'modules'] }),
  })
}

export function useWorkspacePreferences() {
  return useQuery({
    queryKey: qk.workspace.preferences,
    queryFn: () => api.get<WorkspacePreferences>('/workspace/preferences'),
    staleTime: 60_000,
  })
}

export function useUpdateWorkspacePreferences() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: WorkspacePreferencesUpdate) => api.put<WorkspacePreferences>('/workspace/preferences', payload),
    onSuccess: (preferences) => {
      queryClient.setQueryData(qk.workspace.preferences, preferences)
    },
  })
}

/* ------------------------------------------------------------------ */
/* Admin                                                               */
/* ------------------------------------------------------------------ */

/** The platform-wide module catalog. */
export function useAdminCatalog(enabled = true) {
  return useQuery({
    queryKey: qk.workspace.adminCatalog,
    queryFn: () => api.get<AdminCatalogModule[]>('/workspace/admin/modules'),
    enabled,
  })
}

/** Switch a module on or off for everyone (or change its status / order). */
export function useAdminUpdateCatalog() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ code, ...payload }: AdminCatalogUpdate & { code: string }) =>
      api.put<AdminCatalogModule>(`/workspace/admin/modules/${encodeURIComponent(code)}`, payload),
    onSuccess: () => {
      // The catalog, every user's module list and the per-user admin views all change.
      void queryClient.invalidateQueries({ queryKey: qk.workspace.all })
    },
  })
}

/** Exact-email lookup; `enabled` only once the admin submitted an address. */
export function useAdminFindUser(email: string | null) {
  return useQuery({
    queryKey: qk.workspace.adminUser(email ?? ''),
    queryFn: () => api.get<AdminUserRef>('/workspace/admin/users', { params: { email: email ?? '' } }),
    enabled: Boolean(email),
    staleTime: 0,
  })
}

export function useAdminUserModules(userId: string | null | undefined) {
  return useQuery({
    queryKey: qk.workspace.adminUserModules(userId ?? 'none'),
    queryFn: () => api.get<AdminUserModules>(`/workspace/admin/users/${userId}/modules`),
    enabled: Boolean(userId),
  })
}

export function useAdminToggleModule(userId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ code, is_enabled }: { code: string; is_enabled: boolean }) =>
      api.put<AdminUserModules>(`/workspace/admin/users/${userId}/modules/${encodeURIComponent(code)}`, { is_enabled }),
    onSuccess: (view) => {
      queryClient.setQueryData(qk.workspace.adminUserModules(userId), view)
      // The admin may have switched a module for their own account.
      void queryClient.invalidateQueries({ queryKey: ['workspace', 'modules'] })
    },
  })
}
