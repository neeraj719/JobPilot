import { cn, matchScoreBarColor, matchScoreColor } from '@/lib/utils'

export interface MatchScoreProps {
  /** 0–100. `null`/`undefined` renders a muted "Not analyzed" pill. */
  score: number | null | undefined
  className?: string
  /** Adds a thin progress bar underneath the pill. */
  showBar?: boolean
  size?: 'sm' | 'md'
  label?: string
}

/**
 * Match-score pill with the shared colour bands:
 * 85+ green (strong), 70+ amber (decent), below that muted.
 */
export function MatchScore({ score, className, showBar = false, size = 'md', label }: MatchScoreProps) {
  const hasScore = score !== null && score !== undefined
  const clamped = hasScore ? Math.max(0, Math.min(100, Math.round(score))) : 0

  return (
    <div className={cn('inline-flex flex-col gap-1', className)}>
      <span
        className={cn(
          'inline-flex items-center gap-1 whitespace-nowrap rounded-full border font-semibold tabular-nums',
          size === 'sm' ? 'px-2 py-0.5 text-2xs' : 'px-2.5 py-0.5 text-xs',
          matchScoreColor(score),
        )}
        title={hasScore ? `Match score ${clamped} out of 100` : 'Not analyzed yet'}
      >
        {hasScore ? `${clamped}%` : '—'}
        {label ? <span className="font-normal opacity-80">{label}</span> : null}
      </span>
      {showBar ? (
        <span className="h-1 w-full min-w-16 overflow-hidden rounded-full bg-surface-3" aria-hidden>
          <span
            className={cn('block h-full rounded-full transition-all', matchScoreBarColor(score))}
            style={{ width: `${clamped}%` }}
          />
        </span>
      ) : null}
    </div>
  )
}
