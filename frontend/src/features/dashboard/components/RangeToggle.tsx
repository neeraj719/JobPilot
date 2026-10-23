import * as React from 'react'
import { useSearchParams } from 'react-router-dom'

import { cn } from '@/lib/utils'
import type { ChartRange } from '@/types/api'

export const RANGE_OPTIONS: { value: ChartRange; label: string; long: string }[] = [
  { value: '7d', label: '7d', long: 'Last 7 days' },
  { value: '30d', label: '30d', long: 'Last 30 days' },
  { value: '90d', label: '90d', long: 'Last 90 days' },
]

export function rangeLabel(range: ChartRange): string {
  return RANGE_OPTIONS.find((option) => option.value === range)?.long ?? 'Last 30 days'
}

function isRange(value: string | null): value is ChartRange {
  return value === '7d' || value === '30d' || value === '90d'
}

/**
 * The selected window, kept in `?range=` so a view can be linked to and survives a
 * reload. Changing it replaces the history entry rather than pushing one.
 */
export function useRangeParam(fallback: ChartRange = '30d'): [ChartRange, (next: ChartRange) => void] {
  const [searchParams, setSearchParams] = useSearchParams()
  const raw = searchParams.get('range')
  const range = isRange(raw) ? raw : fallback

  const setRange = React.useCallback(
    (next: ChartRange) => {
      setSearchParams(
        (current) => {
          const params = new URLSearchParams(current)
          params.set('range', next)
          return params
        },
        { replace: true },
      )
    },
    [setSearchParams],
  )

  return [range, setRange]
}

/**
 * The date-range control. It sits once, above everything it scopes — every chart on the
 * page re-renders against the same window, so the numbers always agree.
 */
export function RangeToggle({
  value,
  onChange,
  className,
  label = 'Date range',
}: {
  value: ChartRange
  onChange: (range: ChartRange) => void
  className?: string
  label?: string
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={cn('inline-flex items-center rounded-md border border-border bg-muted/40 p-0.5', className)}
    >
      {RANGE_OPTIONS.map((option) => {
        const active = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={option.long}
            onClick={() => onChange(option.value)}
            className={cn(
              'rounded px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              active ? 'bg-card text-foreground shadow-sm dark:bg-surface-3' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}
