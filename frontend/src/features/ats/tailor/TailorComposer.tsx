import { Crosshair, Info, ShieldCheck, Sparkles } from 'lucide-react'
import * as React from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import { ErrorState } from '@/components/common/ErrorState'
import { SkeletonRegion } from '@/components/common/skeletons'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { toast } from '@/components/ui/toaster'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { errorMessage, isApiError } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import { useResumes } from '@/features/resume/api'
import { useUploadSheet } from '@/features/resume-upload/UploadResumeSheet'
import { useAnalyses, useAnalysis, useCompare, useQuickTailor, useTailorTarget, useTarget } from '@/features/ats/api'
import { JdInputPanel } from '@/features/ats/components/JdInputPanel'
import type { JdInput, JdParseResult, TailorResult } from '@/features/ats/types'
import { ResumePicker } from '@/features/ats/tailor/ResumePicker'
import { TailorProgress } from '@/features/ats/tailor/TailorProgress'
import { TailorResultView, aiOutcome } from '@/features/ats/tailor/TailorResultView'
import { TailorSteps } from '@/features/ats/tailor/TailorSteps'
import { AiRunButton } from '@/features/ai-providers/components/AiRunButton'
import type { WorkflowTarget } from '@/features/ai-providers/types'
import { useAiChoices } from '@/features/ai-providers/useAiChoice'

const DESCRIPTION =
  'Paste the job description, pick a resume, and get a copy optimized for that job. Scores are estimates, not any employer’s actual ATS result.'

function ComposerSkeleton() {
  return (
    <SkeletonRegion label="Loading your resumes" className="space-y-6">
      {[0, 1, 2].map((i) => (
        <div key={i} className="rounded-xl border border-border bg-card p-5 shadow-xs">
          <Skeleton className="mb-2 h-5 w-48" />
          <Skeleton className="mb-4 h-4 w-72 max-w-full" />
          <Skeleton className={i === 0 ? 'h-40 w-full' : i === 1 ? 'h-24 w-full' : 'h-9 w-48'} />
        </div>
      ))}
    </SkeletonRegion>
  )
}

/** The saved target's job description, reused for "Optimize another resume for this job". */
function SavedJdCard({ targetId, onClear }: { targetId: string; onClear: () => void }) {
  const target = useTarget(targetId)
  if (target.isLoading) {
    return (
      <SkeletonRegion label="Loading the job description" className="space-y-2">
        <Skeleton className="h-5 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
      </SkeletonRegion>
    )
  }
  if (target.error || !target.data) return <ErrorState error={target.error} size="sm" onRetry={() => void target.refetch()} />
  const required = target.data.latest_snapshot?.structured.required_skills ?? []
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface-2 p-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0 space-y-1">
        <p className="flex items-center gap-2 text-sm font-medium">
          <Crosshair className="size-4 shrink-0 text-primary" aria-hidden />
          <span className="truncate">
            {target.data.role_title} <span className="text-muted-foreground">at</span> {target.data.company_name}
          </span>
        </p>
        <p className="text-xs text-muted-foreground">
          The job description saved with this target is used again{required.length ? `: ${required.slice(0, 6).join(', ')}` : ''}.
        </p>
      </div>
      <Button variant="outline" size="sm" onClick={onClear}>
        Use a different job description
      </Button>
    </div>
  )
}

