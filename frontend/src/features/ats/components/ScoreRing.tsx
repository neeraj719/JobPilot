import { animate, motion, useReducedMotion } from 'framer-motion'
import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import * as React from 'react'

import { cn } from '@/lib/utils'
import { formatDelta, scoreTone, TONE_TEXT } from '@/features/ats/labels'

export interface ScoreRingProps {
  score: number | null | undefined
  /** Score of the analysis this one re-ran; shows the change. */
  previous?: number | null
  size?: number
  className?: string
}

/** Stroke colours per tone: the status colour fading into a lighter step of itself (meaning
 *  stays semantic — the gradient only adds depth). */
const TONE_STOPS: Record<string, [string, string]> = {
  success: ['hsl(var(--success))', 'hsl(var(--success) / 0.55)'],
  warning: ['hsl(var(--warning))', 'hsl(var(--warning) / 0.55)'],
  destructive: ['hsl(var(--destructive))', 'hsl(var(--destructive) / 0.55)'],
  muted: ['hsl(var(--muted-foreground) / 0.5)', 'hsl(var(--muted-foreground) / 0.25)'],
}

/**
 * Counts up to `value` with a spring (instant under reduced motion). The digits are written to
 * the returned element from the spring's `onUpdate` — no React state per animation frame.
 */
function useCountUp(value: number | null | undefined, reduce: boolean): React.RefObject<HTMLSpanElement> {
  const ref = React.useRef<HTMLSpanElement>(null)
  React.useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    if (value == null || reduce) {
      el.textContent = value == null ? '—' : String(value)
      return
    }
    el.textContent = '0'
    const controls = animate(0, value, {
      type: 'spring',
      stiffness: 70,
      damping: 18,
      onUpdate: (v) => {
        el.textContent = String(Math.round(v))
      },
    })
    return () => controls.stop()
  }, [value, reduce])
  return ref
}

/** The overall estimate as a ring, always labelled "estimated". Gradient stroke, spring fill. */
export function ScoreRing({ score, previous, size = 132, className }: ScoreRingProps) {
  const reduce = Boolean(useReducedMotion())
  const gradientId = `ring-${React.useId().replace(/:/g, '')}`
  const digits = useCountUp(score, reduce)
  const value = score ?? 0
  const stroke = 10
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference * (1 - Math.max(0, Math.min(100, value)) / 100)
  const tone = scoreTone(score)
  const delta = previous !== null && previous !== undefined && score !== null && score !== undefined ? score - previous : null

  return (
    <div className={cn('flex flex-col items-center gap-1.5', className)}>
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90" aria-hidden>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor={(TONE_STOPS[tone] ?? TONE_STOPS.muted)[0]} />
              <stop offset="100%" stopColor={(TONE_STOPS[tone] ?? TONE_STOPS.muted)[1]} />
            </linearGradient>
          </defs>
          <circle cx={size / 2} cy={size / 2} r={radius} fill="none" strokeWidth={stroke} className="stroke-muted" />
          <motion.circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={circumference}
            stroke={`url(#${gradientId})`}
            initial={{ strokeDashoffset: reduce ? offset : circumference }}
            animate={{ strokeDashoffset: offset }}
            transition={reduce ? { duration: 0 } : { type: 'spring', stiffness: 60, damping: 16, mass: 1 }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center" role="img" aria-label={`Estimated ATS compatibility ${value} out of 100`}>
          <span ref={digits} className={cn('text-3xl font-heading tabular-nums', TONE_TEXT[tone])} />
          <span className="text-[11px] uppercase tracking-wide text-muted-foreground">of 100</span>
        </div>
      </div>
      <span className="text-xs font-medium text-muted-foreground">Estimated compatibility</span>
      {delta !== null ? (
        <span
          className={cn(
            'inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums',
            delta > 0 ? 'bg-success-soft text-success-soft-foreground' : delta < 0 ? 'bg-destructive-soft text-destructive-soft-foreground' : 'bg-muted text-muted-foreground',
          )}
          title={`Was ${previous} before your changes`}
        >
          {delta > 0 ? <ArrowUpRight className="size-3" aria-hidden /> : delta < 0 ? <ArrowDownRight className="size-3" aria-hidden /> : null}
          {formatDelta(delta)} since last run
        </span>
      ) : null}
    </div>
  )
}
