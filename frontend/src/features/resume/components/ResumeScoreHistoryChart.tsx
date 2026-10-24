import { LineChart as LineChartIcon } from 'lucide-react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { ErrorBoundary } from '@/components/common/ErrorBoundary'
import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { ScoreHistoryPlotSkeleton } from '@/features/resume/components/ResumeSkeletons'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatDate } from '@/lib/utils'
import { axisProps, gridProps, useChartTheme } from '@/features/dashboard/chart-theme'
import { ChartLegend, ChartTooltip } from '@/features/dashboard/components/ChartTooltip'
import { useRecommendationHistory } from '@/features/resume/api'

const SERIES = [
  { key: 'overall_score', label: 'Resume health' },
  { key: 'average_match_score', label: 'Average match score' },
] as const

/**
 * "Before and after" across resume versions. Both series are 0–100 scores, so they
 * share one axis; every version is re-scored against today's target jobs, which keeps
 * the comparison about the resume rather than about the job market.
 */
export function ResumeScoreHistoryChart({ resumeId }: { resumeId: string }) {
  const history = useRecommendationHistory(resumeId)
  const theme = useChartTheme()
  const data = (history.data ?? []).map((point) => ({ ...point, label: `v${point.version_number}` }))

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Before and after</CardTitle>
        <CardDescription>Each saved version scored against your current target jobs.</CardDescription>
      </CardHeader>
      <CardContent>
        {history.isLoading ? (
          <ScoreHistoryPlotSkeleton />
        ) : history.error ? (
          <ErrorState error={history.error} size="sm" onRetry={() => void history.refetch()} />
        ) : data.length < 2 ? (
          <EmptyState
            size="sm"
            icon={LineChartIcon}
            title={data.length === 1 ? 'Only one version so far' : 'No versions yet'}
            description="Apply a recommendation and save the extracted information to see the change here."
          />
        ) : (
          <div className="space-y-3">
            <ErrorBoundary variant="widget" label="the score chart">
            <div style={{ width: '100%', height: 220 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -16 }}>
                  <CartesianGrid {...gridProps(theme)} />
                  <XAxis dataKey="label" tickMargin={8} {...axisProps(theme)} />
                  <YAxis domain={[0, 100]} allowDecimals={false} width={44} {...axisProps(theme)} />
                  <Tooltip
                    content={
                      <ChartTooltip
                        labelFormatter={(label) => {
                          const point = data.find((item) => item.label === label)
                          const when = point?.created_at ? formatDate(point.created_at, 'd MMM yyyy', '') : ''
                          return [`Version ${String(label).slice(1)}`, when].filter(Boolean).join(' · ')
                        }}
                        valueFormatter={(value) => (Number.isInteger(value) ? String(value) : value.toFixed(1))}
                      />
                    }
                  />
                  {SERIES.map((series, index) => (
                    <Line
                      key={series.key}
                      type="monotone"
                      dataKey={series.key}
                      name={series.label}
                      stroke={theme.series[index]}
                      strokeWidth={2}
                      dot={{ r: 3, strokeWidth: 0, fill: theme.series[index] }}
                      activeDot={{ r: 5, strokeWidth: 2, stroke: theme.surface }}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
            </ErrorBoundary>
            <ChartLegend
              markShape="line"
              items={SERIES.map((series, index) => ({
                label: series.label,
                color: theme.series[index] ?? '',
                value: String(data[data.length - 1]?.[series.key] ?? ''),
              }))}
            />
          </div>
        )}
      </CardContent>
    </Card>
  )
}
