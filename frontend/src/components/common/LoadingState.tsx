import {
  CardGridSkeleton,
  ChartSkeleton,
  DetailSkeleton,
  FormSkeleton,
  ListSkeleton,
  SkeletonRegion,
  StatRowSkeleton,
  TableSkeleton,
} from '@/components/common/skeletons'

export interface LoadingStateProps {
  /** Number of placeholder rows / cards. */
  rows?: number
  className?: string
  /**
   * The shape of what is loading: `list` stacked rows, `table` header + rows, `cards` a grid,
   * `stats` a KPI row, `form` labelled fields, `detail` main + side columns, `chart` a plot.
   */
  variant?: 'list' | 'table' | 'cards' | 'stats' | 'form' | 'detail' | 'chart'
  /** Table columns (variant `table`). */
  cols?: number
  /** What is loading, for screen readers ("Loading resumes"). */
  label?: string
}

/**
 * Skeleton placeholder shown while a query is in flight — shaped like the content, never a
 * spinner. A thin wrapper over the composites in `skeletons.tsx`, kept for its API.
 */
export function LoadingState({ rows = 5, className, variant = 'list', cols = 4, label = 'Loading' }: LoadingStateProps) {
  return (
    <SkeletonRegion label={label} className={className}>
      {variant === 'table' ? <TableSkeleton rows={rows} cols={cols} /> : null}
      {variant === 'cards' ? <CardGridSkeleton count={rows} /> : null}
      {variant === 'stats' ? <StatRowSkeleton count={rows > 4 ? 4 : rows} /> : null}
      {variant === 'form' ? <FormSkeleton fields={rows} /> : null}
      {variant === 'detail' ? <DetailSkeleton /> : null}
      {variant === 'chart' ? <ChartSkeleton /> : null}
      {variant === 'list' ? <ListSkeleton rows={rows} /> : null}
    </SkeletonRegion>
  )
}
