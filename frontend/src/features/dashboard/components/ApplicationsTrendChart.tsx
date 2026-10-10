import * as React from 'react'
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { formatDate, formatNumber } from '@/lib/utils'
import type { DatePoint } from '@/types/api'

import { axisProps, gridProps, useChartTheme } from '../chart-theme'
import { ChartLegend, ChartTooltip } from './ChartTooltip'

export interface TrendPoint {
  date: string
  applications: number
  responses: number
}

/** Align the two per-day series the API returns into one row per day. */
export function buildTrendSeries(applicationsPerDay: DatePoint[], responsesPerDay: DatePoint[]): TrendPoint[] {
  const responses = new Map(responsesPerDay.map((point) => [point.date, point.count]))
  return applicationsPerDay.map((point) => ({
    date: point.date,
    applications: point.count,
    responses: responses.get(point.date) ?? 0,
  }))
}

/**
 * Applications sent per day with responses received overlaid.
 *
 * Both series count the same thing (events per day) so they share **one** y-axis — a
 * second scale would invent a correlation that is not in the data.
 */
export function ApplicationsTrendChart({ data, height = 260 }: { data: TrendPoint[]; height?: number }) {
  const theme = useChartTheme()
  const grid = gridProps(theme)
  const axis = axisProps(theme)

  const totals = React.useMemo(
    () =>
      data.reduce(
        (acc, point) => ({
          applications: acc.applications + point.applications,
          responses: acc.responses + point.responses,
        }),
        { applications: 0, responses: 0 },
      ),
    [data],
  )


  return (
    <div className="space-y-3">
      <div style={{ width: '100%', height }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: -16 }}>
            <CartesianGrid {...grid} />
            <XAxis
              dataKey="date"
              // `preserveStartEnd` + a minimum gap lets Recharts drop as many ticks as the
              // container needs, so the dates never collide on a narrow card or a phone.
              interval="preserveStartEnd"
              tickMargin={8}
              minTickGap={26}
              tickFormatter={(value: string) => formatDate(value, 'd MMM', '')}
              {...axis}
            />
            <YAxis allowDecimals={false} width={44} {...axis} />
            <Tooltip
              cursor={{ fill: theme.grid, fillOpacity: 0.35 }}
              content={
                <ChartTooltip
                  labelFormatter={(label) => formatDate(String(label), 'EEE d MMM yyyy')}
                  valueFormatter={(value) => formatNumber(value)}
                />
              }
            />
            <Bar
              dataKey="applications"
              name="Applications"
              fill={theme.series[0]}
              radius={[4, 4, 0, 0]}
              maxBarSize={24}
            />
            <Line
              type="monotone"
              dataKey="responses"
              name="Responses"
              stroke={theme.series[1]}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              dot={false}
              activeDot={{ r: 4, strokeWidth: 2, stroke: theme.surface }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <ChartLegend
        items={[
          { label: 'Applications', color: theme.series[0] ?? '', value: formatNumber(totals.applications) },
          { label: 'Responses', color: theme.series[1] ?? '', value: formatNumber(totals.responses) },
        ]}
      />
    </div>
  )
}
