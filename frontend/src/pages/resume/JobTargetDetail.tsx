import {
  Check,
  Archive,
  ArrowLeft,
  Briefcase,
  ExternalLink,
  FileDown,
  GitCompare,
  History,
  PencilLine,
  RefreshCw,
  ScanSearch,
  Sparkles,
  Trash2,
} from 'lucide-react'
import * as React from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { toast } from '@/components/ui/toaster'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { errorMessage } from '@/lib/api'
import { cn, formatDate, formatDateTime, formatRelative, humanizeEnum } from '@/lib/utils'
import { useResumes } from '@/features/resume/api'
import {
  downloadResumeExport,
  useAddSnapshot,
  useDeleteTarget,
  useRefreshTarget,
  useTailor,
  useTarget,
  useUpdateTarget,
  useUploadSnapshot,
} from '@/features/ats/api'
import { JobTargetDetailSkeleton } from '@/features/ats/components/AtsSkeletons'
import { CompareView } from '@/features/ats/components/CompareView'
import { ScoreRing } from '@/features/ats/components/ScoreRing'
import { StructuredJdView } from '@/features/ats/components/StructuredJdView'
import { TargetDueBadges, TargetStatusBadge } from '@/features/ats/components/TargetBadges'
import { JD_SOURCE_LABELS, TARGET_STATUS_LABELS } from '@/features/ats/labels'
import { JOB_TARGET_STATUSES, type JobTargetDetail, type JobTargetStatus } from '@/features/ats/types'
import { InlineEdit } from '@/features/ats/tailor/InlineEdit'
import { AiRunButton } from '@/features/ai-providers/components/AiRunButton'
import type { WorkflowTarget } from '@/features/ai-providers/types'

const NONE = '__none__'

function dateInput(value: string | null): string {
  return value ? value.slice(0, 10) : ''
}

function toIso(date: string): string | null {
  return date ? new Date(`${date}T09:00:00`).toISOString() : null
}

function JdCard({ target }: { target: JobTargetDetail }) {
  const refresh = useRefreshTarget(target.id)
  const addSnapshot = useAddSnapshot(target.id)
  const upload = useUploadSnapshot(target.id)
  const [editing, setEditing] = React.useState(false)
  const [text, setText] = React.useState('')
  const snapshot = target.latest_snapshot
  const fileRef = React.useRef<HTMLInputElement>(null)

  const report = (created: boolean, changed: boolean) => {
    if (!created) toast.info('No change', { description: 'The job description is the same as the saved one.' })
    else if (changed) toast.success('Job description updated', { description: 'Changed requirements are highlighted. Re-run the analysis to see the new estimate.' })
    else toast.success('Job description saved')
  }

  const doRefresh = async () => {
    try {
      const result = await refresh.mutateAsync()
      report(result.created, result.snapshot.changed_from_previous)
    } catch (error) {
      toast.error('Could not refresh', { description: errorMessage(error) })
    }
  }

  const savePasted = async () => {
    try {
      const result = await addSnapshot.mutateAsync({ source: 'PASTED', text })
      setEditing(false)
      setText('')
      report(result.created, result.snapshot.changed_from_previous)
    } catch (error) {
      toast.error('Could not save the job description', { description: errorMessage(error) })
    }
  }

  const onFile = async (file: File) => {
    try {
      const result = await upload.mutateAsync(file)
      report(result.created, result.snapshot.changed_from_previous)
    } catch (error) {
      toast.error('Could not read the file', { description: errorMessage(error) })
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2 pb-3">
        <div className="space-y-1">
          <CardTitle>Job description</CardTitle>
          <CardDescription>
            {snapshot
              ? `${JD_SOURCE_LABELS[snapshot.source]} · saved ${formatRelative(snapshot.created_at)}${target.snapshots.length > 1 ? ` · ${target.snapshots.length} versions` : ''}`
              : 'Not added yet: paste it, upload it or read it from the posting URL.'}
          </CardDescription>
        </div>
        <div className="flex flex-wrap gap-2">
          {target.job_url ? (
            <Button size="sm" variant="outline" onClick={() => void doRefresh()} loading={refresh.isPending}>
              <RefreshCw aria-hidden />
              Refresh from URL
            </Button>
          ) : null}
          <Button size="sm" variant="outline" onClick={() => setEditing((value) => !value)}>
            <PencilLine aria-hidden />
            {snapshot ? 'Paste update' : 'Paste'}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => fileRef.current?.click()} loading={upload.isPending}>
            Upload
          </Button>
          <input
            ref={fileRef}
            type="file"
            className="hidden"
            accept=".pdf,.docx,.txt"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) void onFile(file)
              e.target.value = ''
            }}
          />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {editing ? (
          <div className="space-y-2">
            <Textarea rows={8} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste the current job description" aria-label="Job description text" />
            <div className="flex gap-2">
              <Button size="sm" onClick={() => void savePasted()} disabled={text.trim().length < 120} loading={addSnapshot.isPending}>
                Save
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : null}
        {snapshot ? (
          <>
            {snapshot.changed_from_previous ? (
              <p className="rounded-md bg-warning/10 px-3 py-2 text-xs">This version changed the requirements compared with the previous one.</p>
            ) : null}
            <StructuredJdView structured={snapshot.structured} changes={snapshot.changed_from_previous ? snapshot.changes : undefined} />
            <details>
              <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-muted-foreground">Full text</summary>
              <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap rounded-md bg-muted/50 p-3 font-sans text-xs">{snapshot.raw_text}</pre>
            </details>
          </>
        ) : null}
      </CardContent>
    </Card>
  )
}

