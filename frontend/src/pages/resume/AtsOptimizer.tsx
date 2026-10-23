import { Check, FileText, ScanSearch } from 'lucide-react'
import * as React from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { LoadingState } from '@/components/common/LoadingState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { toast } from '@/components/ui/toaster'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { errorMessage } from '@/lib/api'
import { cn, formatRelative } from '@/lib/utils'
import { useResumes } from '@/features/resume/api'
import { useAnalyses, useCreateAnalysis } from '@/features/ats/api'
import { AnalysisResults } from '@/features/ats/components/AnalysisResults'
import { JdInputPanel } from '@/features/ats/components/JdInputPanel'
import { scoreTone, TONE_TEXT } from '@/features/ats/labels'
import type { JdInput } from '@/features/ats/types'

function Step({ n, label, done, active }: { n: number; label: string; done: boolean; active: boolean }) {
  return (
    <li className="flex items-center gap-2">
      <span
        className={cn(
          'flex size-7 items-center justify-center rounded-full border text-xs font-semibold',
          done ? 'border-success bg-success text-success-foreground' : active ? 'border-primary text-primary' : 'border-border text-muted-foreground',
        )}
        aria-hidden
      >
        {done ? <Check className="size-3.5" /> : n}
      </span>
      <span className={cn('text-sm', active ? 'font-medium' : 'text-muted-foreground')}>{label}</span>
    </li>
  )
}

/** `/resume/ats` — estimated ATS compatibility of a resume against one job description. */
export default function AtsOptimizerPage() {
  useDocumentTitle('ATS Optimizer')
  const [params, setParams] = useSearchParams()
  const resumes = useResumes()
  const createAnalysis = useCreateAnalysis()
  const [jd, setJd] = React.useState<JdInput | null>(null)

  const analysisId = params.get('analysis')
  const list = React.useMemo(() => (resumes.data ?? []).filter((r) => !r.archived_at && r.parse_status === 'PARSED'), [resumes.data])
  const resumeId = params.get('resume') ?? list.find((r) => r.is_default)?.id ?? list[0]?.id ?? null
  const resume = list.find((r) => r.id === resumeId) ?? null
  const recent = useAnalyses({ resume_id: resumeId ?? undefined, limit: 5 })

  const setParam = (key: string, value: string | null) =>
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous)
        if (value) next.set(key, value)
        else next.delete(key)
        return next
      },
      { replace: key === 'analysis' },
    )

  const analyse = async () => {
    if (!resume || !jd) return
    try {
      const analysis = await createAnalysis.mutateAsync({ resume_id: resume.id, jd })
      setParam('analysis', analysis.id)
      window.requestAnimationFrame(() => document.getElementById('ats-results')?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
    } catch (error) {
      toast.error('Could not analyse', { description: errorMessage(error) })
    }
  }

  if (resumes.isLoading) {
    return (
      <PageContainer>
        <PageHeader title="ATS Optimizer" />
        <LoadingState rows={3} />
      </PageContainer>
    )
  }
  if (resumes.error) {
    return (
      <PageContainer>
        <PageHeader title="ATS Optimizer" />
        <ErrorState error={resumes.error} onRetry={() => void resumes.refetch()} />
      </PageContainer>
    )
  }

  return (
    <PageContainer>
      <PageHeader
        title="ATS Optimizer"
        description="Check how a resume reads against one job description, then apply the safe improvements. Scores are estimates, not any employer's actual ATS result."
        actions={
          <Button variant="outline" asChild>
            <Link to="/resume/targets">Job-specific resumes</Link>
          </Button>
        }
      >
        <ol className="flex flex-wrap items-center gap-x-6 gap-y-2" aria-label="Steps">
          <Step n={1} label="Resume" done={Boolean(resume)} active={!resume} />
          <Step n={2} label="Job description" done={Boolean(jd) || Boolean(analysisId)} active={Boolean(resume) && !jd && !analysisId} />
          <Step n={3} label="Results" done={false} active={Boolean(analysisId)} />
        </ol>
      </PageHeader>

      {list.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No resume to analyse yet"
          description="Upload a resume or create one in the editor first."
          action={
            <Button asChild>
              <Link to="/resume/new">Create or import a resume</Link>
            </Button>
          }
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
          <Card className="h-fit">
            <CardHeader className="pb-3">
              <CardTitle>1 · Resume</CardTitle>
              <CardDescription>The current version is analysed.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Select value={resumeId ?? ''} onValueChange={(value) => { setParam('resume', value); setParam('analysis', null) }}>
                <SelectTrigger aria-label="Resume">
                  <SelectValue placeholder="Choose a resume" />
                </SelectTrigger>
                <SelectContent>
                  {list.map((item) => (
                    <SelectItem key={item.id} value={item.id}>
                      {item.name} · v{item.current_version}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {resume ? (
                <div className="flex flex-wrap gap-2 text-xs">
                  <Badge variant="outline">{resume.kind.toLowerCase()}</Badge>
                  <Badge variant="muted">version {resume.current_version}</Badge>
                  {resume.target_role ? <Badge variant="muted">{resume.target_role}</Badge> : null}
                </div>
              ) : null}
              {recent.data?.length ? (
                <div className="space-y-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Recent analyses</p>
                  <ul className="space-y-1">
                    {recent.data.map((item) => (
                      <li key={item.id}>
                        <button
                          type="button"
                          onClick={() => setParam('analysis', item.id)}
                          className={cn(
                            'flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent',
                            item.id === analysisId && 'bg-accent',
                          )}
                        >
                          <span className="min-w-0 truncate">
                            {item.jd_title ?? 'Job description'}
                            {item.jd_company ? <span className="text-muted-foreground"> · {item.jd_company}</span> : null}
                            <span className="block text-xs text-muted-foreground">v{item.resume_version} · {formatRelative(item.created_at)}</span>
                          </span>
                          <span className={cn('font-semibold tabular-nums', TONE_TEXT[scoreTone(item.overall_score)])}>{item.overall_score ?? '—'}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle>2 · Job description</CardTitle>
              <CardDescription>Paste it, upload it, give the posting URL, or reuse a saved target or a discovered job.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <JdInputPanel initialTarget={params.get('target')} onChange={setJd} />
              <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
                <Button onClick={() => void analyse()} disabled={!resume || !jd || createAnalysis.isPending} loading={createAnalysis.isPending}>
                  <ScanSearch aria-hidden />
                  Analyse
                </Button>
                <span className="text-xs text-muted-foreground">
                  {!jd ? 'Add a job description to continue.' : 'The rule-based estimate appears in about a second.'}
                </span>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {analysisId ? (
        <section id="ats-results" className="scroll-mt-20 space-y-3" aria-label="Results">
          <h2 className="text-base font-semibold">3 · Results</h2>
          <AnalysisResults analysisId={analysisId} onAnalysisChange={(id) => setParam('analysis', id)} />
        </section>
      ) : null}
    </PageContainer>
  )
}
