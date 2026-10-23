import { formatDistanceToNow } from 'date-fns'
import {
  BrainCircuit,
  CalendarClock,
  ChevronRight,
  Crosshair,
  FilePlus2,
  Files,
  PencilLine,
  ScanSearch,
  Sparkles,
  Upload,
  type LucideIcon,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { LoadingState } from '@/components/common/LoadingState'
import { StatCard } from '@/components/common/StatCard'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useAiSettings } from '@/features/ai-providers/api'
import { useAtsSummary } from '@/features/ats/api'
import { TARGET_STATUS_CLASSES, TARGET_STATUS_LABELS, TONE_TEXT, scoreTone } from '@/features/ats/labels'
import { JOB_TARGET_STATUSES } from '@/features/ats/types'
import { useResumeSummary } from '@/features/resume-studio/api'
import { KindBadge } from '@/features/resume-studio/components/badges'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { cn } from '@/lib/utils'

function ago(iso: string | null | undefined): string {
  if (!iso) return ''
  try {
    return formatDistanceToNow(new Date(iso), { addSuffix: true })
  } catch {
    return ''
  }
}

interface QuickAction {
  label: string
  description: string
  to: string
  icon: LucideIcon
}

const QUICK_ACTIONS: QuickAction[] = [
  { label: 'Create a resume', description: 'From your profile or from scratch', to: '/resume/new', icon: FilePlus2 },
  { label: 'Import a resume', description: 'PDF, DOCX, pasted text or LinkedIn export', to: '/resume/new', icon: Upload },
  { label: 'Check against a job', description: 'Estimated ATS score and safe fixes', to: '/resume/ats', icon: ScanSearch },
  { label: 'Tailor for a company', description: 'Save a job target and tailor a copy', to: '/resume/targets', icon: Crosshair },
]

/**
 * `/resume` — the Resume Dashboard. Composes the three summaries the Resume Studio streams
 * expose (`GET /resumes/summary`, `GET /ats/summary`, `GET /ai/settings`); each card loads and
 * fails on its own, so one slow endpoint never blanks the page.
 */
