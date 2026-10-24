/**
 * Hover / focus prefetch for Resume Studio screens: warms the react-query cache with exactly
 * the queries the target page runs first (same keys and fetchers as its hooks), so the page
 * renders from cache instead of a skeleton. Loaded on demand (never in the main bundle).
 */
import { targetsQuery } from '@/features/ats/api'
import { resumeSummaryQuery, studioResumesQuery } from '@/features/resume-studio/api'
import { queryClient } from '@/lib/queryClient'

/** Fresh enough for a page that is about to open: do not refetch what is already cached. */
const STALE = 30_000

export function prefetchResumePath(path: string): Promise<unknown> {
  const tasks: Promise<unknown>[] = []
  if (path === '/resume') {
    tasks.push(queryClient.prefetchQuery({ ...resumeSummaryQuery(), staleTime: STALE }))
    tasks.push(queryClient.prefetchQuery({ ...studioResumesQuery(false), staleTime: STALE }))
  } else if (path === '/resume/my') {
    tasks.push(queryClient.prefetchQuery({ ...studioResumesQuery(false), staleTime: STALE }))
  } else if (path === '/resume/targets') {
    tasks.push(queryClient.prefetchQuery({ ...targetsQuery({ page_size: 100 }), staleTime: STALE }))
  }
  return Promise.all(tasks)
}
