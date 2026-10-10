import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

export interface LoadingStateProps {
  /** Number of placeholder rows. */
  rows?: number
  className?: string
  /** `list` = stacked cards, `table` = header + rows, `cards` = responsive grid. */
  variant?: 'list' | 'table' | 'cards'
}

/** Skeleton placeholder shown while a query is in flight. */
export function LoadingState({ rows = 5, className, variant = 'list' }: LoadingStateProps) {
  if (variant === 'table') {
    return (
      <div className={cn('space-y-2', className)} aria-busy="true" aria-live="polite">
        <div className="flex items-center gap-4 border-b border-border pb-2">
          {Array.from({ length: 4 }, (_, index) => (
            <Skeleton key={index} className="h-3 flex-1" />
          ))}
        </div>
        {Array.from({ length: rows }, (_, index) => (
          <div key={index} className="flex items-center gap-4 py-2">
            {Array.from({ length: 4 }, (_, cell) => (
              <Skeleton key={cell} className="h-4 flex-1" />
            ))}
          </div>
        ))}
      </div>
    )
  }

  if (variant === 'cards') {
    return (
      <div
        className={cn('grid gap-4 sm:grid-cols-2 xl:grid-cols-3', className)}
        aria-busy="true"
        aria-live="polite"
      >
        {Array.from({ length: rows }, (_, index) => (
          <Card key={index}>
            <CardContent className="space-y-3 p-5">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-3 w-1/3" />
              <div className="flex gap-2 pt-2">
                <Skeleton className="h-5 w-16 rounded-full" />
                <Skeleton className="h-5 w-16 rounded-full" />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }

  return (
    <div className={cn('space-y-3', className)} aria-busy="true" aria-live="polite">
      {Array.from({ length: rows }, (_, index) => (
        <Card key={index}>
          <CardContent className="flex items-center gap-4 p-4">
            <Skeleton className="size-10 shrink-0 rounded-lg" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-1/3" />
              <Skeleton className="h-3 w-1/2" />
            </div>
            <Skeleton className="h-6 w-20 rounded-full" />
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
