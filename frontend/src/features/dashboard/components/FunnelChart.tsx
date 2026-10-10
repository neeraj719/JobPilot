import { cn, formatNumber, formatPercent } from '@/lib/utils'
import type { FunnelStageKey } from '@/types/api'

import { useChartTheme } from '../chart-theme'

const STAGE_LABELS: Record<FunnelStageKey | string, string> = {
  discovered: 'Jobs found',
  matched: 'Matched',
  queued: 'Queued',
  applied: 'Applied',
  responses: 'Responses',
  interviews: 'Interviews',
  offers: 'Offers',
}

export interface FunnelRow {
  stage: string
  label: string
  count: number
  /** Share of the first stage. */
  ofTotal: number
  /** Share of the previous stage — the number that tells you where you lose people. */
  conversion: number | null
}

export function buildFunnelRows(stages: { stage: string; count: number }[]): FunnelRow[] {
  if (stages.length === 0) return []
  const top = stages[0]?.count ?? 0
  return stages.map((entry, index) => {
    const previous = index === 0 ? null : (stages[index - 1]?.count ?? 0)
    return {
      stage: entry.stage,
      label: STAGE_LABELS[entry.stage] ?? entry.stage,
      count: entry.count,
      ofTotal: top > 0 ? (entry.count / top) * 100 : 0,
      conversion: previous === null ? null : previous > 0 ? (entry.count / previous) * 100 : 0,
    }
  })
}

/**
 * The pipeline, stage by stage.
 *
 * Drawn as plain HTML bars rather than an SVG chart: the stages are ordered, every row
 * needs three numbers beside it (count, share of discovered, conversion from the stage
 * above), and that reads better as a labelled list than as an axis. One hue for every
 * bar — the length already encodes the magnitude, so colour has no second job here.
 */
export function FunnelChart({ rows, className }: { rows: FunnelRow[]; className?: string }) {
  const theme = useChartTheme()

  return (
    <ol className={cn('space-y-3', className)}>
      {rows.map((row) => (
        <li key={row.stage} className="space-y-1.5">
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="min-w-0 truncate font-medium">{row.label}</span>
            <span className="flex shrink-0 items-baseline gap-2">
              <span className="font-semibold tabular-nums">{formatNumber(row.count)}</span>
              {row.conversion !== null ? (
                <span
                  className="text-xs tabular-nums text-muted-foreground"
                  title={`${formatPercent(row.conversion, 0)} of the stage above`}
                >
                  {formatPercent(row.conversion, 0)}
                </span>
              ) : (
                <span className="text-xs text-muted-foreground">start</span>
              )}
            </span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full transition-[width] duration-500"
              style={{ width: `${Math.max(row.ofTotal, row.count > 0 ? 1.5 : 0)}%`, backgroundColor: theme.primarySeries }}
              role="presentation"
            />
          </div>
        </li>
      ))}
    </ol>
  )
}

/** Compact one-line summary used under the funnel. */
export function FunnelSummary({ rows }: { rows: FunnelRow[] }) {
  const first = rows[0]
  const applied = rows.find((row) => row.stage === 'applied')
  const offers = rows.find((row) => row.stage === 'offers')
  if (!first || !applied) return null
  return (
    <p className="text-xs text-muted-foreground">
      {formatNumber(first.count)} jobs found turned into {formatNumber(applied.count)} applications (
      {formatPercent(applied.ofTotal, 0)})
      {offers ? ` and ${formatNumber(offers.count)} ${offers.count === 1 ? 'offer' : 'offers'}` : ''}.
    </p>
  )
}

export { STAGE_LABELS }
