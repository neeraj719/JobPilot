import { Linkedin } from 'lucide-react'

import { SkeletonLine, SkeletonRegion } from '@/components/common/skeletons'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { cn, formatDate, formatRelative, initials } from '@/lib/utils'

import type { LinkedInStatus } from '../types'

export function LinkedInStatusBadge({ status }: { status: LinkedInStatus['status'] }) {
  switch (status) {
    case 'connected':
      return <Badge variant="success">Connected</Badge>
    case 'expired':
      return <Badge variant="warning">Sign-in expired</Badge>
    case 'revoked':
      return <Badge variant="warning">Access removed</Badge>
    case 'error':
      return <Badge variant="destructive">Error</Badge>
    default:
      return <Badge variant="muted">Not connected</Badge>
  }
}

/** Avatar + name + email + "Connected · synced 2 hours ago". */
export function LinkedInIdentity({ status, className }: { status: LinkedInStatus; className?: string }) {
  return (
    <div className={cn('flex min-w-0 items-center gap-3', className)}>
      <Avatar className="size-12 ring-2 ring-border">
        {status.picture_url ? <AvatarImage src={status.picture_url} alt="" referrerPolicy="no-referrer" /> : null}
        <AvatarFallback>{initials(status.name, 'in')}</AvatarFallback>
      </Avatar>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate font-display text-base font-semibold">{status.name ?? 'LinkedIn member'}</span>
          <LinkedInStatusBadge status={status.status} />
        </div>
        {status.email ? <p className="truncate text-sm text-muted-foreground">{status.email}</p> : null}
        <p className="text-xs text-muted-foreground">
          {status.connected ? 'Connected' : 'Not syncing'}
          {status.last_synced_at ? ` · synced ${formatRelative(status.last_synced_at)}` : ' · not synced yet'}
        </p>
      </div>
    </div>
  )
}

/** Where the full history came from, in one pill. */
export function LinkedInSourceBadge({ status }: { status: LinkedInStatus }) {
  if (status.history_source === 'dma') return <Badge variant="info">Full profile from LinkedIn</Badge>
  if (status.history_source === 'export') {
    return (
      <Badge variant={status.export_stale ? 'warning' : 'info'}>
        Full history from your export{status.export_imported_at ? ` · ${formatDate(status.export_imported_at)}` : ''}
      </Badge>
    )
  }
  return <Badge variant="muted">Basics only</Badge>
}

export function LinkedInMark({ className }: { className?: string }) {
  return (
    <span className={cn('flex size-9 shrink-0 items-center justify-center rounded-lg bg-gradient-brand text-gradient-foreground shadow-glow', className)}>
      <Linkedin className="size-5" aria-hidden />
    </span>
  )
}

/** Shaped like the connected card: identity row, badges, a row of buttons. */
export function LinkedInCardSkeleton() {
  return (
    <SkeletonRegion label="Loading your LinkedIn connection" className="space-y-4">
      <div className="flex items-center gap-3">
        <Skeleton className="size-12 shrink-0 rounded-full" />
        <div className="min-w-0 flex-1">
          <SkeletonLine size="base" className="w-40" />
          <SkeletonLine size="sm" className="w-56" />
          <SkeletonLine size="xs" className="w-32" />
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Skeleton className="h-6 w-36 rounded-full" />
        <Skeleton className="h-6 w-24 rounded-full" />
      </div>
      <div className="flex flex-wrap gap-2">
        <Skeleton className="h-9 w-28 rounded-lg" />
        <Skeleton className="h-9 w-52 rounded-lg" />
        <Skeleton className="h-9 w-44 rounded-lg" />
      </div>
    </SkeletonRegion>
  )
}

/**
 * `components/ui/switch.tsx` loses its checked fill in dark mode: tailwind-merge reads
 * `bg-gradient-brand` as a colour and drops `bg-primary`, then `dark:bg-none` removes the
 * gradient. Re-adding the colour for dark keeps the switch visible (reported to the theme owner).
 */
export const SWITCH_DARK_FIX = 'dark:data-[state=checked]:bg-primary'
