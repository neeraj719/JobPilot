import { CheckCircle2, ExternalLink, FileText, Send, Sparkles, SquareStack, X, XCircle } from 'lucide-react'

import { ErrorState } from '@/components/common/ErrorState'
import { MatchScore } from '@/components/common/MatchScore'
import { PriorityBadge } from '@/components/common/PriorityBadge'
import { StatusBadge } from '@/components/common/StatusBadge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { CompanyAvatar } from '@/features/jobs/components/CompanyAvatar'
import { JobDetailSkeleton } from '@/features/jobs/components/JobsSkeletons'
import {
  EMPLOYMENT_TYPE_LABELS,
  WORK_MODE_LABELS,
  formatDate,
  formatExperience,
  formatRelative,
  formatSalaryRange,
  humanizeEnum,
  sourceLabel,
} from '@/lib/utils'
import type { JobDetail, JobSourceRead, UUID } from '@/types/api'

export interface JobDetailSheetProps {
  jobId: UUID | null
  job: JobDetail | undefined
  loading: boolean
  error: unknown
  onRetry: () => void
  onOpenChange: (open: boolean) => void
  onApply: (job: JobDetail) => void
  onQueue: (job: JobDetail) => void
  onAnalyze: (job: JobDetail) => void
  onSkip: (job: JobDetail) => void
  /** Jump to the Approval Center when the job already has an application. */
  onOpenApplication: (applicationId: UUID) => void
  busy?: boolean
}

const MATCH_LABELS: Record<string, string> = {
  STRONG: 'Strong fit',
  GOOD: 'Good fit',
  UNDER: 'Below the asked range',
  OVER: 'Above the asked range',
  MATCH: 'Matches your locations',
  REMOTE_OK: 'Remote — location is moot',
  MISMATCH: 'Outside your locations',
  ABOVE: 'Above your expectation',
  WITHIN: 'Within your expectation',
  BELOW: 'Below your expectation',
  UNKNOWN: 'Not enough data',
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-0.5">
      <dt className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  )
}

function SkillChips({ skills, tone }: { skills: string[]; tone: 'matched' | 'missing' }) {
  if (skills.length === 0) return <span className="text-sm text-muted-foreground">None</span>
  return (
    <div className="flex flex-wrap gap-1">
      {skills.map((skill) => (
        <span
          key={skill}
          className={
            tone === 'matched'
              ? 'inline-flex items-center gap-1 rounded-md border border-success/25 bg-success/10 px-1.5 py-0.5 text-[11px] font-medium text-success'
              : 'inline-flex items-center gap-1 rounded-md border border-warning/25 bg-warning/10 px-1.5 py-0.5 text-[11px] font-medium text-warning'
          }
        >
          {tone === 'matched' ? <CheckCircle2 className="size-3" aria-hidden /> : <XCircle className="size-3" aria-hidden />}
          {skill}
        </span>
      ))}
    </div>
  )
}

