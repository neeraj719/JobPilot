import { FilePlus2, FileText, Upload } from 'lucide-react'
import * as React from 'react'
import { Link } from 'react-router-dom'

import { EmptyState } from '@/components/common/EmptyState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn, formatRelative } from '@/lib/utils'
import type { ResumeRead } from '@/types/api'
import { scoreTone, TONE_TEXT } from '@/features/ats/labels'
import type { AnalysisListItem } from '@/features/ats/types'
import { KindBadge } from '@/features/resume-studio/components/badges'

export interface ResumePickerProps {
  resumes: ResumeRead[]
  value: string | null
  onChange: (id: string) => void
  /** Recent analyses, to show the last estimate of each resume against this job (matched by title + company). */
  analyses?: AnalysisListItem[]
  jdTitle?: string | null
  jdCompany?: string | null
  onUpload: () => void
  disabled?: boolean
}

function same(a: string | null | undefined, b: string | null | undefined): boolean {
  return Boolean(a && b && a.trim().toLowerCase() === b.trim().toLowerCase())
}

/** Step 2: a radio list of the user's resumes (arrow keys move between them). */
export function ResumePicker({ resumes, value, onChange, analyses = [], jdTitle, jdCompany, onUpload, disabled }: ResumePickerProps) {
  const name = React.useId()
  const sourceNames = React.useMemo(() => new Map(resumes.map((r) => [r.id, r.name])), [resumes])

  if (resumes.length === 0) {
    return (
      <EmptyState
        size="sm"
        icon={FileText}
        title="No resume to optimize yet"
        description="Upload the resume you already have, or build one from your profile. Then come back to this step."
        action={
          <div className="flex flex-wrap justify-center gap-2">
            <Button onClick={onUpload}>
              <Upload aria-hidden />
              Upload my resume
            </Button>
            <Button variant="outline" asChild>
              <Link to="/resume/new?mode=profile">
                <FilePlus2 aria-hidden />
                Build from my profile
              </Link>
            </Button>
          </div>
        }
      />
    )
  }

  const lastEstimate = (resume: ResumeRead): AnalysisListItem | undefined =>
    jdTitle
      ? analyses.find(
          (a) => a.resume_id === resume.id && a.status === 'DONE' && same(a.jd_title, jdTitle) && (!jdCompany || same(a.jd_company, jdCompany)),
        )
      : undefined

  return (
    <fieldset className="space-y-2" disabled={disabled}>
      <legend className="sr-only">Resume to optimize</legend>
      <div className="grid gap-2 md:grid-cols-2">
        {resumes.map((resume) => {
          const checked = resume.id === value
          const unreadable = resume.parse_status !== 'PARSED'
          const estimate = lastEstimate(resume)
          return (
            <label
              key={resume.id}
              className={cn(
                'relative flex min-w-0 cursor-pointer gap-3 rounded-xl border bg-card p-3 shadow-xs transition-[border-color,box-shadow,background-color] duration-150',
                'has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-background',
                checked ? 'border-primary/60 bg-primary/5 shadow-sm' : 'border-border hover:border-primary/40',
                unreadable && 'cursor-not-allowed opacity-60',
              )}
            >
              <input
                type="radio"
                name={name}
                value={resume.id}
                checked={checked}
                disabled={unreadable}
                onChange={() => onChange(resume.id)}
                className="mt-1 size-4 shrink-0 accent-[hsl(var(--primary))]"
              />
              <span className="min-w-0 flex-1 space-y-1.5">
                <span className="flex min-w-0 items-center gap-2">
                  <span className="truncate text-sm font-medium" title={resume.name}>
                    {resume.name}
                  </span>
                  {resume.is_default ? <Badge variant="primary">Default</Badge> : null}
                </span>
                <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                  <KindBadge kind={resume.kind} sourceName={resume.source_resume_id ? sourceNames.get(resume.source_resume_id) : null} />
                  <Badge variant="outline" className="tabular-nums">
                    v{resume.current_version}
                  </Badge>
                  <span className="truncate">{resume.target_role || 'No target role'}</span>
                </span>
                <span className="block text-xs text-muted-foreground">
                  {unreadable ? (
                    'Not readable yet: fix it in the editor first.'
                  ) : estimate ? (
                    <>
                      Last estimate for this job:{' '}
                      <span className={cn('font-semibold tabular-nums', TONE_TEXT[scoreTone(estimate.overall_score)])}>{estimate.overall_score ?? '—'}</span>
                      <span> · {formatRelative(estimate.created_at)}</span>
                    </>
                  ) : (
                    `Edited ${formatRelative(resume.updated_at)}`
                  )}
                </span>
              </span>
            </label>
          )
        })}
      </div>
    </fieldset>
  )
}
