import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { formatNumber } from '@/lib/utils'

import { axisProps, gridProps, matchBucketColor, useChartTheme } from '../chart-theme'
import { ChartTooltip } from './ChartTooltip'

export interface MatchBucketRow {
  bucket: string
  count: number
}

/**
 * How the analysed jobs score against the resume.
 *
 * The buckets are an ordered quality scale, so they wear the same bands as the
 * `<MatchScore />` pill everywhere else in the app: 85+ strong, 70+ decent, below that
 * muted. Each bar is labelled with its bucket and its count, so the bands are a
 * reinforcement rather than the only way to read the chart.
 */
export function MatchDistributionChart({ rows, height = 220 }: { rows: MatchBucketRow[]; height?: number }) {
  const theme = useChartTheme()
  const axis = axisProps(theme)

  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 20, right: 8, bottom: 4, left: -16 }}>
          <CartesianGrid {...gridProps(theme)} />
          <XAxis dataKey="bucket" tickMargin={8} {...axis} />
          <YAxis allowDecimals={false} width={44} {...axis} />
          <Tooltip
            cursor={{ fill: theme.grid, fillOpacity: 0.35 }}
            content={
              <ChartTooltip
                labelFormatter={(label) => `Match score ${label}`}
                valueFormatter={(value) => `${formatNumber(value)} jobs`}
                nameFormatter={() => ''}
              />
            }
          />
          <Bar dataKey="count" name="Jobs" radius={[4, 4, 0, 0]} maxBarSize={56} isAnimationActive={false}>
            {rows.map((row) => (
              <Cell key={row.bucket} fill={matchBucketColor(row.bucket, theme)} />
            ))}
            <LabelList
              dataKey="count"
              position="top"
              offset={6}
              className="fill-muted-foreground text-xs tabular-nums"
              formatter={(value: number) => formatNumber(value)}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
