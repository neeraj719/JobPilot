/**
 * Chart theme for the dashboard + analytics pages.
 *
 * Two kinds of colour live here and they must not be mixed:
 *
 *  - **Categorical series colours** (`series`) identify *who* a mark is (a source, a
 *    series in a multi-series chart). The six slots are a validated categorical
 *    palette: every adjacent pair clears the colour-vision separation gate (ΔE >= 8,
 *    OKLab x100) and the normal-vision floor (ΔE >= 15) in **both** modes, measured
 *    against this app's card surfaces (#ffffff light / #181b22 dark, re-validated for
 *    the 2026-10 theme). The values live in `index.css` as `--chart-1…6` (so legends and
 *    swatches can use `bg-chart-N`); the hex below is only the SSR / test fallback and
 *    must stay identical. The dark column is the same hues re-stepped for the dark
 *    surface — never an automatic flip. Three light slots sit below 3:1 contrast on
 *    white by design, so every chart using them ships a legend plus direct labels (the
 *    "relief" rule); do not remove those. Slots are assigned in a fixed order and never
 *    cycled — a seventh category folds into a neutral "Other".
 *
 *  - **Semantic colours** (`success` / `warning` / `destructive` / `info` / `neutral`)
 *    say whether something is *good or bad*. They are read straight off the app's CSS
 *    custom properties so a chart segment matches the `StatusBadge` pill beside it, and
 *    they are only used where the colour genuinely means a state. They always ride with
 *    a visible label, never colour alone.
 *
 * Chrome (grid, axis, tick text, tooltip surface) is resolved from the same CSS
 * variables the rest of the UI uses, re-read whenever the resolved theme changes, so
 * Recharts — which writes colours as SVG attributes — always receives a concrete value.
 */
import * as React from 'react'

import { scoreTone } from '@/lib/score'
import { sourceLabel } from '@/lib/utils'
import { useUiStore } from '@/stores/ui'
import type { ApplicationStatus, JobSourceType } from '@/types/api'

/* ------------------------------------------------------------------ */
/* Categorical palette                                                 */
/* ------------------------------------------------------------------ */

/** Slot order is the colour-vision safety mechanism — do not re-order. */
const CATEGORICAL_LIGHT = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300'] as const
const CATEGORICAL_DARK = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300'] as const

/** Everything past the sixth slot collapses here rather than inventing a seventh hue. */
const OTHER_LIGHT = '#8a8f98'
const OTHER_DARK = '#7b8493'

export const MAX_CATEGORICAL_SLOTS = CATEGORICAL_LIGHT.length

export type ChartMode = 'light' | 'dark'

export interface ChartTheme {
  mode: ChartMode
  /** Six categorical slots, in fixed order. */
  series: readonly string[]
  /** Neutral used for the folded "Other" bucket. */
  other: string
  /** The single hue used when a chart has exactly one series. */
  primarySeries: string
  grid: string
  axis: string
  tick: string
  surface: string
  border: string
  mutedText: string
  success: string
  warning: string
  destructive: string
  info: string
  neutral: string
}

function cssVar(name: string, fallback: string): string {
  if (typeof window === 'undefined' || typeof document === 'undefined') return fallback
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return raw ? `hsl(${raw})` : fallback
}

/**
 * Resolved chart colours for the current theme.
 *
 * Recharts renders colours as SVG presentation attributes, where `var(--token)` strings
 * are not reliably resolved — we read the computed values instead and recompute them
 * whenever the app's resolved theme flips.
 */
export function useChartTheme(): ChartTheme {
  const mode = useUiStore((state) => state.resolvedTheme)

  return React.useMemo<ChartTheme>(() => {
    const dark = mode === 'dark'
    const border = cssVar('--border', dark ? 'hsl(220 11.1% 20.5%)' : 'hsl(220 12.1% 90%)')
    const muted = cssVar('--muted-foreground', dark ? 'hsl(220 12% 74.2%)' : 'hsl(220 8.4% 40.7%)')
    const fallback = dark ? CATEGORICAL_DARK : CATEGORICAL_LIGHT
    const series = fallback.map((hex, index) => cssVar(`--chart-${index + 1}`, hex))
    return {
      mode,
      series,
      other: dark ? OTHER_DARK : OTHER_LIGHT,
      primarySeries: series[0] ?? fallback[0],
      grid: border,
      axis: border,
      tick: muted,
      surface: cssVar('--card', dark ? 'hsl(221 17% 11.5%)' : 'hsl(0 0% 100%)'),
      border,
      mutedText: muted,
      success: cssVar('--success', dark ? 'hsl(139 54.2% 61.1%)' : 'hsl(143 56.5% 27.7%)'),
      warning: cssVar('--warning', dark ? 'hsl(38 86.8% 61.9%)' : 'hsl(33 95.9% 29.2%)'),
      destructive: cssVar('--destructive', dark ? 'hsl(4 97% 73.8%)' : 'hsl(356 72.8% 42.3%)'),
      info: cssVar('--info', dark ? 'hsl(203 87.6% 69.8%)' : 'hsl(199 97.4% 29.8%)'),
      neutral: dark ? OTHER_DARK : OTHER_LIGHT,
    }
  }, [mode])
}

