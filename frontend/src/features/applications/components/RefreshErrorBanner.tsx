import { AlertTriangle, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { errorMessage } from '@/lib/api'
import { cn } from '@/lib/utils'

export interface RefreshErrorBannerProps {
  error: unknown
  onRetry?: () => void
  className?: string
}

/**
 * Shown when a *background* refresh fails but we still hold good data — a polling
 * page must not throw away what the user is reading because one poll was rate-limited.
 */
export function RefreshErrorBanner({ error, onRetry, className }: RefreshErrorBannerProps) {
  return (
    <div
      role="status"
      className={cn(
        'flex flex-wrap items-center gap-2 rounded-lg border border-warning/30 bg-warning/5 px-3 py-2 text-sm text-warning',
        className,
      )}
    >
      <AlertTriangle className="size-4 shrink-0" aria-hidden />
      <span className="min-w-0 flex-1">Showing the last loaded data — {errorMessage(error).toLowerCase()}</span>
      {onRetry ? (
        <Button variant="ghost" size="sm" onClick={onRetry} className="text-warning hover:text-warning">
          <RefreshCw />
          Retry
        </Button>
      ) : null}
    </div>
  )
}
