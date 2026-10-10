import { AlertTriangle, ExternalLink, FileText, Info, MapPin } from 'lucide-react'

import { MatchScore } from '@/components/common/MatchScore'
import { PriorityBadge } from '@/components/common/PriorityBadge'
import { SourceBadge } from '@/components/common/SourceBadge'
import { StatusBadge } from '@/components/common/StatusBadge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { AutomationBadge, automationSummary } from '@/features/applications/components/AutomationBadge'
import { CompanyAvatar } from '@/features/jobs/components/CompanyAvatar'
import { formatDate } from '@/lib/utils'
import type { ApplicationDetail, ResumeRead, UUID } from '@/types/api'

export interface ApplicationHeaderProps {
  application: ApplicationDetail
  resumes: ResumeRead[] | undefined
  onResumeChange: (resumeId: UUID) => void
  resumeChanging?: boolean
  actions?: React.ReactNode
}

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-0.5">
      <dt className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  )
}

/** Identity block at the top of the Approval Center. */
export function ApplicationHeader({
  application,
  resumes,
  onResumeChange,
  resumeChanging = false,
  actions,
}: ApplicationHeaderProps) {
  const job = application.job
  const summary = automationSummary(application)
  const companyName = application.company_name ?? job?.company?.name ?? 'Unknown company'
  const applyUrl = application.external_url ?? job?.apply_url ?? job?.canonical_url
  // "Ready for your review" is good news, not a warning; a real failure is.
  const alertVariant =
    application.automation_state === 'FAILED'
      ? 'destructive'
      : application.pause_reason === 'USER_REVIEW'
        ? 'info'
        : 'warning'
  // Once submitted the resume is part of the record; changing it would be a lie.
  const resumeLocked = Boolean(application.applied_at) || application.automation_state === 'RUNNING'

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex min-w-0 items-start gap-4">
          <CompanyAvatar name={companyName} logoUrl={application.company_logo_url ?? job?.company?.logo_url} size="lg" />
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-muted-foreground">{companyName}</span>
              <PriorityBadge priority={application.priority} />
              <SourceBadge source={application.source ?? job?.primary_source} />
            </div>
            <h1 className="text-xl font-semibold leading-snug">
              {application.job_title ?? job?.title ?? 'Application'}
            </h1>
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <MapPin className="size-3.5" aria-hidden />
                {application.location ?? job?.location ?? 'Location not specified'}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={application.status} />
              <AutomationBadge application={application} />
              <MatchScore score={application.match_score} />
            </div>
          </div>
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
      </div>

      {summary.needsUser ? (
        <Alert variant={alertVariant}>
          {application.pause_reason === 'USER_REVIEW' ? <Info aria-hidden /> : <AlertTriangle aria-hidden />}
          <AlertTitle>{summary.label}</AlertTitle>
          <AlertDescription>{summary.detail}</AlertDescription>
        </Alert>
      ) : null}

      <dl className="grid grid-cols-2 gap-4 rounded-lg border border-border bg-card p-4 sm:grid-cols-3 lg:grid-cols-5">
        <Meta label="Applied">{application.applied_at ? formatDate(application.applied_at) : 'Not yet'}</Meta>
        <Meta label="Submitted via">{application.submitted_via ?? '—'}</Meta>
        <Meta label="External id">
          {application.external_application_id ? (
            applyUrl ? (
              <a
                href={applyUrl}
                target="_blank"
                rel="noreferrer noopener"
                className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
              >
                {application.external_application_id}
                <ExternalLink className="size-3" aria-hidden />
              </a>
            ) : (
              application.external_application_id
            )
          ) : (
            '—'
          )}
        </Meta>
        <Meta label="Retries">{application.retry_count}</Meta>
        <Meta label="Resume used">
          {resumeLocked ? (
            <span className="inline-flex items-center gap-1.5">
              <FileText className="size-3.5 text-muted-foreground" aria-hidden />
              {resumes?.find((resume) => resume.id === application.resume_id)?.name ??
                application.review?.resume_name ??
                '—'}
            </span>
          ) : (
            <Select
              value={application.resume_id ?? undefined}
              onValueChange={onResumeChange}
              disabled={resumeChanging || !resumes || resumes.length === 0}
            >
              <SelectTrigger className="h-8 text-xs" aria-label="Resume used for this application">
                <SelectValue placeholder="Pick a resume" />
              </SelectTrigger>
              <SelectContent>
                {(resumes ?? []).map((resume) => (
                  <SelectItem key={resume.id} value={resume.id}>
                    {resume.name}
                    {resume.is_default ? ' (default)' : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </Meta>
      </dl>
    </div>
  )
}
