import { cn, sourceLabel } from '@/lib/utils'
import type { JobSourceType } from '@/types/api'

export interface SourceBadgeProps {
  source: JobSourceType | null | undefined
  className?: string
}

/** Neutral pill naming the platform a job was discovered on. */
export function SourceBadge({ source, className }: SourceBadgeProps) {
  if (!source) return null
  return (
    <span
      className={cn(
        'inline-flex items-center whitespace-nowrap rounded-md border border-border bg-muted/60 px-1.5 py-0.5 text-2xs font-medium text-muted-foreground',
        className,
      )}
    >
      {sourceLabel(source)}
    </span>
  )
}

export interface SourceBadgeListProps {
  sources: JobSourceType[] | null | undefined
  /** Show at most this many, then a `+N` pill. */
  max?: number
  className?: string
}

/** The same posting is often found on several platforms — render them compactly. */
export function SourceBadgeList({ sources, max = 3, className }: SourceBadgeListProps) {
  if (!sources || sources.length === 0) return null
  const visible = sources.slice(0, max)
  const overflow = sources.length - visible.length

  return (
    <span className={cn('inline-flex flex-wrap items-center gap-1', className)}>
      {visible.map((source) => (
        <SourceBadge key={source} source={source} />
      ))}
      {overflow > 0 ? (
        <span
          className="inline-flex items-center rounded-md border border-border bg-muted/60 px-1.5 py-0.5 text-2xs font-medium text-muted-foreground"
          title={sources.slice(max).map((s) => sourceLabel(s)).join(', ')}
        >
          +{overflow}
        </span>
      ) : null}
    </span>
  )
}
