import { ArrowRight, RefreshCw, Sparkles } from 'lucide-react'
import type * as React from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn, formatRelative } from '@/lib/utils'
import { healthColor, healthLabel, targetSummaryLine } from '@/features/resume/recommendations'
import type { ResumeRecommendations } from '@/types/api'

const GAUGE_RADIUS = 42
const GAUGE_CIRCUMFERENCE = 2 * Math.PI * GAUGE_RADIUS

/** Ring gauge for the 0–100 health score; the number in the middle carries the meaning. */
function HealthGauge({ score }: { score: number }) {
  const clamped = Math.max(0, Math.min(100, Math.round(score)))
  const offset = GAUGE_CIRCUMFERENCE * (1 - clamped / 100)
  return (
    <div className="relative size-28 shrink-0" role="img" aria-label={`Resume health ${clamped} out of 100`}>
      <svg viewBox="0 0 100 100" className="size-full -rotate-90">
        <circle cx="50" cy="50" r={GAUGE_RADIUS} fill="none" strokeWidth="8" className="stroke-muted" />
        <circle
          cx="50"
          cy="50"
          r={GAUGE_RADIUS}
          fill="none"
          strokeWidth="8"
          strokeLinecap="round"
          stroke="currentColor"
          strokeDasharray={GAUGE_CIRCUMFERENCE}
          strokeDashoffset={offset}
          className={cn('transition-[stroke-dashoffset] duration-500', healthColor(clamped))}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-semibold tabular-nums">{clamped}</span>
        <span className="text-[11px] text-muted-foreground">of 100</span>
      </div>
    </div>
  )
}

function formatScore(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

export interface ResumeHealthCardProps {
  data: ResumeRecommendations
  refreshing: boolean
  onRefresh: () => void
  /** Rendered next to "Refresh analysis" (the "Apply suggestions" button). */
  action?: React.ReactNode
}

/** Overall score, average match now vs projected, and what the analysis looked at. */
export function ResumeHealthCard({ data, refreshing, onRefresh, action }: ResumeHealthCardProps) {
  const { overall_score: score, score_projection: projection, target_summary: summary } = data
  const hasTargets = summary.jobs_analysed > 0
  const gain = projection.delta

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3 space-y-0">
        <div className="min-w-0 space-y-1">
          <CardTitle className="text-base">Resume health</CardTitle>
          <CardDescription>{targetSummaryLine(summary)}</CardDescription>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {action}
          <Button variant="outline" size="sm" onClick={onRefresh} loading={refreshing} disabled={refreshing}>
            {refreshing ? null : <RefreshCw aria-hidden />}
            Refresh analysis
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-6">
          <HealthGauge score={score} />
          <div className="min-w-0 flex-1 space-y-3">
            <p className={cn('text-sm font-medium', healthColor(score))}>{healthLabel(score)}</p>
            {hasTargets ? (
              <div className="space-y-1">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Average match score</p>
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="text-2xl font-semibold tabular-nums">{formatScore(projection.current_average)}</span>
                  <span className="text-xs text-muted-foreground">now</span>
                  {gain > 0 ? (
                    <>
                      <ArrowRight className="size-4 self-center text-muted-foreground" aria-hidden />
                      <span className="text-2xl font-semibold tabular-nums text-success">
                        {formatScore(projection.projected_average)}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        with the high-priority fixes (+{formatScore(gain)}, {projection.jobs_improved}{' '}
                        {projection.jobs_improved === 1 ? 'job' : 'jobs'} improved)
                      </span>
                    </>
                  ) : null}
                </div>
                {projection.added_skills.length > 0 ? (
                  <p className="text-xs text-muted-foreground">
                    Projection assumes you add {projection.added_skills.join(', ')} — only once it is true of you.
                  </p>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          {data.ai_polished ? (
            <Badge variant="muted">
              <Sparkles aria-hidden />
              Wording polished by {data.ai_provider ?? 'AI'}
            </Badge>
          ) : (
            <Badge variant="outline">Rule-based wording</Badge>
          )}
          <span>
            Updated {formatRelative(data.generated_at)} · version {data.resume_version}
          </span>
        </div>
      </CardContent>
    </Card>
  )
}
