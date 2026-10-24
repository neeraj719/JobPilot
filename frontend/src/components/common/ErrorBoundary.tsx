import * as React from 'react'
import { useLocation } from 'react-router-dom'

import { ErrorState } from '@/components/common/ErrorState'
import { cn } from '@/lib/utils'

/** A lazily loaded chunk that failed to download (offline, or a deploy replaced the hashes). */
function isChunkLoadError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error)
  return /dynamically imported module|Importing a module script failed|Failed to fetch|ChunkLoadError|error loading dynamically/i.test(message)
}

interface BoundaryProps {
  children: React.ReactNode
  /** What failed, for the message ("this page", "the chart"…). */
  label?: string
  /** Compact inline fallback for widgets instead of the page-sized one. */
  variant?: 'page' | 'widget'
  className?: string
  /** Changing this value clears the error (e.g. the route path). */
  resetKey?: unknown
}

interface BoundaryState {
  error: unknown
}

/**
 * Catches render errors (and failed chunk downloads) below it and shows a styled fallback
 * with a retry, instead of a blank screen. One per route chunk and per heavy widget (3D scene,
 * charts) so a failure stays local.
 */
export class ErrorBoundary extends React.Component<BoundaryProps, BoundaryState> {
  override state: BoundaryState = { error: null }

  static getDerivedStateFromError(error: unknown): BoundaryState {
    return { error }
  }

  override componentDidUpdate(prev: BoundaryProps) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null })
  }

  override componentDidCatch(error: unknown) {
    if (import.meta.env.DEV) console.error('[ErrorBoundary]', this.props.label ?? 'section', error)
  }

  private retry = () => {
    if (isChunkLoadError(this.state.error)) window.location.reload()
    else this.setState({ error: null })
  }

  override render() {
    const { error } = this.state
    if (!error) return this.props.children
    const chunk = isChunkLoadError(error)
    const what = this.props.label ?? 'this page'
    return (
      <div className={cn(this.props.variant === 'widget' ? 'p-4' : 'mx-auto w-full max-w-3xl px-4 py-12', this.props.className)}>
        <ErrorState
          title={chunk ? `Could not load ${what}` : `Something went wrong in ${what}`}
          description={
            chunk
              ? 'The connection dropped or JobPilot was just updated. Reload to get the latest version.'
              : 'The rest of JobPilot still works. Try again, or reload if it keeps happening.'
          }
          onRetry={this.retry}
          retryLabel={chunk ? 'Reload' : 'Try again'}
          size={this.props.variant === 'widget' ? 'sm' : 'md'}
        />
      </div>
    )
  }
}

/** Route-level boundary that resets when the URL path changes. */
export function RouteErrorBoundary({ children, label }: { children: React.ReactNode; label?: string }) {
  const location = useLocation()
  return (
    <ErrorBoundary label={label} resetKey={location.pathname}>
      {children}
    </ErrorBoundary>
  )
}
