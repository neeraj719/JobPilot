import * as React from 'react'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'

import { formatNumber, formatPercent } from '@/lib/utils'

import { useChartTheme, type SourceSlice } from '../chart-theme'
import { ChartTooltip } from './ChartTooltip'

/**
 * Where the submitted applications went, as a part-to-whole donut.
 *
 * Capped at five coloured slices plus a neutral "Other" — a sixth hue would not be
 * tellable apart under colour-vision deficiency. Every slice is also listed with its
 * count and share beside the chart, so no value is reachable only by hovering.
 */
export function SourceDonut({ slices, height = 240 }: { slices: SourceSlice[]; height?: number }) {
  const theme = useChartTheme()
  const total = React.useMemo(() => slices.reduce((sum, slice) => sum + slice.count, 0), [slices])

  return (
    // Always stacked: inside a three-up card grid a side-by-side legend gets squeezed to
    // nothing and the platform names disappear behind `truncate`.
    <div className="flex flex-col items-center gap-4">
      <div className="relative w-full max-w-[190px] shrink-0" style={{ aspectRatio: '1 / 1', maxHeight: height }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={slices}
              dataKey="count"
              nameKey="label"
              innerRadius="62%"
              outerRadius="92%"
              paddingAngle={0}
              stroke={theme.surface}
              strokeWidth={2}
              isAnimationActive={false}
            >
              {slices.map((slice) => (
                <Cell key={slice.source} fill={slice.color} />
              ))}
            </Pie>
            <Tooltip
              content={
                <ChartTooltip
                  valueFormatter={(value) =>
                    `${formatNumber(value)} · ${formatPercent(total > 0 ? (value / total) * 100 : 0, 0)}`
                  }
                />
              }
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-semibold">{formatNumber(total)}</span>
          <span className="text-xs text-muted-foreground">submitted</span>
        </div>
      </div>

      {/* The legend doubles as the table view: every slice's exact value is visible. */}
      <ul className="w-full min-w-0 space-y-1.5">
        {slices.map((slice) => (
          <li key={slice.source} className="flex items-center gap-2 text-sm">
            <span aria-hidden className="size-2.5 shrink-0 rounded-sm" style={{ backgroundColor: slice.color }} />
            <span className="min-w-0 flex-1 truncate" title={slice.merged?.join(', ')}>
              {slice.label}
            </span>
            <span className="tabular-nums font-medium">{formatNumber(slice.count)}</span>
            <span className="w-10 text-right text-xs tabular-nums text-muted-foreground">
              {formatPercent(total > 0 ? (slice.count / total) * 100 : 0, 0)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
