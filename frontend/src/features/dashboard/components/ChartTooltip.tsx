import * as React from 'react'

import { cn, formatNumber } from '@/lib/utils'

/**
 * Minimal shape of what Recharts hands a custom tooltip. Declared locally so these
 * components never touch `any` and never depend on recharts' internal generics.
 */
export interface TooltipEntry {
  name?: string | number
  value?: number | string | (number | string)[]
  color?: string
  dataKey?: string | number
  payload?: Record<string, unknown>
}

export interface ChartTooltipProps {
  active?: boolean
  label?: string | number
  payload?: TooltipEntry[]
  /** Formats the heading (the x value). */
  labelFormatter?: (label: string | number) => string
  /** Formats one row's value. */
  valueFormatter?: (value: number, entry: TooltipEntry) => string
  /** Overrides a row's series name. */
  nameFormatter?: (entry: TooltipEntry) => string
  /** Extra line under the rows, e.g. a share-of-total. */
  renderFooter?: (payload: TooltipEntry[]) => React.ReactNode
  className?: string
}

function toNumber(value: TooltipEntry['value']): number {
  if (typeof value === 'number') return value
  if (typeof value === 'string') {
    const parsed = Number(value)
    return Number.isNaN(parsed) ? 0 : parsed
  }
  return 0
}

/**
 * Shared tooltip: value leads, series name follows, identity carried by a short line
 * key rather than a filled block. Names come from the API, so they are rendered as
 * text nodes by React — never interpolated into markup.
 */
export function ChartTooltip({
  active,
  label,
  payload,
  labelFormatter,
  valueFormatter,
  nameFormatter,
  renderFooter,
  className,
}: ChartTooltipProps) {
  if (!active || !payload || payload.length === 0) return null

  return (
    <div
      className={cn(
        'pointer-events-none min-w-36 rounded-md border border-border bg-popover/95 px-3 py-2 text-popover-foreground shadow-md backdrop-blur',
        className,
      )}
    >
      {label !== undefined && label !== '' ? (
        <p className="mb-1.5 text-xs font-medium text-muted-foreground">
          {labelFormatter ? labelFormatter(label) : String(label)}
        </p>
      ) : null}
      <ul className="space-y-1">
        {payload.map((entry, index) => {
          const value = toNumber(entry.value)
          return (
            <li key={`${String(entry.dataKey ?? entry.name ?? index)}`} className="flex items-center gap-2 text-sm">
              <span
                aria-hidden
                className="h-0.5 w-3 shrink-0 rounded-full"
                style={{ backgroundColor: entry.color ?? 'currentColor' }}
              />
              <span className="font-semibold tabular-nums">
                {valueFormatter ? valueFormatter(value, entry) : formatNumber(value)}
              </span>
              <span className="truncate text-xs text-muted-foreground">
                {nameFormatter ? nameFormatter(entry) : String(entry.name ?? '')}
              </span>
            </li>
          )
        })}
      </ul>
      {renderFooter ? <div className="mt-1.5 border-t border-border pt-1.5 text-xs text-muted-foreground">{renderFooter(payload)}</div> : null}
    </div>
  )
}

export interface ChartLegendItem {
  label: string
  color: string
  value?: React.ReactNode
}

/**
 * Legend rendered as plain HTML rather than a Recharts legend, so it wraps properly on
 * a phone and keeps its text in the theme's ink colours (never the series colour).
 */
export function ChartLegend({
  items,
  className,
  markShape = 'rect',
}: {
  items: ChartLegendItem[]
  className?: string
  /** `line` for line series, `rect` for bars/areas/slices — mirror the mark. */
  markShape?: 'rect' | 'line'
}) {
  if (items.length === 0) return null
  return (
    <ul className={cn('flex flex-wrap items-center gap-x-4 gap-y-1.5', className)}>
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span
            aria-hidden
            className={cn('shrink-0', markShape === 'line' ? 'h-0.5 w-3.5 rounded-full' : 'size-2.5 rounded-sm')}
            style={{ backgroundColor: item.color }}
          />
          <span className="text-foreground">{item.label}</span>
          {item.value !== undefined ? <span className="tabular-nums">{item.value}</span> : null}
        </li>
      ))}
    </ul>
  )
}
