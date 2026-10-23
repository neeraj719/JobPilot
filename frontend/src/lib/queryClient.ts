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
  // Resume studio (builder / editor / templates / export / version diff) — owned by the
  // resume-builder stream; extend inside this namespace only.
  resumeStudio: {
    all: ['resume-studio'] as const,
    templates: ['resume-studio', 'templates'] as const,
    dashboard: ['resume-studio', 'dashboard'] as const,
    list: (includeArchived: boolean) => ['resume-studio', 'list', includeArchived] as const,
    prefill: ['resume-studio', 'prefill'] as const,
    draft: (id: string) => ['resume-studio', 'draft', id] as const,
    history: (params: unknown) => ['resume-studio', 'history', params] as const,
    versionDiff: (id: string, version: number, against: number | null) =>
      ['resume-studio', 'diff', id, version, against] as const,
    resumeDiff: (id: string, against: string) => ['resume-studio', 'resume-diff', id, against] as const,
  },
  // ATS optimizer (job targets, JD snapshots, analyses, tailoring) — owned by the ats stream.
  ats: {
    all: ['ats'] as const,
    targets: (params: unknown) => ['ats', 'targets', params] as const,
    target: (id: string) => ['ats', 'targets', id] as const,
    analysis: (id: string) => ['ats', 'analyses', id] as const,
    analyses: (params: unknown) => ['ats', 'analyses', 'list', params] as const,
    methodology: ['ats', 'methodology'] as const,
    compare: (id: string) => ['ats', 'compare', id] as const,
    summary: ['ats', 'summary'] as const,
    lookup: (name: string, role: string) => ['ats', 'lookup', name, role] as const,
  },
  // AI provider settings, credentials, model registry, usage — owned by the ai-providers stream.
  aiProviders: {
    all: ['ai-providers'] as const,
    settings: ['ai-providers', 'settings'] as const,
    models: (provider: string) => ['ai-providers', provider, 'models'] as const,
    usage: (params: unknown) => ['ai-providers', 'usage', params] as const,
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
