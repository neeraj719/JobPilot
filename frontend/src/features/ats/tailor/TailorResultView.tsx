import { AlertTriangle, ArrowRight, Bot, Crosshair, FileDown, GitCompare, Info, ListChecks, PencilRuler, RefreshCw, Repeat2, Wand2 } from 'lucide-react'
import * as React from 'react'
import { Link } from 'react-router-dom'

import { ErrorState } from '@/components/common/ErrorState'
import { SkeletonRegion } from '@/components/common/skeletons'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton, SkeletonText } from '@/components/ui/skeleton'
import { toast } from '@/components/ui/toaster'
import { errorMessage } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useUpdateResume } from '@/features/resume/api'
import { downloadResumeExport, useAnalysis, useCompare, useRetryPolish, useTarget, useUpdateTarget } from '@/features/ats/api'
import { CompareView } from '@/features/ats/components/CompareView'
import { ScoreRing } from '@/features/ats/components/ScoreRing'
import { SuggestionList } from '@/features/ats/components/SuggestionList'
import { WordDiff } from '@/features/ats/components/WordDiff'
import { formatDelta } from '@/features/ats/labels'
import type { ApplyResult, AtsAnalysis, TailorChange } from '@/features/ats/types'
import { InlineEdit } from '@/features/ats/tailor/InlineEdit'
import { AiModelChip } from '@/features/ai-providers/components/AiModelChip'
import { AiRunButton } from '@/features/ai-providers/components/AiRunButton'
import type { WorkflowTarget } from '@/features/ai-providers/types'
import { useQueryClient } from '@tanstack/react-query'
import { qk } from '@/lib/queryClient'

const GROUPS: { key: TailorChange['group']; title: string }[] = [
  { key: 'skills', title: 'Skills added' },
  { key: 'summary', title: 'Summary rewritten' },
  { key: 'bullets', title: 'Bullets rewritten' },
  { key: 'sections', title: 'Sections reordered' },
]

/** How the AI pass of this run ended, from its analysis. */
export function aiOutcome(run: AtsAnalysis | undefined): 'ai' | 'error' | 'rules' {
  if (!run) return 'rules'
  if (run.error) return 'error'
  return run.suggestions.some((s) => (s.checks as Record<string, unknown>)?.tailor_pass) ? 'ai' : 'rules'
}

function SourceBadge({ source }: { source: TailorChange['source'] }) {
  return source === 'AI' ? (
    <Badge variant="secondary" className="gap-1" title="Rewritten by the AI model, checked by JobPilot's rules">
      <Bot className="size-3" aria-hidden />
      AI, fact-checked
    </Badge>
  ) : (
    <Badge variant="outline" className="gap-1" title="Made by JobPilot's rules from your own facts">
      <ListChecks className="size-3" aria-hidden />
      Rules
    </Badge>
  )
}

function ChangeItem({ change }: { change: TailorChange }) {
  return (
    <li className={cn('space-y-2 rounded-xl p-3', change.source === 'AI' ? 'border-gradient-soft' : 'border border-border bg-card')}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{change.title}</span>
        <SourceBadge source={change.source} />
        {change.applied_version ? <Badge variant="muted">v{change.applied_version}</Badge> : null}
      </div>
      {change.group === 'skills' ? (
        <p className="text-sm">
          <ins className="rounded bg-success/15 px-1.5 font-medium no-underline">+ {change.after}</ins>
        </p>
      ) : change.group === 'sections' ? (
        <div className="space-y-1 text-xs">
          <p className="text-muted-foreground">
            <span className="font-semibold uppercase tracking-wide">Before </span>
            {change.before}
          </p>
          <p>
            <span className="font-semibold uppercase tracking-wide text-success">After </span>
            {change.after}
          </p>
        </div>
      ) : (
        <WordDiff before={change.before} after={change.after} />
      )}
      {change.rationale ? <p className="text-xs text-muted-foreground">{change.rationale}</p> : null}
    </li>
  )
}

