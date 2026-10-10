import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

function CardSkeleton({ height = 220 }: { height?: number }) {
  return (
    <Card>
      <CardHeader className="space-y-2">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-3 w-56" />
      </CardHeader>
      <CardContent>
        <Skeleton className="w-full" style={{ height }} />
      </CardContent>
    </Card>
  )
}

/** First-paint placeholder for the whole dashboard — same grid, so nothing jumps. */
export function DashboardSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-live="polite">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7">
        {Array.from({ length: 7 }, (_, index) => (
          <Card key={index}>
            <CardContent className="space-y-2 p-5">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-7 w-16" />
              <Skeleton className="h-3 w-20" />
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <CardSkeleton height={200} />
        <CardSkeleton height={200} />
        <CardSkeleton height={200} />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <CardSkeleton height={260} />
        <CardSkeleton height={260} />
        <CardSkeleton height={260} />
      </div>
    </div>
  )
}

/** Same idea for the analytics page. */
export function AnalyticsSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-live="polite">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => (
          <Card key={index}>
            <CardContent className="space-y-2 p-5">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-7 w-16" />
              <Skeleton className="h-3 w-20" />
            </CardContent>
          </Card>
        ))}
      </div>
      <CardSkeleton height={280} />
      <div className="grid gap-4 lg:grid-cols-2">
        <CardSkeleton />
        <CardSkeleton />
      </div>
    </div>
  )
}