/** Side panel with the full posting, its source links and the match breakdown. */
export function JobDetailSheet({
  jobId,
  job,
  loading,
  error,
  onRetry,
  onOpenChange,
  onApply,
  onQueue,
  onAnalyze,
  onSkip,
  onOpenApplication,
  busy = false,
}: JobDetailSheetProps) {
  const sources: JobSourceRead[] = job?.job_sources ?? job?.source_links ?? []
  const alreadyApplied = Boolean(job?.application_status && job.application_status !== 'DISCOVERED')

  return (
    <Sheet open={jobId !== null} onOpenChange={onOpenChange}>
      <SheetContent className="flex w-full flex-col gap-0 p-0 sm:max-w-xl" aria-describedby={undefined}>
        {loading || (!job && !error) ? (
          <>
            <SheetTitle className="sr-only">Loading job</SheetTitle>
            <JobDetailSkeleton />
          </>
        ) : error ? (
          <div className="p-6">
            <ErrorState error={error} onRetry={onRetry} />
          </div>
        ) : job ? (
          <>
            <SheetHeader className="border-b border-border pb-4 pr-12">
              <div className="flex items-start gap-3">
                <CompanyAvatar name={job.company?.name} logoUrl={job.company?.logo_url} size="lg" />
                <div className="min-w-0 flex-1 space-y-1">
                  <SheetTitle className="text-lg leading-snug">{job.title}</SheetTitle>
                  <SheetDescription className="flex flex-wrap items-center gap-1.5">
                    <span className="font-medium text-foreground">{job.company?.name ?? 'Unknown company'}</span>
                    <PriorityBadge priority={job.company_priority} />
                    {job.application_status ? <StatusBadge status={job.application_status} /> : null}
                  </SheetDescription>
                </div>
                <MatchScore score={job.match_score} showBar className="w-16 shrink-0 items-end" />
              </div>
            </SheetHeader>

            <ScrollArea className="flex-1">
              <div className="space-y-5 p-6">
                <dl className="grid grid-cols-2 gap-4">
                  <Field label="Location">
                    {job.location || 'Not specified'}
                    {job.work_mode ? ` · ${WORK_MODE_LABELS[job.work_mode]}` : ''}
                  </Field>
                  <Field label="Salary">
                    {formatSalaryRange(job.salary_min, job.salary_max, job.salary_currency ?? 'INR')}
                  </Field>
                  <Field label="Experience">{formatExperience(job.experience_min, job.experience_max)}</Field>
                  <Field label="Employment">
                    {job.employment_type ? EMPLOYMENT_TYPE_LABELS[job.employment_type] : 'Not specified'}
                  </Field>
                  <Field label="Posted">
                    {job.posted_at ? `${formatDate(job.posted_at)} · ${formatRelative(job.posted_at)}` : 'Unknown'}
                  </Field>
                  <Field label="Apply via">{humanizeEnum(job.application_type)}</Field>
                </dl>

                <Separator />

                <section className="space-y-2">
                  <h3 className="text-sm font-semibold">Where this was found</h3>
                  {sources.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No source links recorded.</p>
                  ) : (
                    <ul className="space-y-1.5">
                      {sources.map((source) => (
                        <li key={source.id} className="flex items-center justify-between gap-2 text-sm">
                          <span className="flex min-w-0 items-center gap-2">
                            <span className="font-medium">{sourceLabel(source.source)}</span>
                            <span className="truncate text-xs text-muted-foreground">{source.external_id}</span>
                          </span>
                          <a
                            href={source.url}
                            target="_blank"
                            rel="noreferrer noopener"
                            className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-primary hover:underline"
                          >
                            Open
                            <ExternalLink className="size-3" aria-hidden />
                          </a>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>

                <Separator />

                <section className="space-y-3">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="text-sm font-semibold">Match breakdown</h3>
                    <Button variant="ghost" size="sm" onClick={() => onAnalyze(job)} loading={busy}>
                      <Sparkles />
                      Re-analyze
                    </Button>
                  </div>
                  {job.match ? (
                    <div className="space-y-3 rounded-lg border border-border bg-muted/30 p-3">
                      <p className="text-sm leading-relaxed text-muted-foreground">{job.match.explanation}</p>
                      <dl className="grid gap-3 sm:grid-cols-2">
                        <Field label="Experience">{MATCH_LABELS[job.match.experience_match ?? 'UNKNOWN']}</Field>
                        <Field label="Location">{MATCH_LABELS[job.match.location_match ?? 'UNKNOWN']}</Field>
                        <Field label="Salary">{MATCH_LABELS[job.match.salary_match ?? 'UNKNOWN']}</Field>
                        <Field label="Company priority">
                          <PriorityBadge priority={job.match.company_priority ?? job.company_priority} verbose />
                        </Field>
                      </dl>
                      <div className="space-y-2">
                        <Field label={`Skills matched (${job.match.skill_match?.matched?.length ?? 0})`}>
                          <SkillChips skills={job.match.skill_match?.matched ?? []} tone="matched" />
                        </Field>
                        <Field label={`Skills missing (${job.match.skill_match?.missing?.length ?? 0})`}>
                          <SkillChips skills={job.match.skill_match?.missing ?? []} tone="missing" />
                        </Field>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      This job has not been scored yet. Run <strong>Analyze match</strong> to see how it fits your resume.
                    </p>
                  )}
                </section>

                <Separator />

                <section className="space-y-2">
                  <h3 className="text-sm font-semibold">Job description</h3>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
                    {job.description || 'No description was captured for this posting.'}
                  </p>
                </section>

                {(job.required_skills?.length ?? 0) > 0 || (job.preferred_skills?.length ?? 0) > 0 ? (
                  <section className="grid gap-3 sm:grid-cols-2">
                    <Field label="Required skills">
                      <SkillChips skills={job.required_skills ?? []} tone="matched" />
                    </Field>
                    <Field label="Preferred skills">
                      <SkillChips skills={job.preferred_skills ?? []} tone="matched" />
                    </Field>
                  </section>
                ) : null}
              </div>
            </ScrollArea>

            <div className="flex flex-wrap items-center gap-2 border-t border-border p-4">
              {alreadyApplied && job.application_id ? (
                <Button className="flex-1" onClick={() => onOpenApplication(job.application_id as UUID)}>
                  <FileText />
                  Open application
                </Button>
              ) : (
                <Button onClick={() => onApply(job)} loading={busy} disabled={alreadyApplied} className="flex-1">
                  <Send />
                  Apply now
                </Button>
              )}
              <Button variant="outline" onClick={() => onQueue(job)} disabled={busy || alreadyApplied}>
                <SquareStack />
                Queue
              </Button>
              <Button variant="ghost" onClick={() => onSkip(job)} disabled={busy}>
                <X />
                Skip
              </Button>
              {job.apply_url ? (
                <Button variant="ghost" size="icon" asChild aria-label="Open the original posting">
                  <a href={job.apply_url} target="_blank" rel="noreferrer noopener">
                    <ExternalLink />
                  </a>
                </Button>
              ) : null}
            </div>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  )
}
