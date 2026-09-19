import { AlertTriangle, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { errorMessage } from '@/lib/api'
import { cn } from '@/lib/utils'

export interface ErrorStateProps {
  /** Anything thrown by the API client; the message is extracted for you. */
  error?: unknown
  title?: string
  description?: string
  onRetry?: () => void
  retryLabel?: string
  className?: string
  size?: 'sm' | 'md'
}

/** Failure panel with a retry affordance — pair it with a react-query `refetch`. */
export function ErrorState({
  error,
  title = 'Something went wrong',
  description,
  onRetry,
  retryLabel = 'Try again',
  className,
  size = 'md',
}: ErrorStateProps) {
  const message = description ?? (error ? errorMessage(error) : 'The request could not be completed.')

  return (
    <div
      role="alert"
      className={cn(
        'flex flex-col items-center justify-center rounded-lg border border-destructive/30 bg-destructive/5 text-center',
        size === 'md' ? 'gap-3 px-6 py-12' : 'gap-2 px-4 py-8',
        className,
      )}
    >
      <span className="flex size-11 items-center justify-center rounded-full bg-destructive/10 text-destructive">
        <AlertTriangle className="size-5" aria-hidden />
      </span>
      <div className="space-y-1">
        <h3 className="text-base font-semibold text-foreground">{title}</h3>
        <p className="mx-auto max-w-md text-sm text-muted-foreground">{message}</p>
      </div>
      {onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw />
          {retryLabel}
        </Button>
      ) : null}
    </div>
  )
}
