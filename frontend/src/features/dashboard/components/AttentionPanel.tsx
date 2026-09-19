import {
  AlertTriangle,
  CalendarClock,
  CheckCheck,
  ClipboardCheck,
  Mail,
  PencilLine,
  type LucideIcon,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import { EmptyState } from '@/components/common/EmptyState'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { AttentionItem } from '@/types/api'

interface AttentionStyle {
  icon: LucideIcon
  /** Wrapper classes for the icon chip — semantic, and always paired with the text. */
  tone: string
  action: string
}

const STYLES: Record<string, AttentionStyle> = {
  requires_input: { icon: PencilLine, tone: 'bg-warning/15 text-warning', action: 'Answer' },
  pending_review: { icon: ClipboardCheck, tone: 'bg-primary/10 text-primary', action: 'Review' },
  upcoming_interviews: { icon: CalendarClock, tone: 'bg-success/10 text-success', action: 'Prepare' },
  unread_emails: { icon: Mail, tone: 'bg-info/10 text-info', action: 'Read' },
  failed_runs: { icon: AlertTriangle, tone: 'bg-destructive/10 text-destructive', action: 'Inspect' },
}

const FALLBACK: AttentionStyle = { icon: AlertTriangle, tone: 'bg-muted text-muted-foreground', action: 'Open' }

/**
 * "Needs your attention" — the one panel that answers *what do I do now?*
 *
 * Each row is an action, not a statistic: an icon for the kind of work, the server's
 * own sentence, and a button that lands on the screen where the work happens.
 */
export function AttentionPanel({ items, className }: { items: AttentionItem[]; className?: string }) {
  return (
    <Card className={cn('flex min-w-0 flex-col', className)}>
      <CardHeader>
        <CardTitle className="text-base">Needs your attention</CardTitle>
        <CardDescription>Everything waiting on a decision from you.</CardDescription>
      </CardHeader>
      <CardContent className="flex-1">
        {items.length === 0 ? (
          <EmptyState
            size="sm"
            icon={CheckCheck}
            title="All caught up"
            description="Nothing is waiting on you. The automation will keep queueing matches in the background."
          />
        ) : (
          <ul className="space-y-2">
            {items.map((item) => {
              const style = STYLES[item.type] ?? FALLBACK
              const Icon = style.icon
              return (
                <li
                  key={`${item.type}-${item.link}`}
                  className="flex items-center gap-3 rounded-lg border border-border bg-card/60 p-3"
                >
                  <span className={cn('flex size-9 shrink-0 items-center justify-center rounded-lg', style.tone)}>
                    <Icon className="size-4" aria-hidden />
                  </span>
                  {/* The server writes a whole sentence here, so let it wrap rather than
                      clipping it — the count is already inside the sentence. */}
                  <p className="min-w-0 flex-1 text-sm font-medium leading-snug">{item.title}</p>
                  <Button asChild size="sm" variant="outline" className="shrink-0">
                    <Link to={item.link}>{style.action}</Link>
                  </Button>
                </li>
              )
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