/** Shaped like the result: header with two rings, the change list. */
export function TailorResultSkeleton() {
  return (
    <SkeletonRegion label="Loading the tailored resume" className="space-y-6">
      <div className="rounded-xl border border-border bg-card p-5 shadow-xs sm:p-6">
        <div className="flex flex-col gap-6 md:flex-row md:items-center">
          <div className="flex items-center justify-center gap-3 sm:gap-5">
            <Skeleton className="size-24 rounded-full" />
            <Skeleton className="size-5 rounded" />
            <Skeleton className="size-24 rounded-full" />
          </div>
          <div className="min-w-0 flex-1 space-y-3">
            <Skeleton className="h-6 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
            <div className="flex flex-wrap gap-2">
              <Skeleton className="h-9 w-36" />
              <Skeleton className="h-9 w-24" />
              <Skeleton className="h-9 w-24" />
            </div>
          </div>
        </div>
      </div>
      <div className="rounded-xl border border-border bg-card p-5 shadow-xs">
        <Skeleton className="mb-4 h-5 w-40" />
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="rounded-xl border border-border p-3">
              <Skeleton className="mb-2 h-4 w-1/3" />
              <SkeletonText lines={2} />
            </div>
          ))}
        </div>
      </div>
    </SkeletonRegion>
  )
}

export interface TailorResultViewProps {
  targetId: string
  /** The tailored copy's first analysis: the one the AI pass ran on. */
  analysisId: string
  /** "Optimize another resume for this job": back to the resume step with this target's JD. */
  onAnother: () => void
}

