import * as React from 'react'

import { cn } from '@/lib/utils'

/**
 * Loading placeholder. A shimmer band sweeps across the `skeleton` base fill (transform only);
 * under `prefers-reduced-motion` it becomes a slow opacity pulse instead (index.css).
 *
 * Rule (docs/DESIGN.md): content loading is ALWAYS a skeleton shaped like the content — never a
 * spinner or a "Loading…" screen. Size it like the real element so nothing shifts on arrival.
 */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('shimmer rounded-md', className)} aria-hidden {...props} />
}

/** A run of text lines; the last one shorter, like a real paragraph. */
export function SkeletonText({ lines = 2, className, lineClassName }: { lines?: number; className?: string; lineClassName?: string }) {
  return (
    <div className={cn('space-y-2', className)} aria-hidden>
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton key={index} className={cn('h-3.5', index === lines - 1 && lines > 1 ? 'w-3/5' : 'w-full', lineClassName)} />
      ))}
    </div>
  )
}
