import { type LucideIcon, TrendingDown, TrendingUp } from 'lucide-react'
import * as React from 'react'

import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

export interface StatCardProps {
  title: string
  value: React.ReactNode
  /** Signed change vs. the previous period, e.g. `+3` or `-12`. */
  delta?: number | null
  /** Text after the delta, e.g. `vs last week`. */
  deltaLabel?: string
  /** `false` when a rising number is bad (rejections). */
  deltaPositiveIsGood?: boolean
  icon?: LucideIcon
  description?: string
  loading?: boolean
  className?: string
  onClick?: () => void
}

/** Headline KPI tile used across the dashboard and analytics pages. */
export function StatCard({
  title,
  value,
  delta,
  deltaLabel = 'vs previous period',
  deltaPositiveIsGood = true,
  icon: Icon,
  description,
  loading = false,
  className,
  onClick,
}: StatCardProps) {
  const hasDelta = delta !== undefined && delta !== null && delta !== 0
  const isUp = (delta ?? 0) > 0
  const isGood = isUp === deltaPositiveIsGood

  return (
    <Card
      className={cn(
        'overflow-hidden transition-shadow',
        onClick && 'cursor-pointer hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        className,
      )}
      onClick={onClick}
      {...(onClick
        ? {
            role: 'button',
            tabIndex: 0,
            onKeyDown: (event: React.KeyboardEvent<HTMLDivElement>) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                onClick()
              }
            },
          }
        : {})}
    >
      <CardContent className="flex items-start justify-between gap-4 p-5">
        <div className="min-w-0 space-y-1">
          <p className="truncate text-sm font-medium text-muted-foreground">{title}</p>
          {loading ? (
            <Skeleton className="h-8 w-20" />
          ) : (
            <p className="text-2xl font-semibold tabular-nums tracking-tight">{value}</p>
          )}
          {hasDelta && !loading ? (
            <p className="flex items-center gap-1 text-xs">
              <span className={cn('inline-flex items-center gap-0.5 font-medium', isGood ? 'text-success' : 'text-destructive')}>
                {isUp ? <TrendingUp className="size-3" aria-hidden /> : <TrendingDown className="size-3" aria-hidden />}
                {isUp ? '+' : ''}
                {delta}
              </span>
              <span className="text-muted-foreground">{deltaLabel}</span>
            </p>
          ) : null}
          {description && !hasDelta ? <p className="text-xs text-muted-foreground">{description}</p> : null}
        </div>
        {Icon ? (
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Icon className="size-4" aria-hidden />
          </span>
        ) : null}
      </CardContent>
    </Card>
  )
}
