import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { formatNumber, truncate } from '@/lib/utils'

import { axisProps, useChartTheme } from '../chart-theme'
import { ChartTooltip } from './ChartTooltip'

export interface BarRow {
  /** Y-axis label — always visible, so colour is never the only channel. */
  label: string
  value: number
  /** Omit for a single-series chart: every bar then takes the primary hue. */
  color?: string
  /** Extra line in the tooltip. */
  hint?: string
}

/**
 * Ranked horizontal bars with the value at each bar's tip.
 *
 * Long category names are why this is horizontal: a column chart would either rotate
 * them or clip them. Every bar carries its value at the tip and its name on the axis,
 * so there is no gridline here at all — nothing is left for it to do.
 */
export function HorizontalBarChart({
  rows,
  height,
  labelWidth = 120,
  ariaLabel,
}: {
  rows: BarRow[]
  /** Defaults to 30px per bar plus the axis band. */
  height?: number
  labelWidth?: number
  ariaLabel?: string
}) {
  const theme = useChartTheme()
  const axis = axisProps(theme)
  const plotHeight = height ?? Math.max(140, rows.length * 30 + 32)
  const max = rows.reduce((peak, row) => Math.max(peak, row.value), 0)
  // Recharts wraps a category tick that does not fit its axis width onto a second line,
  // which then collides with its neighbours — so truncate to what the width can hold.
  const maxLabelChars = Math.max(8, Math.floor((labelWidth - 14) / 7.2))

  return (
    <div style={{ width: '100%', height: plotHeight }} role="img" aria-label={ariaLabel}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={rows}
          layout="vertical"
          margin={{ top: 4, right: 36, bottom: 4, left: 0 }}
          barCategoryGap={6}
        >
          <XAxis type="number" allowDecimals={false} domain={[0, Math.max(1, Math.ceil(max * 1.15))]} hide />
          <YAxis
            type="category"
            dataKey="label"
            width={labelWidth}
            interval={0}
            tickFormatter={(value: string) => truncate(value, maxLabelChars)}
            {...axis}
            axisLine={false}
          />
          <Tooltip
            cursor={{ fill: theme.grid, fillOpacity: 0.35 }}
            content={
              <ChartTooltip
                valueFormatter={(value) => formatNumber(value)}
                nameFormatter={(entry) => {
                  const payload = entry.payload as BarRow | undefined
                  return payload?.hint ? `${payload.label} · ${payload.hint}` : (payload?.label ?? '')
                }}
              />
            }
          />
          <Bar dataKey="value" name="value" radius={[0, 4, 4, 0]} maxBarSize={22} isAnimationActive={false}>
            {rows.map((row, index) => (
              <Cell key={`${row.label}-${index}`} fill={row.color ?? theme.primarySeries} />
            ))}
            <LabelList
              dataKey="value"
              position="right"
              offset={8}
              className="fill-muted-foreground text-xs tabular-nums"
              formatter={(value: number) => formatNumber(value)}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