/* ------------------------------------------------------------------ */
/* Source -> colour                                                    */
/* ------------------------------------------------------------------ */

export interface SourceSlice {
  source: JobSourceType | 'OTHER'
  label: string
  count: number
  color: string
  /** Sources rolled into the `OTHER` slice, for the tooltip. */
  merged?: JobSourceType[]
}

/**
 * Fold `by_source` into at most six coloured slices plus a neutral "Other".
 *
 * The mapping is derived once per payload and shared by every chart and table on the
 * page, so a platform keeps the same colour wherever it appears. Ties break on the
 * source name so the assignment is deterministic rather than dependent on row order.
 */
export function buildSourceSlices(
  rows: { source: JobSourceType; count: number }[] | undefined,
  theme: ChartTheme,
): SourceSlice[] {
  if (!rows || rows.length === 0) return []
  const sorted = [...rows].sort((a, b) => b.count - a.count || a.source.localeCompare(b.source))
  const head = sorted.slice(0, MAX_CATEGORICAL_SLOTS)
  const tail = sorted.slice(MAX_CATEGORICAL_SLOTS)

  const slices: SourceSlice[] = head.map((row, index) => ({
    source: row.source,
    label: sourceLabel(row.source),
    count: row.count,
    color: theme.series[index] ?? theme.other,
  }))

  if (tail.length > 0) {
    slices.push({
      source: 'OTHER',
      label: `Other (${tail.length})`,
      count: tail.reduce((sum, row) => sum + row.count, 0),
      color: theme.other,
      merged: tail.map((row) => row.source),
    })
  }
  return slices
}

/** Lookup table for charts/tables that need one source's colour. */
export function sourceColorMap(slices: SourceSlice[]): Record<string, string> {
  const map: Record<string, string> = {}
  for (const slice of slices) {
    map[slice.source] = slice.color
    for (const merged of slice.merged ?? []) map[merged] = slice.color
  }
  return map
}

/* ------------------------------------------------------------------ */
/* Status -> colour (semantic, never a categorical slot)               */
/* ------------------------------------------------------------------ */

/** Mirrors `statusColor()` in `@/lib/utils` so charts match the status pills. */
export function statusChartColor(status: ApplicationStatus | string, theme: ChartTheme): string {
  switch (status) {
    case 'OFFER':
    case 'INTERVIEW':
      return theme.success
    case 'ASSESSMENT':
      return theme.warning
    case 'REJECTED':
      return theme.destructive
    case 'APPLIED':
    case 'IN_PROGRESS':
      return theme.series[0] ?? theme.info
    case 'QUEUED':
    case 'APPLICATION_RECEIVED':
    case 'RECRUITER_CONTACTED':
      return theme.info
    default:
      return theme.neutral
  }
}

/** Match-score bands via the shared `scoreTone(_, 'match')`, so bars match `<MatchScore />`. */
export function matchBucketColor(bucket: string, theme: ChartTheme): string {
  const floor = Number.parseInt(bucket, 10)
  if (Number.isNaN(floor)) return theme.neutral
  const tone = scoreTone(floor, 'match')
  if (tone === 'success') return theme.success
  if (tone === 'warning') return theme.warning
  return theme.neutral
}

/* ------------------------------------------------------------------ */
/* Shared Recharts props                                               */
/* ------------------------------------------------------------------ */

/** Hairline, solid, one step off the surface — never dashed. */
export function gridProps(theme: ChartTheme) {
  return { stroke: theme.grid, strokeWidth: 1, vertical: false } as const
}

/** Hover cursor behind bars: a faint wash of the grid colour, never a solid block. */
export function cursorProps(theme: ChartTheme) {
  return { fill: theme.grid, fillOpacity: 0.35 } as const
}

export function axisProps(theme: ChartTheme) {
  return {
    stroke: theme.axis,
    tick: { fill: theme.tick, fontSize: 12 },
    tickLine: false,
    axisLine: { stroke: theme.axis },
  } as const
}
