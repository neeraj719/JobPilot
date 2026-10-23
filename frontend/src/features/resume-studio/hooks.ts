import * as React from 'react'

/**
 * Warn before leaving while edits are not on the server yet.
 *
 * The app uses `<BrowserRouter>` (no data router, so no `useBlocker`): tab close/reload is
 * covered by `beforeunload`, in-app links by a capture-phase click listener that asks first.
 */
export function useUnsavedGuard(when: boolean, message = 'Your latest edits are still being saved. Leave anyway?') {
  React.useEffect(() => {
    if (!when) return
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = message
      return message
    }
    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return
      const anchor = (event.target as HTMLElement | null)?.closest?.('a[href]') as HTMLAnchorElement | null
      if (!anchor || anchor.target === '_blank' || anchor.hasAttribute('download')) return
      if (anchor.origin !== window.location.origin) return
      if (!window.confirm(message)) {
        event.preventDefault()
        event.stopPropagation()
      }
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    document.addEventListener('click', onClick, true)
    return () => {
      window.removeEventListener('beforeunload', onBeforeUnload)
      document.removeEventListener('click', onClick, true)
    }
  }, [when, message])
}

/** `true` while the viewport matches `query` (re-renders on change). */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = React.useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches)
  React.useEffect(() => {
    const media = window.matchMedia(query)
    const onChange = () => setMatches(media.matches)
    onChange()
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [query])
  return matches
}

export type AutosaveStatus = 'idle' | 'pending' | 'saving' | 'saved' | 'error'

/**
 * Debounced autosave of `value` (compared by JSON). Never blocks typing; on failure it
 * retries once after a few seconds and exposes `retry()` for the status button.
 */
export function useAutosave<T>(
  value: T,
  save: (value: T) => Promise<unknown>,
  { delay = 1500, enabled = true, initial }: { delay?: number; enabled?: boolean; initial?: T } = {},
) {
  const serialized = JSON.stringify(value)
  // What the server already holds when the editor opens (nothing to save until it changes).
  const lastSaved = React.useRef<string | null>(initial !== undefined ? JSON.stringify(initial) : null)
  const latest = React.useRef(value)
  latest.current = value
  const saveRef = React.useRef(save)
  saveRef.current = save
  const [status, setStatus] = React.useState<AutosaveStatus>('idle')
  const [savedAt, setSavedAt] = React.useState<Date | null>(null)
  const retryTimer = React.useRef<number | undefined>(undefined)
  const inFlight = React.useRef(false)

  const flush = React.useCallback(async (attempt = 0): Promise<void> => {
    const snapshot = JSON.stringify(latest.current)
    if (snapshot === lastSaved.current) {
      setStatus((s) => (s === 'pending' ? 'saved' : s))
      return
    }
    if (inFlight.current) return
    inFlight.current = true
    setStatus('saving')
    try {
      await saveRef.current(latest.current)
      lastSaved.current = snapshot
      setSavedAt(new Date())
      setStatus(JSON.stringify(latest.current) === snapshot ? 'saved' : 'pending')
    } catch {
      setStatus('error')
      if (attempt === 0) {
        window.clearTimeout(retryTimer.current)
        retryTimer.current = window.setTimeout(() => void flush(1), 5000)
      }
    } finally {
      inFlight.current = false
    }
  }, [])

  /** Mark the current value as already stored (initial load, or after saving a version). */
  const markClean = React.useCallback((current?: T) => {
    lastSaved.current = JSON.stringify(current ?? latest.current)
    setStatus('idle')
  }, [])

  React.useEffect(() => {
    if (!enabled || lastSaved.current === null || serialized === lastSaved.current) return
    setStatus('pending')
    const timer = window.setTimeout(() => void flush(), delay)
    return () => window.clearTimeout(timer)
  }, [serialized, enabled, delay, flush])

  React.useEffect(() => () => window.clearTimeout(retryTimer.current), [])

  return {
    status,
    savedAt,
    retry: () => void flush(),
    flush,
    markClean,
    dirty: lastSaved.current !== null && serialized !== lastSaved.current,
  }
}