function TailorCard({ target }: { target: JobTargetDetail }) {
  const navigate = useNavigate()
  const resumes = useResumes()
  const tailor = useTailor(target.id)
  const [sourceId, setSourceId] = React.useState(target.source_resume?.id ?? NONE)
  const [comparing, setComparing] = React.useState(false)
  const tailored = target.tailored_resume
  const options = (resumes.data ?? []).filter((r) => !r.archived_at && r.kind !== 'TAILORED')

  const run = async (ai?: WorkflowTarget) => {
    try {
      const result = await tailor.mutateAsync({ source_resume_id: sourceId === NONE ? undefined : sourceId, ai })
      const running = result.ai_pass === 'running'
      toast.success(`Created “${result.resume.name}”`, {
        description: running
          ? `${result.explanations.length} safe changes applied; the AI rewrite continues in the background. The original is unchanged.`
          : `Estimate ${result.source_score ?? '—'} → ${result.analysis.overall_score ?? '—'} with ${result.explanations.length} safe changes. The original is unchanged.`,
        action: { label: running ? 'Follow progress' : 'See what changed', onClick: () => navigate(`/resume/targets/new?target=${target.id}&analysis=${result.analysis.id}`) },
      })
      setComparing(true)
    } catch (error) {
      toast.error('Could not tailor the resume', { description: errorMessage(error) })
    }
  }

  const exportAs = (format: 'pdf' | 'docx') => {
    if (!tailored) return
    void downloadResumeExport(tailored, format).catch((error) => toast.error('Export failed', { description: errorMessage(error) }))
  }

  return (
    <Card variant="soft">
      <CardHeader className="pb-3">
        <CardTitle>Tailored resume</CardTitle>
        <CardDescription>
          A separate resume generated from your chosen resume with only safe, fact-preserving changes. Your original is never overwritten.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {tailored ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border p-3">
            <div className="min-w-0">
              <p className="truncate font-medium">{tailored.name}</p>
              <p className="text-xs text-muted-foreground">
                Version {tailored.current_version}
                {target.source_resume ? ` · from ${target.source_resume.name}` : ''}
                {target.submitted_resume_version ? ` · v${target.submitted_resume_version} was sent` : ''}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" asChild>
                <Link to={`/resume/my/${tailored.id}/edit`}>
                  <PencilLine aria-hidden />
                  Open in editor
                </Link>
              </Button>
              <Button size="sm" variant="ghost" onClick={() => exportAs('pdf')}>
                <FileDown aria-hidden />
                PDF
              </Button>
              <Button size="sm" variant="ghost" onClick={() => exportAs('docx')}>
                <FileDown aria-hidden />
                DOCX
              </Button>
              <Button size="sm" variant={comparing ? 'secondary' : 'ghost'} onClick={() => setComparing((value) => !value)} aria-pressed={comparing}>
                <GitCompare aria-hidden />
                Compare
              </Button>
            </div>
          </div>
        ) : null}
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <div className="flex-1 space-y-1.5">
            <Label>Tailor from</Label>
            <Select value={sourceId} onValueChange={setSourceId}>
              <SelectTrigger aria-label="Resume to tailor from">
                <SelectValue placeholder="Your default resume" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>Your default resume</SelectItem>
                {options.map((r) => (
                  <SelectItem key={r.id} value={r.id}>
                    {r.name} · v{r.current_version}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <AiRunButton
            task="tailor_resume"
            context="Your resume and this job description"
            onRun={(ai) => run(ai)}
            disabled={!target.latest_snapshot || tailor.isPending}
            loading={tailor.isPending}
            wrapperClassName="sm:items-end"
          >
            <Sparkles aria-hidden />
            {tailored ? 'Tailor again' : 'Tailor resume'}
          </AiRunButton>
        </div>
        {!target.latest_snapshot ? <p className="text-xs text-muted-foreground">Add the job description first.</p> : null}
        {tailor.isPending ? <p className="text-sm text-muted-foreground" role="status">Analysing and applying safe changes…</p> : null}
        {tailored && comparing ? <CompareView targetId={target.id} /> : null}
      </CardContent>
    </Card>
  )
}

function DetailsCard({ target }: { target: JobTargetDetail }) {
  const update = useUpdateTarget(target.id)
  const [notes, setNotes] = React.useState(target.notes ?? '')
  const [deadline, setDeadline] = React.useState(dateInput(target.deadline))
  const [followUp, setFollowUp] = React.useState(dateInput(target.follow_up_at))
  React.useEffect(() => {
    setNotes(target.notes ?? '')
    setDeadline(dateInput(target.deadline))
    setFollowUp(dateInput(target.follow_up_at))
  }, [target.notes, target.deadline, target.follow_up_at])
  const dirty = notes !== (target.notes ?? '') || deadline !== dateInput(target.deadline) || followUp !== dateInput(target.follow_up_at)

  const save = async () => {
    try {
      await update.mutateAsync({ notes: notes || null, deadline: toIso(deadline), follow_up_at: toIso(followUp) })
      toast.success('Saved')
    } catch (error) {
      toast.error('Could not save', { description: errorMessage(error) })
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle>Details and notes</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
          <dt className="text-muted-foreground">Location</dt>
          <dd>{target.location ?? '—'}</dd>
          <dt className="text-muted-foreground">Work mode</dt>
          <dd>{target.work_mode ? humanizeEnum(target.work_mode) : '—'}</dd>
          <dt className="text-muted-foreground">Saved</dt>
          <dd>{formatDate(target.created_at)}</dd>
        </dl>
        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1">
            <Label htmlFor="detail-deadline">Deadline</Label>
            <Input id="detail-deadline" type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="detail-follow">Follow up on</Label>
            <Input id="detail-follow" type="date" value={followUp} onChange={(e) => setFollowUp(e.target.value)} />
          </div>
        </div>
        <div className="space-y-1">
          <Label htmlFor="detail-notes">Notes</Label>
          <Textarea id="detail-notes" rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>
        <Button size="sm" onClick={() => void save()} disabled={!dirty || update.isPending} loading={update.isPending}>
          Save details
        </Button>
      </CardContent>
    </Card>
  )
}

/** `/resume/targets/:id` — one company and role: JD, estimate, tailored resume, activity. */
/** The main path a target moves along; Rejected / Archived sit outside it. */
const STEPS: JobTargetStatus[] = ['SAVED', 'PREPARING', 'READY', 'APPLIED', 'INTERVIEW', 'OFFER']

/** Clickable status stepper (the Status select beside it covers every status). */
function StatusStepper({ status, onChange, disabled }: { status: JobTargetStatus; onChange: (status: JobTargetStatus) => void; disabled?: boolean }) {
  const current = STEPS.indexOf(status)
  const off = current < 0
  return (
    <div className="-mx-1 overflow-x-auto px-1 pb-1">
      <ol className="grid min-w-[34rem] grid-cols-6" aria-label="Status">
        {STEPS.map((step, index) => {
          const done = !off && index < current
          const here = index === current
          return (
            <li key={step} className="relative flex flex-col items-center gap-1.5">
              {index > 0 ? (
                <span
                  aria-hidden
                  className={cn('absolute right-1/2 top-3.5 h-0.5 w-full -translate-y-1/2', !off && index <= current ? 'bg-gradient-brand' : 'bg-border')}
                />
              ) : null}
              <button
                type="button"
                disabled={disabled || here}
                onClick={() => onChange(step)}
                aria-current={here ? 'step' : undefined}
                aria-label={`${TARGET_STATUS_LABELS[step]}${here ? ' (current)' : done ? ' (done)' : ''}`}
                className={cn(
                  'relative z-10 flex size-7 items-center justify-center rounded-full text-xs font-semibold tabular-nums transition-[box-shadow,background-color]',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
                  done && 'bg-gradient-brand text-gradient-foreground',
                  here && 'bg-gradient-brand text-gradient-foreground shadow-glow ring-4 ring-primary/20',
                  !done && !here && 'border border-border bg-card text-muted-foreground hover:border-primary/40 hover:text-foreground',
                  'disabled:cursor-default',
                )}
              >
                {done ? <Check className="size-3.5" aria-hidden /> : index + 1}
              </button>
              <span className={cn('h-4 whitespace-nowrap text-xs leading-4', here ? 'font-semibold text-foreground' : 'text-muted-foreground')}>
                {TARGET_STATUS_LABELS[step]}
              </span>
            </li>
          )
        })}
      </ol>
      {off ? (
        <p className="mt-2 text-xs text-muted-foreground">
          This target is <span className="font-medium text-foreground">{TARGET_STATUS_LABELS[status]}</span> — pick a step to bring it back.
        </p>
      ) : null}
    </div>
  )
}

export default function JobTargetDetailPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const query = useTarget(id)
  const update = useUpdateTarget(id)
  const remove = useDeleteTarget()
  const [confirm, setConfirm] = React.useState<'delete' | 'archive' | null>(null)
  const target = query.data
  useDocumentTitle(target ? `${target.role_title} · ${target.company_name}` : 'Job target')

  if (query.isLoading) {
    return (
      <PageContainer>
        <JobTargetDetailSkeleton />
      </PageContainer>
    )
  }
  if (query.error || !target) {
    return (
      <PageContainer>
        <PageHeader title="Job target" eyebrow={<Link to="/resume/targets">← Job-specific resumes</Link>} />
        <ErrorState error={query.error} title="This job target could not be loaded" onRetry={() => void query.refetch()} />
      </PageContainer>
    )
  }

  const setStatus = async (status: JobTargetStatus) => {
    try {
      const next = await update.mutateAsync({ status })
      toast.success(`Moved to ${TARGET_STATUS_LABELS[status]}`, {
        description: status === 'APPLIED' && next.submitted_resume_version ? `Recorded that resume version ${next.submitted_resume_version} was sent.` : undefined,
      })
    } catch (error) {
      toast.error('Could not change the status', { description: errorMessage(error) })
    }
  }

  const rename = async (field: 'role_title' | 'company_name', value: string) => {
    try {
      await update.mutateAsync({ [field]: value })
      toast.success(field === 'role_title' ? 'Role renamed' : 'Company renamed')
    } catch (error) {
      toast.error('Could not rename', { description: errorMessage(error) })
      throw error
    }
  }

  const analysis = target.last_analysis
  const optimizerLink = `/resume/ats?target=${target.id}${target.tailored_resume ? `&resume=${target.tailored_resume.id}` : target.source_resume ? `&resume=${target.source_resume.id}` : ''}`

  return (
    <PageContainer>
      {/* Header band: where this target stands, on the soft brand panel. */}
      <header className="border-gradient-soft relative min-w-0 space-y-5 overflow-hidden rounded-3xl p-5 sm:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-2">
            <Link
              to="/resume/targets"
              className="inline-flex h-5 items-center gap-1 rounded-sm text-sm text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <ArrowLeft className="size-3.5" aria-hidden />
              Job-specific resumes
            </Link>
            <h1 className="min-w-0 text-2xl font-heading sm:text-3xl">
              <InlineEdit value={target.role_title} label="Role" onSave={(v) => rename('role_title', v)} saving={update.isPending} className="w-full" />
            </h1>
            <p className="flex min-h-6 flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <InlineEdit
                value={target.company_name}
                label="Company"
                onSave={(v) => rename('company_name', v)}
                saving={update.isPending}
                textClassName="font-medium text-foreground"
              />
              <TargetStatusBadge status={target.status} />
              <TargetDueBadges target={target} />
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
              <Select value={target.status} onValueChange={(value) => void setStatus(value as JobTargetStatus)}>
                <SelectTrigger className="w-44" aria-label="Status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {JOB_TARGET_STATUSES.map((status) => (
                    <SelectItem key={status} value={status}>
                      {TARGET_STATUS_LABELS[status]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {target.job_url ? (
                <Button variant="outline" size="icon" asChild title="Open the posting">
                  <a href={target.job_url} target="_blank" rel="noreferrer noopener" aria-label="Open the posting">
                    <ExternalLink />
                  </a>
                </Button>
              ) : null}
              {target.job_id ? (
                <Button variant="outline" size="icon" asChild title="Open in Jobs">
                  <Link to={`/jobs?q=${encodeURIComponent(target.role_title)}`} aria-label="Find this job in Jobs">
                    <Briefcase />
                  </Link>
                </Button>
              ) : null}
              {target.status !== 'ARCHIVED' ? (
                <Button variant="ghost" size="icon" onClick={() => setConfirm('archive')} title="Archive" aria-label="Archive">
                  <Archive />
                </Button>
              ) : null}
              <Button variant="ghost" size="icon" onClick={() => setConfirm('delete')} title="Delete" aria-label="Delete">
                <Trash2 />
              </Button>
          </div>
        </div>
        <StatusStepper status={target.status} disabled={update.isPending} onChange={(next) => void setStatus(next)} />
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,20rem)]">
        <div className="min-w-0 space-y-6">
          <Card>
            <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2 pb-3">
              <div className="space-y-1">
                <CardTitle>ATS estimate</CardTitle>
                <CardDescription>
                  {analysis
                    ? `${analysis.resume_name} v${analysis.resume_version} · ${formatRelative(analysis.created_at)}. An estimate, not the employer's ATS result.`
                    : 'Not analysed yet.'}
                </CardDescription>
              </div>
              <Button size="sm" variant="outline" asChild>
                <Link to={analysis ? `/resume/ats?analysis=${analysis.id}&resume=${analysis.resume_id}` : optimizerLink}>
                  <ScanSearch aria-hidden />
                  {analysis ? 'Open in ATS Optimizer' : 'Analyse'}
                </Link>
              </Button>
            </CardHeader>
            <CardContent>
              {analysis ? (
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                  <ScoreRing score={analysis.overall_score} size={104} />
                  <div className="min-w-0 space-y-2">
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Missing requirements</p>
                    {target.missing_requirements.length ? (
                      <ul className="flex flex-wrap gap-1.5">
                        {target.missing_requirements.map((skill) => (
                          <li key={skill} className="rounded-full border border-destructive/20 bg-destructive-soft px-2.5 py-0.5 text-xs font-medium text-destructive-soft-foreground">
                            {skill}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-sm text-muted-foreground">Every required skill of the posting is on the resume.</p>
                    )}
                  </div>
                </div>
              ) : (
                <EmptyState
                  size="sm"
                  icon={ScanSearch}
                  title="No estimate yet"
                  description={target.latest_snapshot ? 'Analyse a resume against this job description.' : 'Add the job description first.'}
                />
              )}
            </CardContent>
          </Card>
          <TailorCard target={target} />
          <JdCard target={target} />
        </div>

        <div className="space-y-6">
          <DetailsCard target={target} />
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2">
                <History className="size-4" aria-hidden />
                Activity
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="relative space-y-4 pl-6">
                <span aria-hidden className="pointer-events-none absolute inset-y-1 left-[5px] w-0.5 rounded-full bg-gradient-to-b from-primary/50 via-border to-border/0" />
                {target.activity.map((item, index) => (
                  <li key={`${item.at}-${index}`} className="relative text-sm">
                    <span className="absolute -left-6 top-1 size-3 rounded-full bg-gradient-brand ring-4 ring-card" aria-hidden />
                    <p>{item.message}</p>
                    <p className="text-xs text-muted-foreground" title={formatDateTime(item.at)}>
                      {formatRelative(item.at)}
                    </p>
                  </li>
                ))}
              </ol>
              {target.application_id ? (
                <Badge variant="outline" className="mt-3">
                  Linked to a JobPilot application
                </Badge>
              ) : null}
            </CardContent>
          </Card>
        </div>
      </div>

      <ConfirmDialog
        open={confirm === 'delete'}
        onOpenChange={(open) => setConfirm(open ? 'delete' : null)}
        title="Delete this job target?"
        description="The target, its job descriptions and its link to the tailored resume are removed. The tailored resume itself stays in My Resumes."
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={async () => {
          try {
            await remove.mutateAsync(target.id)
            toast.success('Job target deleted')
            navigate('/resume/targets')
          } catch (error) {
            toast.error('Could not delete', { description: errorMessage(error) })
          }
        }}
      />
      <ConfirmDialog
        open={confirm === 'archive'}
        onOpenChange={(open) => setConfirm(open ? 'archive' : null)}
        title="Archive this job target?"
        description="It moves to the Archived column. You can change its status back at any time."
        confirmLabel="Archive"
        onConfirm={() => setStatus('ARCHIVED')}
      />
    </PageContainer>
  )
}
