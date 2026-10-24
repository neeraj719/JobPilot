import { type LucideIcon, Inbox } from 'lucide-react'
import * as React from 'react'

import { cn } from '@/lib/utils'

/** The 3D illustrations available for empty states (public/3d/empty-*.webp, CC0 3dicons). */
export type EmptyArt =
  | 'document'
  | 'folder'
  | 'search'
  | 'target'
  | 'calendar'
  | 'mail'
  | 'bell'
  | 'ai'
  | 'rocket'
  | 'lock'
  | 'clock'
  | 'settings'
  | 'profile'
  | 'trophy'
  | 'chart'
  | 'send'
  | 'briefcase'
  | 'star'

/** lucide icon name → the illustration that says the same thing, so existing call sites get
 *  3D art without changes. Unknown icons fall back to the folder. */
const ART_FOR_ICON: Record<string, EmptyArt> = {
  Files: 'document',
  FileText: 'document',
  FilePlus2: 'document',
  FileCheck2: 'document',
  ListChecks: 'document',
  Inbox: 'folder',
  Folder: 'folder',
  FolderOpen: 'folder',
  Search: 'search',
  ScanSearch: 'search',
  SearchX: 'search',
  Crosshair: 'target',
  Target: 'target',
  CircleDot: 'target',
  CalendarClock: 'calendar',
  Calendar: 'calendar',
  CalendarDays: 'calendar',
  Mail: 'mail',
  MailOpen: 'mail',
  Bell: 'bell',
  BellOff: 'bell',
  Sparkles: 'ai',
  BrainCircuit: 'ai',
  Bot: 'ai',
  Wand2: 'ai',
  History: 'clock',
  GitCompareArrows: 'clock',
  Clock: 'clock',
  Hourglass: 'clock',
  UserRound: 'profile',
  User: 'profile',
  Users: 'profile',
  Briefcase: 'briefcase',
  Building2: 'briefcase',
  BarChart3: 'chart',
  LineChart: 'chart',
  ChartColumn: 'chart',
  Send: 'send',
  Lock: 'lock',
  Settings: 'settings',
  Trophy: 'trophy',
  Rocket: 'rocket',
  LayoutGrid: 'star',
}

export interface EmptyStateProps {
  title: string
  description?: string
  /** A lucide icon; also picks the matching 3D illustration unless `art` is given. */
  icon?: LucideIcon
  /** The 3D illustration to show (`'none'` keeps the plain icon chip). */
  art?: EmptyArt | 'none'
  /** Primary call to action, e.g. a `<Button>`. */
  action?: React.ReactNode
  className?: string
  /** `sm` for empty table bodies, `md` for whole pages. */
  size?: 'sm' | 'md'
}

function artFor(icon: LucideIcon, art: EmptyStateProps['art']): EmptyArt | null {
  if (art === 'none') return null
  if (art) return art
  const name = (icon as { displayName?: string }).displayName ?? ''
  return ART_FOR_ICON[name] ?? 'folder'
}

/** The "nothing here yet" panel — every list and page uses this one. v2: a floating 3D
 *  illustration over a soft brand glow instead of a grey icon chip. */
export function EmptyState({ title, description, icon: Icon = Inbox, art, action, className, size = 'md' }: EmptyStateProps) {
  const illustration = artFor(Icon, art)
  const px = size === 'md' ? 112 : 80
  return (
    <div
      className={cn(
        'relative isolate flex flex-col items-center justify-center overflow-hidden rounded-2xl border border-dashed border-border bg-surface-2/60 text-center',
        size === 'md' ? 'gap-3 px-6 py-12' : 'gap-2 px-4 py-8',
        className,
      )}
    >
      {illustration ? (
        <span className="relative" style={{ width: px, height: px }}>
          <span aria-hidden className="absolute inset-[18%] -z-10 rounded-full bg-glow-brand/25 blur-2xl" />
          <img
            src={`/3d/empty-${illustration}-240.webp`}
            srcSet={`/3d/empty-${illustration}-240.webp 240w, /3d/empty-${illustration}.webp 480w`}
            sizes={`${px}px`}
            width={px}
            height={px}
            alt=""
            aria-hidden
            loading="lazy"
            decoding="async"
            className="size-full animate-float select-none object-contain motion-reduce:animate-none"
          />
        </span>
      ) : (
        <span
          className={cn(
            'flex items-center justify-center rounded-full bg-card text-muted-foreground shadow-xs ring-1 ring-border',
            size === 'md' ? 'size-12' : 'size-10',
          )}
        >
          <Icon className={size === 'md' ? 'size-6' : 'size-5'} aria-hidden />
        </span>
      )}
      <div className="space-y-1">
        <h3 className={cn('font-display font-semibold tracking-tight', size === 'md' ? 'text-lg' : 'text-sm')}>{title}</h3>
        {description ? <p className="mx-auto max-w-md text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {action ? <div className="pt-1">{action}</div> : null}
    </div>
  )
}
