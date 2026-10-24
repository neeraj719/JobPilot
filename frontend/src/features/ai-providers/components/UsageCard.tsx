import { BarChart3 } from 'lucide-react'
import * as React from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { formatDate, formatNumber } from '@/lib/utils'
import { axisProps, gridProps, useChartTheme } from '@/features/dashboard/chart-theme'
import { ChartTooltip } from '@/features/dashboard/components/ChartTooltip'
import { useAiUsage } from '@/features/ai-providers/api'
import { UsageBodySkeleton } from '@/features/ai-providers/components/AiProvidersSkeleton'
import { formatUsd } from '@/features/ai-providers/schema'
import type { UsageGroup, UsageRange } from '@/features/ai-providers/types'

const RANGES: { id: UsageRange; label: string }[] = [
  { id: '7d', label: '7 days' },
  { id: '30d', label: '30 days' },
  { id: 'month', label: 'This month' },
]

function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: React.ReactNode }) {
  return (
    <div className="rounded-lg border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums">{value}</p>
      {hint ? <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  )
}

function GroupTable({ caption, rows }: { caption: string; rows: UsageGroup[] }) {
  if (!rows.length) return null
  return (
    <div className="overflow-x-auto rounded-lg border">
      <Table>
        <caption className="sr-only">{caption}</caption>
        <TableHeader>
          <TableRow>
            <TableHead>{caption}</TableHead>
            <TableHead className="text-right">Calls</TableHead>
            <TableHead className="text-right">Errors</TableHead>
            <TableHead className="text-right">Tokens in / out</TableHead>
            <TableHead className="text-right">Est. cost</TableHead>
            <TableHead className="text-right">Avg time</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.key}>
              <TableCell className="font-medium">{row.label ?? row.key}</TableCell>
              <TableCell className="text-right tabular-nums">{formatNumber(row.calls)}</TableCell>
              <TableCell className="text-right tabular-nums">{row.errors ? formatNumber(row.errors) : '—'}</TableCell>
              <TableCell className="text-right tabular-nums">
                {formatNumber(row.input_tokens)} / {formatNumber(row.output_tokens)}
                {row.tokens_estimated_calls ? <span className="text-muted-foreground"> ~</span> : null}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {formatUsd(row.estimated_cost_usd)}
                {row.cost_unknown_calls ? <span className="text-muted-foreground"> +?</span> : null}
              </TableCell>
              <TableCell className="text-right tabular-nums">{row.avg_duration_ms != null ? `${(row.avg_duration_ms / 1000).toFixed(1)} s` : '—'}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

/** Calls, tokens and the estimated cost of the user's AI usage. */
export function UsageCard() {
  const [range, setRange] = React.useState<UsageRange>('30d')
  const usage = useAiUsage(range)
  const theme = useChartTheme()
  const data = usage.data
  const pricesAsOf = data ? Object.entries(data.prices_as_of) : []

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3 space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <BarChart3 className="size-4" aria-hidden /> Usage and estimated cost
          </CardTitle>
          <CardDescription>Every real model call is counted. Costs are estimates; your provider’s billing page is the source of truth.</CardDescription>
        </div>
        <Tabs value={range} onValueChange={(value) => setRange(value as UsageRange)}>
          <TabsList aria-label="Usage period">
            {RANGES.map((r) => (
              <TabsTrigger key={r.id} value={r.id}>
                {r.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </CardHeader>
      <CardContent className="space-y-4">
        {usage.isLoading ? (
          <UsageBodySkeleton />
        ) : usage.error ? (
          <ErrorState error={usage.error} size="sm" onRetry={() => void usage.refetch()} />
        ) : !data || data.totals.calls === 0 ? (
          <EmptyState
            size="sm"
            icon={BarChart3}
            title="No AI calls in this period"
            description="Calls answered by the built-in rules are free and not counted. Parse a resume or analyse a job to see usage here."
          />
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat label="Model calls" value={formatNumber(data.totals.calls)} hint={`${data.totals.errors} failed · ${data.totals.fallbacks} via fallback`} />
              <Stat
                label="Estimated cost"
                value={formatUsd(data.totals.estimated_cost_usd)}
                hint={data.totals.cost_unknown_calls ? `+ ${data.totals.cost_unknown_calls} calls with unknown pricing` : 'estimate'}
              />
              <Stat
                label="Tokens in / out"
                value={`${formatNumber(data.totals.input_tokens)} / ${formatNumber(data.totals.output_tokens)}`}
                hint={data.totals.tokens_estimated_calls ? `${data.totals.tokens_estimated_calls} calls estimated from text length` : 'reported by the provider'}
              />
              <Stat
                label="Today"
                value={`${data.limits.calls_today ?? 0}${data.limits.daily_call_limit ? ` / ${data.limits.daily_call_limit}` : ''} ${(data.limits.daily_call_limit ?? data.limits.calls_today) === 1 ? 'call' : 'calls'}`}
                hint={
                  data.limits.monthly_budget_usd != null
                    ? `${formatUsd(data.limits.spent_this_month_usd ?? 0)} of ${formatUsd(data.limits.monthly_budget_usd, 2)} this month`
                    : `${formatUsd(data.limits.spent_this_month_usd ?? 0)} this month`
                }
              />
            </div>

            <div style={{ width: '100%', height: 180 }} aria-label="Calls per day" role="img">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.daily} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
                  <CartesianGrid {...gridProps(theme)} />
                  <XAxis dataKey="date" tickFormatter={(value) => formatDate(value, 'd MMM', value)} tickMargin={6} minTickGap={16} {...axisProps(theme)} />
                  <YAxis allowDecimals={false} width={40} {...axisProps(theme)} />
                  <Tooltip
                    cursor={{ fill: theme.grid, opacity: 0.4 }}
                    content={
                      <ChartTooltip
                        labelFormatter={(label) => formatDate(String(label), 'EEE d MMM', String(label))}
                        valueFormatter={(value) => String(value)}
                      />
                    }
                  />
                  <Bar dataKey="calls" name="Calls" fill={theme.primarySeries} radius={[3, 3, 0, 0]} />
                  <Bar dataKey="errors" name="Failed" fill={theme.destructive} radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <GroupTable caption="Task" rows={data.by_workflow} />
            <GroupTable caption="Provider · model" rows={data.by_provider} />
          </>
        )}
        <p className="text-xs text-muted-foreground">
          {data?.note}
          {pricesAsOf.length ? ` Prices as of ${pricesAsOf.map(([p, d]) => `${p} ${d}`).join(', ')}.` : ''} “~” marks estimated token counts.
        </p>
      </CardContent>
    </Card>
  )
}
