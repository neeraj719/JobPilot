import { PriorityBadge } from '@/components/common/PriorityBadge'
import { SourceBadge } from '@/components/common/SourceBadge'
import { StatusBadge } from '@/components/common/StatusBadge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn, formatNumber, formatPercent } from '@/lib/utils'
import type { ApplicationStatus } from '@/types/api'

import type { PriorityRateRow, SourceRateRow } from '../analytics'
import { useChartTheme } from '../chart-theme'

/** A percentage rendered as a number plus a thin track, so the eye can scan the column. */
function RateCell({ value, tone = 'primary' }: { value: number; tone?: 'primary' | 'success' }) {
  const theme = useChartTheme()
  const color = tone === 'success' ? theme.success : theme.primarySeries
  return (
    <div className="flex items-center justify-end gap-2">
      <span className="tabular-nums">{formatPercent(value, 0)}</span>
      <span aria-hidden className="h-1.5 w-14 shrink-0 overflow-hidden rounded-full bg-muted">
        <span
          className="block h-full rounded-full"
          style={{ width: `${Math.min(100, Math.max(0, value))}%`, backgroundColor: color }}
        />
      </span>
    </div>
  )
}

/**
 * Which platforms actually get replies.
 *
 * Counted the same way the server counts its own `response_rate`: only submitted
 * applications are in the denominator, and an application counts as answered when it
 * has a recorded response or sits in a post-response status.
 */
export function SourceRateTable({
  rows,
  colors,
  className,
}: {
  rows: SourceRateRow[]
  /** Source -> colour, shared with the donut so a platform keeps its hue. */
  colors?: Record<string, string>
  className?: string
}) {
  return (
    <Table className={className}>
      <TableHeader>
        <TableRow>
          <TableHead>Source</TableHead>
          <TableHead className="text-right">Sent</TableHead>
          <TableHead className="text-right">Replied</TableHead>
          <TableHead className="text-right">Interviews</TableHead>
          <TableHead className="text-right">Response rate</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.source}>
            <TableCell>
              <span className="flex items-center gap-2">
                {colors?.[row.source] ? (
                  <span
                    aria-hidden
                    className="size-2.5 shrink-0 rounded-sm"
                    style={{ backgroundColor: colors[row.source] }}
                  />
                ) : null}
                <SourceBadge source={row.source} />
              </span>
            </TableCell>
            <TableCell className="text-right tabular-nums">{formatNumber(row.sent)}</TableCell>
            <TableCell className="text-right tabular-nums">{formatNumber(row.responded)}</TableCell>
            <TableCell className="text-right tabular-nums">{formatNumber(row.interviews)}</TableCell>
            <TableCell className="text-right">
              <RateCell value={row.responseRate} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

/**
 * Does aiming at the dream companies pay off?
 *
 * "Reached interview" is the share of submitted applications now sitting in the
 * interview or offer stage — the list endpoint carries the current status, not the full
 * history, so an application that was interviewed and then rejected is not counted.
 */
export function PriorityConversionTable({ rows, className }: { rows: PriorityRateRow[]; className?: string }) {
  return (
    <Table className={className}>
      <TableHeader>
        <TableRow>
          <TableHead>Company priority</TableHead>
          <TableHead className="text-right">Sent</TableHead>
          <TableHead className="text-right">Replied</TableHead>
          <TableHead className="text-right">Offers</TableHead>
          <TableHead className="text-right">Reached interview</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.priority}>
            <TableCell>
              <PriorityBadge priority={row.priority} verbose />
            </TableCell>
            <TableCell className="text-right tabular-nums">{formatNumber(row.sent)}</TableCell>
            <TableCell className="text-right tabular-nums">{formatNumber(row.responded)}</TableCell>
            <TableCell className="text-right tabular-nums">{formatNumber(row.offers)}</TableCell>
            <TableCell className="text-right">
              <RateCell value={row.interviewRate} tone="success" />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

/** The table twin of the status chart — every value readable without hovering. */
export function StatusTable({
  rows,
  className,
}: {
  rows: { status: ApplicationStatus; count: number }[]
  className?: string
}) {
  const total = rows.reduce((sum, row) => sum + row.count, 0)
  return (
    <Table className={className}>
      <TableHeader>
        <TableRow>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Applications</TableHead>
          <TableHead className="text-right">Share</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.status}>
            <TableCell>
              <StatusBadge status={row.status} />
            </TableCell>
            <TableCell className="text-right tabular-nums">{formatNumber(row.count)}</TableCell>
            <TableCell className={cn('text-right tabular-nums', row.count === 0 && 'text-muted-foreground')}>
              {formatPercent(total > 0 ? (row.count / total) * 100 : 0, 1)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

/** The table twin of the match-score chart. */
export function MatchDistributionTable({
  rows,
  className,
}: {
  rows: { bucket: string; count: number }[]
  className?: string
}) {
  const total = rows.reduce((sum, row) => sum + row.count, 0)
  return (
    <Table className={className}>
      <TableHeader>
        <TableRow>
          <TableHead>Match score</TableHead>
          <TableHead className="text-right">Jobs</TableHead>
          <TableHead className="text-right">Share</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.bucket}>
            <TableCell className="tabular-nums">{row.bucket}</TableCell>
            <TableCell className="text-right tabular-nums">{formatNumber(row.count)}</TableCell>
            <TableCell className="text-right tabular-nums">
              {formatPercent(total > 0 ? (row.count / total) * 100 : 0, 1)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