/** `/resume/targets/new` — job description, resume, optimize: one screen, then the result. */
export default function TailorComposerPage() {
  useDocumentTitle('Optimize a resume for a job')
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const resumes = useResumes()
  const analyses = useAnalyses({ limit: 100 })
  const choices = useAiChoices('tailor_resume')
  const upload = useUploadSheet()
  const quick = useQuickTailor()
  const tailorTarget = useTailorTarget()

  const targetId = params.get('target')
  const analysisId = params.get('analysis')
  const savedTargetId = targetId && !analysisId ? targetId : null

  const [jd, setJd] = React.useState<JdInput | null>(null)
  const [parsed, setParsed] = React.useState<JdParseResult | null>(null)
  const [role, setRole] = React.useState('')
  const [company, setCompany] = React.useState('')
  const touched = React.useRef({ role: false, company: false })
  const [picked, setPicked] = React.useState<string | null>(params.get('resume'))
  const [aiPass, setAiPass] = React.useState<TailorResult['ai_pass'] | null>(null)
  const [conflict, setConflict] = React.useState<{ id: string; message: string } | null>(null)
  const announce = React.useRef(false)
  const wasRunning = React.useRef(false)

  // Prefill role / company from the parse (until the user types their own).
  React.useEffect(() => {
    if (!parsed) return
    if (!touched.current.role) setRole(parsed.title ?? '')
    if (!touched.current.company) setCompany(parsed.company ?? '')
  }, [parsed])

  const list = React.useMemo(() => (resumes.data ?? []).filter((r) => !r.archived_at), [resumes.data])
  const readable = list.filter((r) => r.parse_status === 'PARSED')
  const resumeId =
    (picked && readable.some((r) => r.id === picked) ? picked : null) ?? readable.find((r) => r.is_default)?.id ?? readable[0]?.id ?? null
  const resume = list.find((r) => r.id === resumeId) ?? null

  const run = useAnalysis(analysisId)
  const runStatus = run.data?.status
  const running = runStatus === 'RUNNING' || runStatus === 'PENDING'
  const finished = Boolean(analysisId && run.data && !running)
  const target = useTarget(finished ? targetId : null)
  const compare = useCompare(finished ? targetId : null)

  // The AI pass finished while we watched: refresh what it changed.
  React.useEffect(() => {
    if (running) wasRunning.current = true
    if (finished && wasRunning.current) {
      wasRunning.current = false
      void queryClient.invalidateQueries({ queryKey: qk.ats.compare(targetId ?? 'none') })
      void queryClient.invalidateQueries({ queryKey: qk.ats.target(targetId ?? 'none') })
      void queryClient.invalidateQueries({ queryKey: qk.resumes.all })
      void queryClient.invalidateQueries({ queryKey: qk.resumeStudio.all })
    }
  }, [running, finished, targetId, queryClient])

  // One toast per run, once the final numbers are in.
  React.useEffect(() => {
    if (!announce.current || !finished || !compare.data || compare.isFetching || !target.data) return
    announce.current = false
    const outcome = aiOutcome(run.data)
    toast.success(`Optimized for ${target.data.role_title}`, {
      description: `Estimate ${compare.data.source.score ?? '—'} → ${compare.data.tailored.score ?? '—'}. ${
        outcome === 'ai' ? 'AI rewrite applied and fact-checked.' : outcome === 'error' ? 'The AI rewrite did not run; the rules-only copy is ready.' : 'Rules-only copy.'
      } Your original is unchanged.`,
    })
  }, [finished, compare.data, compare.isFetching, target.data, run.data])

  const pending = quick.isPending || tailorTarget.isPending
  const hasModel = Boolean(choices.data?.candidates.some((c) => c.available && c.provider !== 'mock'))
  const jdReady = Boolean(savedTargetId || jd?.text)
  const showResult = Boolean(targetId && analysisId)

  const optimize = async (ai?: WorkflowTarget) => {
    if (!resumeId || !jdReady) return
    setConflict(null)
    try {
      let result: TailorResult
      if (savedTargetId) {
        result = await tailorTarget.mutateAsync({ targetId: savedTargetId, source_resume_id: resumeId, ai })
      } else {
        result = await quick.mutateAsync({
          jd: { source: 'PASTED', text: jd?.text ?? '', url: jd?.url ?? undefined, structured: jd?.structured },
          source_resume_id: resumeId,
          company_name: company.trim() || undefined,
          role_title: role.trim() || undefined,
          ai,
        })
      }
      announce.current = true
      wasRunning.current = result.ai_pass === 'running'
      setAiPass(result.ai_pass)
      setParams({ target: result.target.id, analysis: result.analysis.id })
      window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
    } catch (error) {
      if (isApiError(error) && error.code === 'target_exists') {
        const id = (error.details as { id?: string } | undefined)?.id
        if (id) {
          setConflict({ id, message: errorMessage(error) })
          return
        }
      }
      toast.error('Could not optimize the resume', { description: errorMessage(error) })
    }
  }

  const another = () => {
    if (!targetId) return
    setAiPass(null)
    setParams({ target: targetId })
  }

  const steps = [
    { label: 'Job description', done: jdReady || showResult, active: !jdReady && !showResult },
    { label: 'Resume', done: (jdReady && Boolean(resumeId)) || showResult, active: jdReady && !resumeId && !showResult },
    { label: 'Optimize', done: showResult && finished, active: (jdReady && Boolean(resumeId)) || (showResult && !finished) },
  ]

  const header = (
    <PageHeader
      title="Optimize a resume for a job"
      description={DESCRIPTION}
      eyebrow={<Link to="/resume/targets">← Job-specific resumes</Link>}
    >
      <TailorSteps steps={steps} />
    </PageHeader>
  )

  // ------------------------------------------------------------------ result / progress
  if (showResult && targetId && analysisId) {
    let body: React.ReactNode
    if (run.isLoading) body = <TailorProgress phase="final" aiPass={aiPass} resumeName={resume?.name} />
    else if (run.error || !run.data) body = <ErrorState error={run.error} onRetry={() => void run.refetch()} />
    else if (running) body = <TailorProgress phase="ai" analysis={run.data} aiPass="running" resumeName={resume?.name} />
    else if (!target.data || !compare.data) {
      body =
        target.error || compare.error ? (
          <ErrorState error={target.error ?? compare.error} onRetry={() => void Promise.all([target.refetch(), compare.refetch()])} />
        ) : (
          <TailorProgress phase="final" analysis={run.data} aiPass={aiOutcome(run.data) === 'ai' ? 'running' : aiPass ?? 'rules_only'} resumeName={resume?.name} />
        )
    } else body = <TailorResultView targetId={targetId} analysisId={analysisId} onAnother={another} />
    return (
      <PageContainer className="max-w-5xl">
        {header}
        {body}
      </PageContainer>
    )
  }

  // ------------------------------------------------------------------ composer
  // While the request runs the composer stays mounted (hidden), so a failed run keeps the pasted JD.
  return (
    <PageContainer className="max-w-5xl">
      {header}
      {pending ? <TailorProgress phase="request" resumeName={resume?.name} /> : null}
      <div className={pending ? 'hidden' : undefined}>
      {resumes.isLoading ? (
        <ComposerSkeleton />
      ) : resumes.error ? (
        <ErrorState error={resumes.error} onRetry={() => void resumes.refetch()} />
      ) : (
        <div className="space-y-6">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle>1 · Job description</CardTitle>
              <CardDescription>Paste it (or upload it, or give the posting URL). It is read as data only: instructions inside it are ignored.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {savedTargetId ? (
                <SavedJdCard targetId={savedTargetId} onClear={() => setParams(resumeId ? { resume: resumeId } : {})} />
              ) : (
                <>
                  <JdInputPanel
                    tabs={['paste', 'upload', 'url']}
                    showMetaFields={false}
                    autoPreview
                    onChange={setJd}
                    onParsed={setParsed}
                  />
                  {jd?.text ? (
                    <div className="grid gap-3 border-t border-border pt-4 sm:grid-cols-2">
                      <div className="space-y-1.5">
                        <Label htmlFor="tailor-role">Role</Label>
                        <Input
                          id="tailor-role"
                          value={role}
                          onChange={(e) => {
                            touched.current.role = true
                            setRole(e.target.value)
                          }}
                          placeholder="Read from the job description"
                          maxLength={255}
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="tailor-company">Company</Label>
                        <Input
                          id="tailor-company"
                          value={company}
                          onChange={(e) => {
                            touched.current.company = true
                            setCompany(e.target.value)
                          }}
                          placeholder="Unknown company"
                          maxLength={255}
                        />
                      </div>
                      <p className="text-xs text-muted-foreground sm:col-span-2">
                        Optional. Used to name the saved target and the tailored copy; you can rename both later.
                      </p>
                    </div>
                  ) : null}
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle>2 · Resume</CardTitle>
              <CardDescription>The resume to start from. Its current version is copied; the resume itself is not changed.</CardDescription>
            </CardHeader>
            <CardContent>
              <ResumePicker
                resumes={list}
                value={resumeId}
                onChange={setPicked}
                analyses={analyses.data}
                jdTitle={role || parsed?.title}
                jdCompany={company || parsed?.company}
                onUpload={() => upload.openSheet()}
              />
            </CardContent>
          </Card>

          <Card variant="soft">
            <CardHeader className="pb-3">
              <CardTitle>3 · Optimize</CardTitle>
              <CardDescription>
                {hasModel
                  ? 'Safe rule-based changes first, then your AI model rewrites the summary and the most relevant bullets. Every rewrite is fact-checked before it is applied.'
                  : 'Safe rule-based changes: evidenced skills listed, the posting’s skills first, weak openers fixed.'}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {conflict ? (
                <Alert>
                  <Info aria-hidden />
                  <AlertDescription className="flex flex-wrap items-center justify-between gap-2">
                    <span>{conflict.message} Optimize this resume for the saved target instead.</span>
                    <Button size="sm" variant="outline" onClick={() => setParams({ target: conflict.id, ...(resumeId ? { resume: resumeId } : {}) })}>
                      Use the saved target
                    </Button>
                  </AlertDescription>
                </Alert>
              ) : null}
              <AiRunButton
                task="tailor_resume"
                size="lg"
                context="Your resume and the job description"
                onRun={(ai) => optimize(ai)}
                disabled={!jdReady || !resumeId || pending}
                loading={pending}
              >
                <Sparkles aria-hidden />
                Optimize for this job
              </AiRunButton>
              {!hasModel && !choices.isLoading ? (
                <p className="text-sm text-muted-foreground">
                  No AI model is configured, so the rewrite will be rules-only.{' '}
                  <Link to="/resume/ai-settings" className="font-medium text-primary underline-offset-4 hover:underline">
                    Settings → AI models
                  </Link>
                </p>
              ) : null}
              <p className="flex items-start gap-2 text-sm text-muted-foreground">
                <ShieldCheck className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
                We create a tailored copy. Your original is never changed. Nothing is invented: every change keeps your facts.
              </p>
              {!jdReady ? <p className="text-xs text-muted-foreground">Add the job description (at least 120 characters) to continue.</p> : null}
            </CardContent>
          </Card>
        </div>
      )}
      </div>
      {upload.element}
    </PageContainer>
  )
}
