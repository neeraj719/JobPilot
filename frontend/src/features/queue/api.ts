/**
 * Application queue API — `GET /applications/queue` plus the one cross-module
 * mutation the queue needs (`POST /companies/preferences` to blacklist a company).
 *
 * The start / skip mutations live in `features/applications/api.ts`; the queue page
 * reuses them so a row action and the Approval Center invalidate the same keys.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import type { CompanyPreferenceRead, CompanyPriority, PageResponse, QueueItem, QueueParams } from '@/types/api'

function cleanParams(params: QueueParams): Record<string, string | number | boolean> {
  const out: Record<string, string | number | boolean> = {}
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    out[key] = value as string | number | boolean
  }
  return out
}

export interface QueueOptions {
  /** Poll while any row is mid-run. */
  refetchInterval?: number | false
}

export function useQueue(params: QueueParams, options: QueueOptions = {}) {
  const clean = cleanParams(params)
  return useQuery({
    queryKey: qk.applications.queue(clean),
    queryFn: () => api.get<PageResponse<QueueItem>>('/applications/queue', { params: clean }),
    placeholderData: (previous) => previous,
    // Back off while the API is unhappy (e.g. rate limited) rather than polling into it.
    refetchInterval: (query) => {
      const base = options.refetchInterval ?? false
      if (base === false) return false
      return query.state.status === 'error' ? Math.max(base * 3, 30_000) : base
    },
  })
}

/** Set (or overwrite) the caller's priority for one company — used for "Blacklist company". */
export function useSetCompanyPriority() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ companyName, priority, notes }: { companyName: string; priority: CompanyPriority; notes?: string }) =>
      api.post<CompanyPreferenceRead>('/companies/preferences', {
        company_name: companyName,
        priority,
        notes: notes ?? null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.companies.all })
      void queryClient.invalidateQueries({ queryKey: qk.applications.all })
      void queryClient.invalidateQueries({ queryKey: qk.jobs.all })
    },
  })
}
