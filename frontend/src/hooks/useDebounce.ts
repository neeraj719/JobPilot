import * as React from 'react'

/**
 * Debounce a rapidly changing value — typically a search box feeding a query key.
 *
 * ```ts
 * const [q, setQ] = useState('')
 * const debouncedQ = useDebounce(q, 300)
 * useJobs({ q: debouncedQ })
 * ```
 */
export function useDebounce<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = React.useState(value)

  React.useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay)
    return () => window.clearTimeout(timer)
  }, [value, delay])

  return debounced
}

/** Debounced callback with a stable identity. */
export function useDebouncedCallback<Args extends unknown[]>(
  callback: (...args: Args) => void,
  delay = 300,
): (...args: Args) => void {
  const callbackRef = React.useRef(callback)
  const timerRef = React.useRef<number | undefined>(undefined)

  React.useEffect(() => {
    callbackRef.current = callback
  }, [callback])

  React.useEffect(() => () => window.clearTimeout(timerRef.current), [])

  return React.useCallback(
    (...args: Args) => {
      window.clearTimeout(timerRef.current)
      timerRef.current = window.setTimeout(() => callbackRef.current(...args), delay)
    },
    [delay],
  )
}
