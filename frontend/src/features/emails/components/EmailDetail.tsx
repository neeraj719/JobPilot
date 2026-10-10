import { ExternalLink, Link2, MailOpen, Sparkles, Unlink } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { EmptyState } from '@/components/common/EmptyState'
import { StatusBadge } from '@/components/common/StatusBadge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { EMAIL_CLASSIFICATION_LABELS } from '@/lib/utils'
import { formatApiDateTime, formatApiRelative } from '@/features/automation/datetime'
import { ClassificationBadge } from '@/features/emails/components/ClassificationBadge'
import { EMAIL_CLASSIFICATIONS, type ApplicationRead, type EmailClassification, type EmailMessageRead } from '@/types/api'

export interface EmailDetailProps {
  email: EmailMessageRead | null
  /** The application the email is linked to, when we know it. */
  application: ApplicationRead | undefined
  loading?: boolean
  markReadPending?: boolean
  classifyPending?: boolean
  unlinkPending?: boolean
  onMarkRead: () => void
  onClassify: (classification: EmailClassification) => void
  onLink: () => void
  onUnlink: () => void
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-2 text-sm">
      <span className="w-16 shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 flex-1 break-words">{children}</span>
    </div>
  )
}

/** Right-hand reading pane: the message, what the classifier thought, and the actions. */
export function EmailDetail({
  email,
  application,
  loading = false,
  markReadPending = false,
  classifyPending = false,
  unlinkPending = false,
  onMarkRead,
  onClassify,
  onLink,
  onUnlink,
}: EmailDetailProps) {
  if (loading) {
    return (
      <div className="space-y-4 p-5">
        <Skeleton className="h-6 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }

  if (!email) {
    return (
      <EmptyState
        icon={MailOpen}
        title="Select an email"
        description="Pick a message on the left to read it, check how it was classified and link it to an application."
        className="m-5 border-none bg-transparent"
      />
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="space-y-3 border-b border-border p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h2 className="min-w-0 flex-1 text-lg font-semibold leading-snug">{email.subject || '(no subject)'}</h2>
          <div className="flex shrink-0 items-center gap-2">
            {!email.is_read ? (
              <Button variant="outline" size="sm" onClick={onMarkRead} loading={markReadPending}>
                <MailOpen />
                Mark read
              </Button>
            ) : (
              <span className="text-xs text-muted-foreground">Read</span>
            )}
          </div>
        </div>

        <div className="space-y-1">
          <Field label="From">
            <span className="font-medium">{email.sender}</span>
          </Field>
          <Field label="Date">
            {formatApiDateTime(email.received_at)}{' '}
            <span className="text-muted-foreground">({formatApiRelative(email.received_at)})</span>
          </Field>
          {email.recipient ? <Field label="To">{email.recipient}</Field> : null}
        </div>

        {email.is_simulated ? (
          <p className="inline-flex items-center gap-1.5 rounded-md border border-info/25 bg-info/10 px-2 py-1 text-xs text-info">
            <Sparkles className="size-3" aria-hidden />
            Simulated message — created by the demo helper, not fetched from Gmail.
          </p>
        ) : null}
      </div>

      <div className="space-y-4 border-b border-border p-5">
        <div className="space-y-2 rounded-lg border border-border bg-muted/30 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <ClassificationBadge classification={email.classification} confidence={email.classification_confidence} />
            {email.classified_by ? (
              <span className="text-xs text-muted-foreground">
                by {email.classified_by.toLowerCase()}
                {email.matched_by ? ` · matched ${email.matched_by.toLowerCase()}` : ''}
              </span>
            ) : null}
            {email.status_applied ? (
              <span className="rounded-full border border-success/25 bg-success/10 px-2 py-0.5 text-[10px] font-medium text-success">
                Status applied
              </span>
            ) : null}
          </div>
          {email.classification_reason ? (
            <p className="text-xs text-muted-foreground">{email.classification_reason}</p>
          ) : null}

          <div className="flex flex-wrap items-end gap-2 pt-1">
            <div className="min-w-[12rem] flex-1 space-y-1">
              <label htmlFor="email-classification" className="text-xs font-medium text-muted-foreground">
                Reclassify
              </label>
              <Select
                value={email.classification}
                onValueChange={(value) => onClassify(value as EmailClassification)}
                disabled={classifyPending}
              >
                <SelectTrigger id="email-classification" className="h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {EMAIL_CLASSIFICATIONS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {EMAIL_CLASSIFICATION_LABELS[option]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <p className="flex-[2] basis-full text-xs text-muted-foreground sm:basis-auto">
              Changing this can move the linked application&apos;s status — an{' '}
              <em>Interview</em> email pushes it to Interview, a <em>Rejection</em> to Rejected.
            </p>
          </div>
        </div>

        {email.application_id ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border p-3">
            <div className="min-w-0">
              <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                <Link2 className="size-3.5" aria-hidden />
                Linked application
              </p>
              <p className="mt-1 truncate text-sm font-medium">
                {application?.company_name ?? 'Application'}
                {application?.job_title ? ` — ${application.job_title}` : ''}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {application ? <StatusBadge status={application.status} /> : null}
              <Button asChild variant="outline" size="sm">
                <Link to={`/applications/${email.application_id}`}>
                  <ExternalLink />
                  Open
                </Link>
              </Button>
              <Button variant="ghost" size="sm" onClick={onUnlink} loading={unlinkPending}>
                <Unlink />
                Unlink
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed border-border p-3">
            <p className="text-sm text-muted-foreground">
              This message is not linked to an application, so it cannot update any status.
            </p>
            <Button variant="outline" size="sm" onClick={onLink} className="shrink-0">
              <Link2 />
              Link to application
            </Button>
          </div>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-5">
        <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-foreground/90">
          {email.body_text || email.snippet || 'This message has no body.'}
        </pre>
      </div>
    </div>
  )
}