export default function ResumeDashboardPage() {
  useDocumentTitle('Resume Dashboard')
  const resumes = useResumeSummary()
  const ats = useAtsSummary()
  const ai = useAiSettings()

  const resumeData = resumes.data
  const atsData = ats.data
  const isFirstVisit = resumeData !== undefined && resumeData.total === 0

  const latestScore = atsData?.recent_analyses.find((analysis) => analysis.overall_score !== null)?.overall_score ?? null
  const openTargets = atsData
    ? atsData.total_targets - (atsData.targets_by_status.ARCHIVED ?? 0) - (atsData.targets_by_status.REJECTED ?? 0)
    : null

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Resume"
        title="Resume Dashboard"
        description="Your resumes, how they score against real job descriptions, and the jobs you are tailoring them for."
        actions={
          <Button asChild>
            <Link to="/resume/new">
              <FilePlus2 aria-hidden />
              New resume
            </Link>
          </Button>
        }
      />

      {isFirstVisit ? (
        <Card className="border-primary/30 bg-primary/5">
          <CardContent className="flex flex-col gap-4 p-6 sm:flex-row sm:items-center">
            <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary/15 text-primary">
              <Sparkles className="size-5" aria-hidden />
            </span>
            <div className="min-w-0 flex-1">
              <p className="font-semibold">Start with one resume</p>
              <p className="text-sm text-muted-foreground">
                Import the resume you already have or build one from your profile. Then paste a job description to see an
                estimated ATS score and the changes that are safe to make. Nothing is added to your resume without your OK.
              </p>
            </div>
            <Button asChild>
              <Link to="/resume/new">Get started</Link>
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          title="Resumes"
          icon={Files}
          loading={resumes.isLoading}
          value={resumeData?.total ?? '—'}
          description={
            resumeData
              ? `${resumeData.by_kind.TAILORED ?? 0} tailored · ${resumeData.archived} archived`
              : undefined
          }
        />
        <StatCard
          title="Saved job targets"
          icon={Crosshair}
          loading={ats.isLoading}
          value={openTargets ?? '—'}
          description={atsData ? `${atsData.targets_by_status.APPLIED ?? 0} applied · ${atsData.targets_by_status.INTERVIEW ?? 0} interviewing` : undefined}
        />
        <StatCard
          title="Needs your review"
          icon={PencilLine}
          loading={resumes.isLoading}
          value={resumeData ? resumeData.ai_versions_to_review + resumeData.drafts_pending : '—'}
          description={
            resumeData ? `${resumeData.ai_versions_to_review} AI versions · ${resumeData.drafts_pending} unsaved drafts` : undefined
          }
        />
        <StatCard
          title="Latest ATS estimate"
          icon={ScanSearch}
          loading={ats.isLoading}
          value={latestScore !== null ? <span className={TONE_TEXT[scoreTone(latestScore)]}>{latestScore}</span> : '—'}
          description={latestScore !== null ? 'Estimate, not an employer score' : 'No analysis yet'}
        />
      </div>

      <section aria-labelledby="quick-actions" className="space-y-3">
        <h2 id="quick-actions" className="text-sm font-semibold text-muted-foreground">
          Quick actions
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {QUICK_ACTIONS.map((action) => (
            <Link
              key={action.label}
              to={action.to}
              className="group flex items-center gap-3 rounded-lg border bg-card p-4 transition-colors hover:border-primary/40 hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                <action.icon className="size-4" aria-hidden />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium">{action.label}</span>
                <span className="block truncate text-xs text-muted-foreground">{action.description}</span>
              </span>
              <ChevronRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" aria-hidden />
            </Link>
          ))}
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex-row items-start justify-between space-y-0">
            <div>
              <CardTitle className="text-base">Recently edited</CardTitle>
              <CardDescription>Pick up where you left off.</CardDescription>
            </div>
            <Button variant="ghost" size="sm" asChild>
              <Link to="/resume/my">All resumes</Link>
            </Button>
          </CardHeader>
          <CardContent>
            {resumes.isLoading ? (
              <LoadingState rows={3} />
            ) : resumes.isError ? (
              <ErrorState title="Could not load your resumes" error={resumes.error} onRetry={() => resumes.refetch()} />
            ) : !resumeData?.recently_edited.length ? (
              <EmptyState size="sm" icon={Files} title="No resumes yet" description="Create or import one to see it here." />
            ) : (
              <ul className="divide-y">
                {resumeData.recently_edited.map((resume) => (
                  <li key={resume.id}>
                    <Link
                      to={`/resume/my/${resume.id}`}
                      className="flex items-center gap-3 rounded-md py-2.5 hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">
                          {resume.name}
                          {resume.id === resumeData.default_resume_id ? (
                            <span className="ml-2 text-xs font-normal text-muted-foreground">Default</span>
                          ) : null}
                        </p>
                        <p className="truncate text-xs text-muted-foreground">
                          {resume.target_role ?? 'No target role'} · v{resume.current_version} · {ago(resume.updated_at)}
                          {resume.has_draft ? ' · unsaved draft' : ''}
                        </p>
                      </div>
                      <KindBadge kind={resume.kind} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-start justify-between space-y-0">
            <div>
              <CardTitle className="text-base">Recent ATS analyses</CardTitle>
              <CardDescription>Estimated compatibility against the job descriptions you checked.</CardDescription>
            </div>
            <Button variant="ghost" size="sm" asChild>
              <Link to="/resume/ats">Analyse</Link>
            </Button>
          </CardHeader>
          <CardContent>
            {ats.isLoading ? (
              <LoadingState rows={3} />
            ) : ats.isError ? (
              <ErrorState title="Could not load your analyses" error={ats.error} onRetry={() => ats.refetch()} />
            ) : !atsData?.recent_analyses.length ? (
              <EmptyState
                size="sm"
                icon={ScanSearch}
                title="No analyses yet"
                description="Paste a job description in the ATS Optimizer to get an estimated score."
              />
            ) : (
              <ul className="divide-y">
                {atsData.recent_analyses.map((analysis) => (
                  <li key={analysis.id}>
                    <Link
                      to={`/resume/ats?analysis=${analysis.id}`}
                      className="flex items-center gap-3 rounded-md py-2.5 hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <span
                        className={cn(
                          'w-10 shrink-0 text-center text-lg font-semibold tabular-nums',
                          TONE_TEXT[scoreTone(analysis.overall_score)],
                        )}
                      >
                        {analysis.overall_score ?? '–'}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">
                          {[analysis.jd_title, analysis.jd_company].filter(Boolean).join(' · ') || 'Job description'}
                        </p>
                        <p className="truncate text-xs text-muted-foreground">
                          {analysis.resume_name ?? 'Resume'} v{analysis.resume_version} · {ago(analysis.created_at)}
                        </p>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex-row items-start justify-between space-y-0">
            <div>
              <CardTitle className="text-base">Job-specific resumes</CardTitle>
              <CardDescription>Where each saved job stands.</CardDescription>
            </div>
            <Button variant="ghost" size="sm" asChild>
              <Link to="/resume/targets">All targets</Link>
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            {ats.isLoading ? (
              <LoadingState rows={2} />
            ) : ats.isError ? null : !atsData?.total_targets ? (
              <EmptyState
                size="sm"
                icon={Crosshair}
                title="No job targets yet"
                description="Save a company and role to tailor a resume for it and track the application."
              />
            ) : (
              <>
                <div className="flex flex-wrap gap-2">
                  {JOB_TARGET_STATUSES.filter((status) => (atsData.targets_by_status[status] ?? 0) > 0).map((status) => (
                    <Link
                      key={status}
                      to="/resume/targets"
                      className={cn(
                        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium',
                        TARGET_STATUS_CLASSES[status],
                      )}
                    >
                      {TARGET_STATUS_LABELS[status]}
                      <span className="tabular-nums">{atsData.targets_by_status[status]}</span>
                    </Link>
                  ))}
                </div>
                {atsData.in_progress.length ? (
                  <ul className="divide-y">
                    {atsData.in_progress.map((target) => (
                      <li key={target.id}>
                        <Link
                          to={`/resume/targets/${target.id}`}
                          className="flex items-center gap-3 rounded-md py-2.5 hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-medium">{target.role_title}</p>
                            <p className="truncate text-xs text-muted-foreground">{target.company_name}</p>
                          </div>
                          <span
                            className={cn('rounded-full border px-2 py-0.5 text-xs', TARGET_STATUS_CLASSES[target.status])}
                          >
                            {TARGET_STATUS_LABELS[target.status]}
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </>
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <CalendarClock className="size-4 text-muted-foreground" aria-hidden />
                Coming up
              </CardTitle>
              <CardDescription>Deadlines and follow-ups.</CardDescription>
            </CardHeader>
            <CardContent>
              {ats.isLoading ? (
                <LoadingState rows={2} />
              ) : !atsData?.upcoming.length ? (
                <p className="text-sm text-muted-foreground">Nothing scheduled.</p>
              ) : (
                <ul className="space-y-2">
                  {atsData.upcoming.map((target) => {
                    const when = target.deadline ?? target.follow_up_at
                    return (
                      <li key={target.id}>
                        <Link to={`/resume/targets/${target.id}`} className="block rounded-md text-sm hover:underline">
                          <span className="font-medium">{target.company_name}</span> · {target.role_title}
                          <span className="block text-xs text-muted-foreground">
                            {target.deadline ? 'Deadline' : 'Follow up'} {ago(when)}
                          </span>
                        </Link>
                      </li>
                    )
                  })}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <BrainCircuit className="size-4 text-muted-foreground" aria-hidden />
                AI model
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {ai.isLoading ? (
                <LoadingState rows={1} />
              ) : ai.isError ? (
                <p className="text-sm text-muted-foreground">Could not read your AI settings.</p>
              ) : (
                <>
                  <p className="text-sm">{ai.data?.summary}</p>
                  {ai.data?.status.problem ? <p className="text-xs text-destructive">{ai.data.status.problem}</p> : null}
                </>
              )}
              <Button variant="outline" size="sm" asChild>
                <Link to="/resume/ai-settings">AI Model Settings</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </PageContainer>
  )
}
