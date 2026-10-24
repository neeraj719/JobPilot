/**
 * Route chunk loaders shared by the router (`React.lazy`) and the idle / hover prefetchers.
 * `import()` is cached by the module system, so prefetching and rendering share one request.
 */
export const loadHome = () => import('@/pages/Home')
export const loadResumePages = () => import('@/modules/resume/pages')
export const loadAuthPages = () => import('@/modules/auth/pages')

type Loader = () => Promise<unknown>

/** Whether prefetching is welcome: not on a metered / data-saver connection. */
function mayPrefetch(): boolean {
  const connection = (navigator as unknown as { connection?: { saveData?: boolean; effectiveType?: string } }).connection
  return !(connection?.saveData || connection?.effectiveType === '2g' || connection?.effectiveType === 'slow-2g')
}

/** Download a chunk when the browser is idle (after the current page has painted). */
export function prefetchWhenIdle(load: Loader, timeout = 3000): () => void {
  if (typeof window === 'undefined' || !mayPrefetch()) return () => undefined
  const run = () => void load().catch(() => undefined)
  if ('requestIdleCallback' in window) {
    const id = window.requestIdleCallback(run, { timeout })
    return () => window.cancelIdleCallback(id)
  }
  const id = setTimeout(run, 1500)
  return () => clearTimeout(id)
}

/** Props that prefetch a chunk on hover / focus / touch (pointer intent). */
export function prefetchOnIntent(load: Loader) {
  let done = false
  const go = () => {
    if (done || !mayPrefetch()) return
    done = true
    void load().catch(() => {
      done = false
    })
  }
  return { onPointerEnter: go, onFocus: go, onTouchStart: go }
}
