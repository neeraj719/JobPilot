import { Inbox, Link2, Sparkles } from 'lucide-react'

import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { cn, truncate } from '@/lib/utils'
import { formatApiRelative } from '@/features/automation/datetime'
import { ClassificationBadge } from '@/features/emails/components/ClassificationBadge'
import type { ApplicationRead, EmailMessageRead, UUID } from '@/types/api'
import { EmailListSkeleton } from '@/features/emails/components/EmailSkeletons'

export interface EmailListProps {
  emails: EmailMessageRead[] | undefined
  loading?: boolean
  error?: unknown
  onRetry?: () => void
  selectedId: UUID | null
  onSelect: (email: EmailMessageRead) => void
  /** Used to name the application an email is linked to. */
  applicationsById: Map<UUID, ApplicationRead>
  emptyTitle?: string
  emptyDescription?: string
}

/** `"Talent Team" <talent@netflix.com>` -> `Talent Team`; a bare address stays whole. */
function senderName(sender: string): string {
  const named = /^\s*"?([^"<]+?)"?\s*</.exec(sender)
  if (named?.[1]) return named[1].trim()
  return sender.trim() || 'Unknown sender'
}

/** The inbox column: sender, subject, snippet, classification and link state. */
export function EmailList({
  emails,
  loading = false,
  error,
  onRetry,
  selectedId,
  onSelect,
  applicationsById,
  emptyTitle = 'No emails yet',
  emptyDescription = 'Connect Gmail or use “Simulate email” to see how replies are classified and linked.',
}: EmailListProps) {
  if (loading) {
    return (
      <EmailListSkeleton rows={6} />
    )
  }

  if (error) return <ErrorState error={error} size="sm" onRetry={onRetry} className="m-3" />

  if (!emails || emails.length === 0) {
    return <EmptyState size="sm" icon={Inbox} title={emptyTitle} description={emptyDescription} className="m-3" />
  }

  return (
    <ul className="divide-y divide-border">
      {emails.map((email) => {
        const selected = email.id === selectedId
        const application = email.application_id ? applicationsById.get(email.application_id) : undefined
        return (
          <li key={email.id}>
            <button
              type="button"
              onClick={() => onSelect(email)}
              aria-current={selected ? 'true' : undefined}
              className={cn(
                'w-full space-y-1 px-3 py-2.5 text-left transition-colors',
                'hover:bg-accent focus-visible:bg-accent focus-visible:outline-none',
                selected && 'bg-primary/5 shadow-[inset_2px_0_0_0] shadow-primary',
              )}
            >
              <div className="flex items-center gap-2">
                {!email.is_read ? (
                  <span className="size-1.5 shrink-0 rounded-full bg-primary" aria-label="Unread" />
                ) : (
                  <span className="size-1.5 shrink-0" aria-hidden />
                )}
                <span
                  className={cn('min-w-0 flex-1 truncate text-sm', email.is_read ? 'text-muted-foreground' : 'font-semibold')}
                >
                  {senderName(email.sender)}
                </span>
                <time className="shrink-0 text-[11px] text-muted-foreground" dateTime={email.received_at}>
                  {formatApiRelative(email.received_at)}
                </time>
              </div>

              <p className={cn('truncate pl-3.5 text-sm', email.is_read ? 'text-foreground/80' : 'font-medium')}>
                {email.subject || '(no subject)'}
              </p>
              <p className="line-clamp-2 pl-3.5 text-xs text-muted-foreground">
                {truncate(email.snippet ?? email.body_text ?? '', 140)}
              </p>

              <div className="flex flex-wrap items-center gap-1 pl-3.5 pt-0.5">
                <ClassificationBadge
                  classification={email.classification}
                  confidence={email.classification_confidence}
                  size="sm"
                />
                {email.application_id ? (
                  <span className="inline-flex max-w-[12rem] items-center gap-1 rounded-full border border-border bg-muted/60 px-1.5 py-0.5 text-[10px] text-muted-foreground">
                    <Link2 className="size-2.5 shrink-0" aria-hidden />
                    <span className="truncate">{application?.company_name ?? 'Linked'}</span>
                  </span>
                ) : (
                  <span className="rounded-full border border-dashed border-border px-1.5 py-0.5 text-[10px] text-muted-foreground">
                    Unlinked
                  </span>
                )}
                {email.is_simulated ? (
                  <span className="inline-flex items-center gap-1 rounded-full border border-info/25 bg-info/10 px-1.5 py-0.5 text-[10px] text-info">
                    <Sparkles className="size-2.5" aria-hidden />
                    Demo
                  </span>
                ) : null}
              </div>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
