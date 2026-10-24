import { animate, useInView, useReducedMotion } from 'framer-motion'
import * as React from 'react'

export interface AnimatedNumberProps {
  value: number
  /** Formats the in-between and final value (default: locale integer). */
  format?: (value: number) => string
  className?: string
}

const defaultFormat = (v: number) => Math.round(v).toLocaleString()

/**
 * Counts up to `value` with a soft spring when it scrolls into view, then follows changes.
 * Instant under `prefers-reduced-motion`. The final value is always what screen readers get.
 * The animated digits are written straight to the DOM from the spring's `onUpdate` (no React
 * state per frame, so a count-up never re-renders the card it sits in ~60 times).
 */
export function AnimatedNumber({ value, format = defaultFormat, className }: AnimatedNumberProps) {
  const ref = React.useRef<HTMLSpanElement>(null)
  const digits = React.useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true })
  const reduce = useReducedMotion()
  const from = React.useRef(reduce ? value : 0)
  const formatRef = React.useRef(format)
  formatRef.current = format
  const write = React.useCallback((v: number) => {
    if (digits.current) digits.current.textContent = formatRef.current(v)
  }, [])

  // First paint: the start value (or the final one under reduced motion), before the browser paints.
  React.useLayoutEffect(() => {
    write(from.current)
  }, [write])

  React.useEffect(() => {
    if (reduce) {
      from.current = value
      write(value)
      return
    }
    if (!inView) return
    let current = from.current
    const controls = animate(current, value, {
      type: 'spring',
      stiffness: 90,
      damping: 20,
      onUpdate: (v) => {
        current = v
        write(v)
      },
      onComplete: () => {
        from.current = value
      },
    })
    return () => {
      controls.stop()
      from.current = current
    }
  }, [value, inView, reduce, write])

  return (
    <span ref={ref} className={className}>
      <span aria-hidden ref={digits} />
      <span className="sr-only">{format(value)}</span>
    </span>
  )
}
