import { ArrowDownRight, ArrowUpRight } from 'lucide-react'

import { cn } from '@/lib/utils'
import { formatDelta, scoreTone, TONE_TEXT } from '@/features/ats/labels'

export interface ScoreRingProps {
  score: number | null | undefined
  /** Score of the analysis this one re-ran; shows the change. */
  previous?: number | null
  size?: number
  className?: string
}

/** The overall estimate as a ring, always labelled "estimated". */
export function ScoreRing({ score, previous, size = 132, className }: ScoreRingProps) {
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
          <circle cx={size / 2} cy={size / 2} r={radius} fill="none" strokeWidth={stroke} className="stroke-muted" />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className={cn('transition-[stroke-dashoffset] duration-700', {
              'stroke-success': tone === 'success',
              'stroke-warning': tone === 'warning',
              'stroke-destructive': tone === 'destructive',
              'stroke-muted-foreground/40': tone === 'muted',
            })}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center" role="img" aria-label={`Estimated ATS compatibility ${value} out of 100`}>
          <span className={cn('text-3xl font-semibold tabular-nums', TONE_TEXT[tone])}>{score ?? '—'}</span>
          <span className="text-[11px] uppercase tracking-wide text-muted-foreground">of 100</span>
        </div>
      </div>
      <span className="text-xs font-medium text-muted-foreground">Estimated compatibility</span>
      {delta !== null ? (
        <span
          className={cn(
            'inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums',
            delta > 0 ? 'bg-success/15 text-success' : delta < 0 ? 'bg-destructive/10 text-destructive' : 'bg-muted text-muted-foreground',
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
