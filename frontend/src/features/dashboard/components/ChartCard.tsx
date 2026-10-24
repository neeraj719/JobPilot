import type { LucideIcon } from 'lucide-react'
import * as React from 'react'

import { ErrorBoundary } from '@/components/common/ErrorBoundary'

import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

export interface ChartCardProps {
  title: string
  description?: React.ReactNode
  /** Range toggles, export buttons — rendered on the right of the header. */
  actions?: React.ReactNode
  /** First load only: shows a skeleton the size of the plot. */
  loading?: boolean
  /** A background refetch: the previous render is held at reduced opacity. */
  refreshing?: boolean
  error?: unknown
  onRetry?: () => void
  /** `true` renders the empty state instead of the children. */
  empty?: boolean
  emptyTitle?: string
  emptyDescription?: string
  emptyIcon?: LucideIcon
  /** Plot height in px — set it tall enough to include the x-axis band. */
  height?: number
  className?: string
  /** Rendered under the plot: the legend, a caption or a table view. */
  footer?: React.ReactNode
  children: React.ReactNode
}

/**
 * The frame every chart on these two pages sits in.
 *
 * It owns the four states a chart can be in (loading / error / empty / data) so the
 * chart components themselves only ever deal with data, and it holds the previous
 * render during a refetch instead of flashing a skeleton.
 */
export function ChartCard({
  title,
  description,
  actions,
  loading = false,
  refreshing = false,
  error,
  onRetry,
  empty = false,
  emptyTitle = 'Nothing to chart yet',
  emptyDescription = 'This chart fills in once you have applications in the selected window.',
  emptyIcon,
  height = 280,
  className,
  footer,
  children,
}: ChartCardProps) {
  return (
    <Card className={cn('flex min-w-0 flex-col', className)}>
      <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <div className="min-w-0 space-y-1">
          <CardTitle className="text-base">{title}</CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
      </CardHeader>
      <CardContent className="flex-1">
        {error ? (
          <ErrorState size="sm" error={error} onRetry={onRetry} title="This chart could not load" />
        ) : loading ? (
          <div className="space-y-3" style={{ minHeight: height }} aria-busy="true" aria-live="polite">
            <Skeleton className="h-full w-full" style={{ height: height - 24 }} />
            <Skeleton className="h-3 w-1/3" />
          </div>
        ) : empty ? (
          <EmptyState size="sm" icon={emptyIcon} title={emptyTitle} description={emptyDescription} />
        ) : (
          <div
            className={cn('transition-opacity duration-200', refreshing && 'opacity-60')}
            aria-busy={refreshing || undefined}
          >
            <ErrorBoundary variant="widget" label="this chart">
              {children}
            </ErrorBoundary>
          </div>
        )}
        {footer && !error && !loading && !empty ? <div className="pt-3">{footer}</div> : null}
      </CardContent>
    </Card>
  )
}
