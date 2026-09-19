import { Building2, FileText, MapPin, MoreHorizontal, Send, Sparkles, SquareStack, X } from 'lucide-react'

import { MatchScore } from '@/components/common/MatchScore'
import { PriorityBadge } from '@/components/common/PriorityBadge'
import { SourceBadgeList } from '@/components/common/SourceBadge'
import { StatusBadge } from '@/components/common/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { CompanyAvatar } from '@/features/jobs/components/CompanyAvatar'
import {
  WORK_MODE_LABELS,
  cn,
  formatExperience,
  formatRelative,
  formatSalaryRange,
  sourceLabel,
} from '@/lib/utils'
import type { JobCard } from '@/types/api'

export interface JobCardItemProps {
  job: JobCard
  onView: (job: JobCard) => void
  onApply: (job: JobCard) => void
  onQueue: (job: JobCard) => void
  onAnalyze: (job: JobCard) => void
  onSkip: (job: JobCard) => void
  /** Jump to the Approval Center for a job that already has an application. */
  onOpenApplication: (job: JobCard) => void
  /** Id of the job whose mutation is in flight, so only that card shows a spinner. */
  busyJobId?: string | null
  busyAction?: 'apply' | 'queue' | 'analyze' | 'skip' | null
}

const MAX_MISSING_SKILLS = 3

export function JobCardItem({
  job,
  onView,
  onApply,
  onQueue,
  onAnalyze,
  onSkip,
  onOpenApplication,
  busyJobId,
  busyAction,
}: JobCardItemProps) {
  const busy = busyJobId === job.id
  const missing = job.missing_skills ?? []
  const visibleMissing = missing.slice(0, MAX_MISSING_SKILLS)
  const overflowMissing = missing.length - visibleMissing.length
  const alreadyApplied = Boolean(job.application_status && job.application_status !== 'DISCOVERED')
  const extraSources = (job.sources ?? []).filter((source) => source !== job.primary_source)

  return (
    <Card className="flex h-full flex-col transition-shadow hover:shadow-md">
      <CardContent className="flex flex-1 flex-col gap-3 p-4">
        <div className="flex items-center gap-3">
          <CompanyAvatar name={job.company?.name} logoUrl={job.company?.logo_url} size="sm" />
          <div className="flex min-w-0 flex-1 items-center gap-1.5">
            <span className="truncate text-sm font-medium text-muted-foreground" title={job.company?.name ?? undefined}>
              {job.company?.name ?? 'Unknown company'}
            </span>
            <PriorityBadge priority={job.company_priority} />
          </div>
          <MatchScore score={job.match_score} showBar className="w-14 shrink-0 items-end" />
        </div>

        <button
          type="button"
          onClick={() => onView(job)}
          className="line-clamp-2 text-left text-base font-semibold leading-snug hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          {job.title}
        </button>

        <dl className="grid gap-1 text-xs text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <MapPin className="size-3.5 shrink-0" aria-hidden />
            <dt className="sr-only">Location</dt>
            <dd className="truncate">
              {job.location || 'Location not specified'}
              {job.work_mode ? ` · ${WORK_MODE_LABELS[job.work_mode]}` : ''}
            </dd>
          </div>
          <div className="flex items-center gap-1.5">
            <Building2 className="size-3.5 shrink-0" aria-hidden />
            <dt className="sr-only">Salary and experience</dt>
            <dd className="truncate">
              {formatSalaryRange(job.salary_min, job.salary_max, job.salary_currency ?? 'INR')}
              {' · '}
              {formatExperience(job.experience_min, job.experience_max)}
            </dd>
          </div>
        </dl>

        {visibleMissing.length > 0 ? (
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-[11px] font-medium text-muted-foreground">Missing:</span>
            {visibleMissing.map((skill) => (
              <span
                key={skill}
                className="inline-flex items-center rounded-md border border-warning/25 bg-warning/10 px-1.5 py-0.5 text-[11px] font-medium text-warning"
              >
                {skill}
              </span>
            ))}
            {overflowMissing > 0 ? (
              <span
                className="inline-flex items-center rounded-md border border-border bg-muted/60 px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground"
                title={missing.slice(MAX_MISSING_SKILLS).join(', ')}
              >
                +{overflowMissing}
              </span>
            ) : null}
          </div>
        ) : null}

        <div className="mt-auto flex flex-wrap items-center gap-2 pt-1">
          <span title={extraSources.length > 0 ? `Also on ${extraSources.map((s) => sourceLabel(s)).join(', ')}` : undefined}>
            <SourceBadgeList sources={job.sources} max={2} />
          </span>
          {job.application_status ? <StatusBadge status={job.application_status} /> : null}
          <span className="ml-auto whitespace-nowrap text-[11px] text-muted-foreground">
            {job.posted_at ? formatRelative(job.posted_at) : 'Date unknown'}
          </span>
        </div>

        <div className="flex items-center gap-2 border-t border-border pt-3">
          <Button variant="outline" size="sm" onClick={() => onView(job)} className="flex-1">
            View job
          </Button>
          {alreadyApplied && job.application_id ? (
            <Button variant="secondary" size="sm" className="flex-1" onClick={() => onOpenApplication(job)}>
              <FileText />
              Application
            </Button>
          ) : (
            <Button
              size="sm"
              className="flex-1"
              onClick={() => onApply(job)}
              loading={busy && busyAction === 'apply'}
              disabled={busy || alreadyApplied}
              title={alreadyApplied ? 'An application already exists for this job' : 'Queue and start the application'}
            >
              <Send />
              Apply
            </Button>
          )}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label={`More actions for ${job.title}`} disabled={busy}>
                <MoreHorizontal />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => onAnalyze(job)}>
                <Sparkles className={cn(busy && busyAction === 'analyze' && 'animate-pulse')} />
                Analyze match
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => onQueue(job)} disabled={alreadyApplied}>
                <SquareStack />
                Add to queue
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => onSkip(job)} className="text-destructive focus:text-destructive">
                <X />
                Skip this job
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </CardContent>
    </Card>
  )
}
