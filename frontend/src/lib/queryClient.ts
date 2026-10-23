import { QueryClient } from '@tanstack/react-query'

import { isApiError } from '@/lib/api'

/**
 * Shared react-query client.
 *
 * Defaults chosen for a dashboard that talks to a single-user API: data is fresh for 30s,
 * one retry for transient/server failures (never for 4xx), and no refetch storm when the
 * user tabs back into the browser.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        if (isApiError(error) && error.isClientError) return false
        return failureCount < 1
      },
    },
    mutations: {
      retry: 0,
    },
  },
})

/**
 * Canonical query keys. Feature modules extend this rather than inventing their own
 * strings, so cross-feature invalidation (`queryClient.invalidateQueries({ queryKey: qk.applications.all })`)
 * keeps working.
 */
export const qk = {
  auth: {
    me: ['auth', 'me'] as const,
  },
  profile: {
    detail: ['profile'] as const,
    jobPreferences: ['preferences', 'job'] as const,
  },
  resumes: {
    all: ['resumes'] as const,
    detail: (id: string) => ['resumes', id] as const,
    versions: (id: string) => ['resumes', id, 'versions'] as const,
    recommendations: (id: string) => ['resumes', id, 'recommendations'] as const,
    recommendationHistory: (id: string) => ['resumes', id, 'recommendations', 'history'] as const,
    applyPlan: (id: string) => ['resumes', id, 'recommendations', 'apply-plan'] as const,
  },
  companies: {
    all: ['companies'] as const,
    list: (params: unknown) => ['companies', 'list', params] as const,
    detail: (id: string) => ['companies', id] as const,
    preferences: ['companies', 'preferences'] as const,
  },
  jobs: {
    all: ['jobs'] as const,
    list: (params: unknown) => ['jobs', 'list', params] as const,
    detail: (id: string) => ['jobs', id] as const,
    sources: ['jobs', 'sources'] as const,
  },
  matching: {
    summary: ['matching', 'summary'] as const,
  },
  applications: {
    all: ['applications'] as const,
    list: (params: unknown) => ['applications', 'list', params] as const,
    detail: (id: string) => ['applications', id] as const,
    events: (id: string) => ['applications', id, 'events'] as const,
    queue: (params: unknown) => ['applications', 'queue', params] as const,
    reviewSummary: ['applications', 'review-summary'] as const,
  },
  interviews: {
    all: ['interviews'] as const,
    list: (params: unknown) => ['interviews', 'list', params] as const,
    detail: (id: string) => ['interviews', id] as const,
  },
  emails: {
    all: ['emails'] as const,
    list: (params: unknown) => ['emails', 'list', params] as const,
    detail: (id: string) => ['emails', id] as const,
  },
  integrations: {
    all: ['integrations'] as const,
    accounts: ['integrations', 'accounts'] as const,
  },
  automation: {
    config: ['automation', 'config'] as const,
    status: ['automation', 'status'] as const,
    runs: (params: unknown) => ['automation', 'runs', params] as const,
    run: (id: string) => ['automation', 'runs', id] as const,
  },
  dashboard: {
    stats: ['dashboard', 'stats'] as const,
    charts: (range: string) => ['dashboard', 'charts', range] as const,
    activity: (limit: number) => ['dashboard', 'activity', limit] as const,
  },
  notifications: {
    all: ['notifications'] as const,
    list: (params: unknown) => ['notifications', 'list', params] as const,
    unreadCount: ['notifications', 'unread-count'] as const,
  },
  audit: {
    list: (params: unknown) => ['audit', 'list', params] as const,
  },
} as const