/** Before -> after estimate, what changed (grouped), what needs the user's confirmation, actions. */
export function TailorResultView({ targetId, analysisId, onAnother }: TailorResultViewProps) {
  const queryClient = useQueryClient()
  const target = useTarget(targetId)
  const compare = useCompare(targetId)
  const run = useAnalysis(analysisId)
  const retry = useRetryPolish(analysisId, 'tailor_resume')
  const updateResume = useUpdateResume()
  const updateTarget = useUpdateTarget(targetId)
  const [finalId, setFinalId] = React.useState<string | null>(null)
  const [comparing, setComparing] = React.useState(false)
  const finalAnalysisId = finalId ?? target.data?.last_analysis_id ?? null
  const final = useAnalysis(finalAnalysisId)

  if (target.isLoading || compare.isLoading || run.isLoading) return <TailorResultSkeleton />
  if (target.error || compare.error || !target.data || !compare.data) {
    return <ErrorState error={target.error ?? compare.error} onRetry={() => void Promise.all([target.refetch(), compare.refetch()])} />
  }

  const detail = target.data
  const result = compare.data
  const tailored = detail.tailored_resume
  const before = result.source.score
  const after = result.tailored.score
  const delta = before !== null && after !== null ? after - before : null
  const outcome = aiOutcome(run.data)
  const grouped = GROUPS.map((group) => ({ ...group, items: result.changes.filter((c) => c.group === group.key) })).filter((g) => g.items.length)

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: qk.ats.compare(targetId) })
    void queryClient.invalidateQueries({ queryKey: qk.ats.target(targetId) })
  }

  const onApplied = (applied: ApplyResult) => {
    if (applied.applied.length === 0) {
      toast.warning('Nothing was applied', { description: applied.skipped.map((s) => s.reason.replace(/_/g, ' ')).join(', ') || undefined })
      return
    }
    setFinalId(applied.analysis.id)
    refresh()
    toast.success(`Applied ${applied.applied.length} ${applied.applied.length === 1 ? 'change' : 'changes'}`, {
      description: `Estimate ${applied.previous_score ?? '—'} → ${applied.analysis.overall_score ?? '—'}. Saved as version ${applied.resume.current_version} of the tailored copy.`,
    })
  }

  const exportAs = (format: 'pdf' | 'docx') => {
    if (!tailored) return
    void downloadResumeExport(tailored, format).catch((error) => toast.error('Export failed', { description: errorMessage(error) }))
  }

  const renameResume = async (name: string) => {
    if (!tailored) return
    try {
      await updateResume.mutateAsync({ id: tailored.id, name })
      refresh()
      toast.success('Renamed')
    } catch (error) {
      toast.error('Could not rename', { description: errorMessage(error) })
      throw error
    }
  }

  const renameTarget = async (field: 'company_name' | 'role_title', value: string) => {
    try {
      await updateTarget.mutateAsync({ [field]: value })
      toast.success(field === 'company_name' ? 'Company saved' : 'Role saved')
    } catch (error) {
      toast.error('Could not save', { description: errorMessage(error) })
      throw error
    }
  }

  return (
    <div className="space-y-6">
      <Card variant="gradient">
        <CardContent className="grid gap-6 p-5 sm:p-6 md:grid-cols-[auto_minmax(0,1fr)] md:items-center">
          <div className="flex items-start justify-center gap-2 sm:gap-4" aria-label="Estimated ATS compatibility, before and after">
            <div className="flex flex-col items-center gap-1">
              <span className="text-2xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">Original</span>
              <ScoreRing score={before} size={96} />
            </div>
            <div className="flex flex-col items-center gap-1 pt-12">
              <ArrowRight className="size-5 text-muted-foreground" aria-hidden />
              {delta !== null ? (
                <span
                  className={cn(
                    'rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums',
                    delta > 0 ? 'bg-success-soft text-success-soft-foreground' : delta < 0 ? 'bg-destructive-soft text-destructive-soft-foreground' : 'bg-muted text-muted-foreground',
                  )}
                  aria-label={`Change ${formatDelta(delta)}`}
                >
                  {formatDelta(delta)}
                </span>
              ) : null}
            </div>
            <div className="flex flex-col items-center gap-1">
              <span className="text-2xs font-semibold uppercase tracking-[0.08em] text-primary">Tailored</span>
              <ScoreRing score={after} size={96} />
            </div>
          </div>

          <div className="min-w-0 space-y-3">
            <div className="min-w-0 space-y-1">
              {tailored ? (
                <InlineEdit
                  value={tailored.name}
                  label="Tailored resume name"
                  onSave={renameResume}
                  saving={updateResume.isPending}
                  textClassName="font-display text-lg font-semibold"
                  className="w-full"
                />
              ) : null}
              <p className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1 text-sm text-muted-foreground">
                <span>For</span>
                <InlineEdit value={detail.role_title} label="Role" onSave={(v) => renameTarget('role_title', v)} saving={updateTarget.isPending} textClassName="font-medium text-foreground" />
                <span>at</span>
                <InlineEdit value={detail.company_name} label="Company" onSave={(v) => renameTarget('company_name', v)} saving={updateTarget.isPending} textClassName="font-medium text-foreground" />
              </p>
              <p className="text-xs text-muted-foreground">
                Version {result.tailored.version} · from {result.source.name} (unchanged). Scores are estimates, not any employer&apos;s ATS result.
              </p>
            </div>

            {outcome === 'ai' ? (
              <p className="flex flex-wrap items-center gap-2 text-sm">
                <AiModelChip provider={run.data?.ai_provider} model={run.data?.ai_model} prefix="AI rewrite by" />
                {result.ai_rejected ? (
                  <span className="text-xs text-muted-foreground">
                    {result.ai_rejected} AI {result.ai_rejected === 1 ? 'rewrite was' : 'rewrites were'} refused by the fact checks and not applied.
                  </span>
                ) : null}
              </p>
            ) : outcome === 'error' ? (
              <Alert>
                <AlertTriangle aria-hidden />
                <AlertDescription className="flex flex-wrap items-center justify-between gap-2">
                  <span>
                    The AI rewrite did not run: {(run.data?.error ?? '').replace(/^The AI rewrite did not run:\s*/, '')} The rules-only copy below is kept.
                  </span>
                  <AiRunButton
                    task="tailor_resume"
                    size="sm"
                    variant="outline"
                    showModel={false}
                    loading={retry.isPending}
                    onRun={(ai?: WorkflowTarget) => retry.mutateAsync(ai).catch((e) => toast.error('Could not retry', { description: errorMessage(e) }))}
                  >
                    <RefreshCw aria-hidden />
                    Retry
                  </AiRunButton>
                </AlertDescription>
              </Alert>
            ) : (
              <p className="flex items-start gap-2 rounded-lg bg-surface-2 px-3 py-2 text-sm">
                <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                <span>
                  Rules-only result: no AI model is configured, so only rule-safe changes were made.{' '}
                  <Link to="/resume/ai-settings" className="font-medium text-primary underline-offset-4 hover:underline">
                    Set up an AI model
                  </Link>{' '}
                  to have the summary and bullets rewritten too.
                </span>
              </p>
            )}

            <div className="flex flex-wrap gap-2">
              {tailored ? (
                <Button asChild>
                  <Link to={`/resume/my/${tailored.id}/edit`}>
                    <PencilRuler aria-hidden />
                    Open in editor
                  </Link>
                </Button>
              ) : null}
              <Button variant="outline" onClick={() => exportAs('pdf')} disabled={!tailored}>
                <FileDown aria-hidden />
                PDF
              </Button>
              <Button variant="outline" onClick={() => exportAs('docx')} disabled={!tailored}>
                <FileDown aria-hidden />
                DOCX
              </Button>
              <Button variant={comparing ? 'secondary' : 'outline'} onClick={() => setComparing((v) => !v)} aria-pressed={comparing} aria-controls="tailor-compare">
                <GitCompare aria-hidden />
                Compare with original
              </Button>
              <Button variant="ghost" asChild>
                <Link to={`/resume/targets/${detail.id}`}>
                  <Crosshair aria-hidden />
                  View target
                </Link>
              </Button>
              <Button variant="ghost" onClick={onAnother}>
                <Repeat2 aria-hidden />
                Optimize another resume for this job
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {comparing ? (
        <Card id="tailor-compare">
          <CardHeader className="pb-3">
            <CardTitle>Original vs tailored</CardTitle>
            <CardDescription>Every difference, with the reason for each change.</CardDescription>
          </CardHeader>
          <CardContent>
            <CompareView targetId={detail.id} />
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2">
            <Wand2 className="size-4 text-primary" aria-hidden />
            What changed
          </CardTitle>
          <CardDescription>
            {result.changes.length
              ? `${result.changes.length} ${result.changes.length === 1 ? 'change' : 'changes'}, each kept to your own facts. Undo any of them from the version history.`
              : 'Nothing could be changed safely. The items below need your input.'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {grouped.map((group) => (
            <section key={group.key} className="space-y-2" aria-label={group.title}>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {group.title} ({group.items.length})
              </h3>
              <ul className="space-y-2">
                {group.items.map((change) => (
                  <ChangeItem key={change.suggestion_ids.join(':')} change={change} />
                ))}
              </ul>
            </section>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle>Needs your confirmation</CardTitle>
          <CardDescription>
            JobPilot will not add these on its own: skills nothing on your resume shows, results only you know. Apply one only if it
            is true; it saves a new version of the tailored copy.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {final.isLoading || !final.data ? (
            <SkeletonRegion label="Loading the remaining suggestions" className="space-y-2">
              {[0, 1].map((i) => (
                <div key={i} className="rounded-xl border border-border p-4">
                  <Skeleton className="mb-2 h-4 w-1/3" />
                  <SkeletonText lines={2} />
                </div>
              ))}
            </SkeletonRegion>
          ) : (
            <SuggestionList analysis={final.data} readOnly={!final.data.is_current} onApplied={onApplied} />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
