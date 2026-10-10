/**
 * Notifications feature API — the reference example of the convention every page agent
 * should follow: one `src/features/<area>/api.ts` module holding the react-query hooks
 * for that area, built on `api` from `@/lib/api` and the shared keys from `@/lib/queryClient`.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import type { NotificationRead, PageResponse, UnreadCount } from '@/types/api'

export interface NotificationListParams {
  unread_only?: boolean
  page?: number
  page_size?: number
}

export function useNotifications(params: NotificationListParams = {}) {
  return useQuery({
    queryKey: qk.notifications.list(params),
    queryFn: () => api.get<PageResponse<NotificationRead>>('/notifications', { params: { ...params } }),
  })
}

export function useUnreadCount(options: { enabled?: boolean; refetchInterval?: number } = {}) {
  return useQuery({
    queryKey: qk.notifications.unreadCount,
    queryFn: () => api.get<UnreadCount>('/notifications/unread-count'),
    // The badge should feel live without hammering the API.
    refetchInterval: options.refetchInterval ?? 60_000,
    enabled: options.enabled ?? true,
  })
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.post<NotificationRead>(`/notifications/${id}/read`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.notifications.all })
    },
  })
}

export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<{ updated: number }>('/notifications/read-all'),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.notifications.all })
    },
  })
}
