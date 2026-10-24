import { AlertTriangle, Bookmark, FileWarning, RefreshCw, Sparkles, Wand2 } from 'lucide-react'
import * as React from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { ErrorState } from '@/components/common/ErrorState'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { toast } from '@/components/ui/toaster'
import { errorMessage } from '@/lib/api'
import { formatRelative } from '@/lib/utils'
import { useAnalysis, useAutoOptimize, useCreateTarget, useRetryPolish, useUndoApply } from '@/features/ats/api'
import { AnalysisResultsSkeleton } from '@/features/ats/components/AtsSkeletons'
import { CategoryBars } from '@/features/ats/components/CategoryBars'
import { KeywordChips } from '@/features/ats/components/KeywordChips'
import { MethodologyPopover } from '@/features/ats/components/MethodologyPopover'
import { ScoreRing } from '@/features/ats/components/ScoreRing'
import { SuggestionList } from '@/features/ats/components/SuggestionList'
import type { ApplyResult, AtsAnalysis } from '@/features/ats/types'
import { AiModelChip } from '@/features/ai-providers/components/AiModelChip'
import { AiRunButton } from '@/features/ai-providers/components/AiRunButton'
import type { WorkflowTarget } from '@/features/ai-providers/types'
import { useAiChoices } from '@/features/ai-providers/useAiChoice'

function PolishStatus({ analysis }: { analysis: AtsAnalysis }) {
  const retry = useRetryPolish(analysis.id)
  const choices = useAiChoices('polish_suggestions')
  const runPolish = (ai?: WorkflowTarget) =>
    retry.mutateAsync(ai).catch((e) => toast.error('Could not polish the suggestions', { description: errorMessage(e) }))
  const unpolished = analysis.suggestions.some(
    (s) => s.kind === 'REPLACE_BULLET' && s.status === 'PROPOSED' && !(s.checks as Record<string, unknown> | undefined)?.ai_attempted,
  )
  const hasModel = Boolean(choices.data?.candidates.some((c) => c.available && c.provider !== 'mock'))
  if (analysis.status === 'RUNNING' || analysis.status === 'PENDING') {
    return (
      <div className="space-y-1.5 rounded-md border border-border bg-muted/40 p-3" role="status" aria-live="polite">
        <p className="flex items-center gap-2 text-sm">
          <Sparkles className="size-4 shrink-0 text-primary" aria-hidden />
          The AI model is polishing the bullet suggestions. The results below are already final; rewrites appear as they pass JobPilot's fact checks.
        </p>
        <Progress value={analysis.progress} aria-label="Polish progress" />
      </div>
    )
  }
  if (analysis.error) {
    return (
      <Alert>
        <AlertTriangle aria-hidden />
        <AlertDescription className="flex flex-wrap items-center justify-between gap-2">
          <span>{analysis.error} The rule-based suggestions are shown.</span>
          <AiRunButton task="polish_suggestions" size="sm" variant="outline" onRun={runPolish} loading={retry.isPending} showModel={false}>
            <RefreshCw aria-hidden />
            Retry AI polish
          </AiRunButton>
        </AlertDescription>
      </Alert>
    )
  }
  if (analysis.is_current && unpolished && hasModel && (!analysis.ai_provider || analysis.ai_provider === 'mock')) {
    return (
      <div className="flex flex-wrap items-start justify-between gap-3 rounded-md border border-border bg-muted/40 p-3">
        <p className="flex items-center gap-2 text-sm">
          <Wand2 className="size-4 shrink-0 text-primary" aria-hidden />
          These suggestions come from JobPilot&apos;s rules. An AI model can reword the bullet rewrites (every result is fact-checked).
        </p>
        <AiRunButton task="polish_suggestions" size="sm" variant="outline" onRun={runPolish} loading={retry.isPending}>
          <Sparkles aria-hidden />
          Polish suggestions
        </AiRunButton>
      </div>
    )
  }
  return null
}

export interface AnalysisResultsProps {
  analysisId: string
  /** The analysis shown changed (re-run after apply / undo / auto-optimize). */
  onAnalysisChange: (id: string) => void
}

/** Score, categories, keywords, weak content and the suggestions of one analysis. */
export function AnalysisResults({ analysisId, onAnalysisChange }: AnalysisResultsProps) {
  const navigate = useNavigate()
  const query = useAnalysis(analysisId)
  const analysis = query.data
  const undo = useUndoApply()
  const autoOptimize = useAutoOptimize(analysisId)
  const createTarget = useCreateTarget()
  const [confirmAuto, setConfirmAuto] = React.useState(false)
  /** The model picked for the auto-optimize run (the picker runs before the confirmation). */
  const [autoAi, setAutoAi] = React.useState<WorkflowTarget | undefined>(undefined)

  if (query.isLoading) return <AnalysisResultsSkeleton />
  if (query.error || !analysis) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />

  const onApplied = (result: ApplyResult) => {
    const applied = result.applied.length
    if (applied === 0) {
      toast.warning('Nothing was applied', { description: result.skipped.map((s) => s.reason.replace(/_/g, ' ')).join(', ') || undefined })
      return
    }
    onAnalysisChange(result.analysis.id)
    toast.success(
      `Applied ${applied} ${applied === 1 ? 'change' : 'changes'} — estimate ${result.previous_score ?? '—'} → ${result.analysis.overall_score ?? '—'}`,
      {
        description: `Saved as version ${result.resume.current_version}. Version ${result.restorable_version} stays in the history.`,
        duration: 12000,
        action: {
          label: 'Undo',
          onClick: () => {
            void undo
              .mutateAsync(result.analysis.id)
              .then((undone) => {
                onAnalysisChange(undone.analysis.id)
                toast.success('Undone', { description: `Version ${undone.restored_version} restored as version ${undone.resume.current_version}.` })
              })
              .catch((error) => toast.error('Could not undo', { description: errorMessage(error) }))
          },
        },
      },
    )
  }

  const runAutoOptimize = async () => {
    try {
      const result = await autoOptimize.mutateAsync({ mode: 'new_resume', ai: autoAi })
      onAnalysisChange(result.analysis.id)
      toast.success(`Created “${result.resume.name}”`, {
        description: `${result.applied.length} safe changes · estimate ${result.previous_score ?? '—'} → ${result.analysis.overall_score ?? '—'}. Your original resume is unchanged.`,
        duration: 12000,
        action: { label: 'Open in editor', onClick: () => navigate(`/resume/my/${result.resume.id}/edit`) },
      })
    } catch (error) {
      toast.error('Could not create the tailored resume', { description: errorMessage(error) })
    }
  }

  const saveAsTarget = async () => {
    try {
      const target = await createTarget.mutateAsync({
        snapshot_id: analysis.snapshot_id ?? undefined,
        analysis_id: analysis.id,
        company_name: analysis.jd.company ?? undefined,
        role_title: analysis.jd.title ?? undefined,
      })
      toast.success('Saved as a job target', {
        action: { label: 'Open', onClick: () => navigate(`/resume/targets/${target.id}`) },
      })
    } catch (error) {
      toast.error('Could not save the job target', { description: errorMessage(error) })
    }
  }

  const proposedSafe = analysis.suggestions.filter((s) => s.status === 'PROPOSED' && s.safe).length

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="grid gap-6 p-6 md:grid-cols-[auto_1fr]">
          <ScoreRing score={analysis.overall_score} previous={analysis.previous_score} />
          <div className="min-w-0 space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0 space-y-1">
                <h2 className="text-lg font-semibold">
                  {analysis.jd.title ?? 'Job description'}
                  {analysis.jd.company ? <span className="text-muted-foreground"> · {analysis.jd.company}</span> : null}
                </h2>
                <p className="text-sm text-muted-foreground">
                  {analysis.resume_name} v{analysis.resume_version} · analysed {formatRelative(analysis.created_at)}
                </p>
                <AiModelChip provider={analysis.ai_provider} model={analysis.ai_model} prefix="Suggestions polished by" />
              </div>
              <MethodologyPopover weights={analysis.weights} />
            </div>
            <p className="text-xs text-muted-foreground">{analysis.disclaimer}</p>
            <PolishStatus analysis={analysis} />
            <div className="flex flex-wrap gap-2">
              <AiRunButton
                task="polish_suggestions"
                size="sm"
                showModel={false}
                onRun={(ai) => {
                  setAutoAi(ai)
                  setConfirmAuto(true)
                }}
                disabled={!analysis.is_current || autoOptimize.isPending}
                loading={autoOptimize.isPending}
              >
                <Sparkles aria-hidden />
                Auto-optimize → new resume
              </AiRunButton>
              {analysis.job_target_id ? (
                <Button size="sm" variant="outline" asChild>
                  <Link to={`/resume/targets/${analysis.job_target_id}`}>
                    <Bookmark aria-hidden />
                    Open job target
                  </Link>
                </Button>
              ) : (
                <Button size="sm" variant="outline" onClick={() => void saveAsTarget()} loading={createTarget.isPending}>
                  <Bookmark aria-hidden />
                  Save as job target
                </Button>
              )}
              <Button size="sm" variant="ghost" asChild>
                <Link to={`/resume/my/${analysis.resume_id}/edit`}>Edit resume</Link>
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle>Category scores</CardTitle>
            <CardDescription>Each is computed by fixed rules; open one to see why.</CardDescription>
          </CardHeader>
          <CardContent>
            <CategoryBars categories={analysis.category_scores} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle>Keywords</CardTitle>
            <CardDescription>What the posting asks for, found or not on your resume.</CardDescription>
          </CardHeader>
          <CardContent>
            <KeywordChips matched={analysis.matched_keywords} missing={analysis.missing_keywords} />
          </CardContent>
        </Card>
      </div>

      {analysis.weak_items.length || analysis.parse_risks.length ? (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2">
              <FileWarning className="size-4 text-warning" aria-hidden />
              Weak content and parsing risks
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            <ul className="space-y-2">
              {analysis.weak_items.slice(0, 10).map((item) => (
                <li key={`${item.path}:${item.text}`} className="text-sm">
                  <p className="line-clamp-2">“{item.text}”</p>
                  <p className="text-xs text-muted-foreground">{item.reason}</p>
                </li>
              ))}
              {analysis.weak_items.length === 0 ? <li className="text-sm text-muted-foreground">Every bullet states a result.</li> : null}
            </ul>
            <ul className="space-y-2">
              {analysis.parse_risks.map((risk) => (
                <li key={risk.code} className="flex items-start gap-2 text-sm">
                  <Badge variant={risk.severity === 'high' ? 'destructive' : 'muted'}>{risk.severity}</Badge>
                  <span>{risk.message}</span>
                </li>
              ))}
              {analysis.parse_risks.length === 0 ? <li className="text-sm text-muted-foreground">No parsing risks found.</li> : null}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle>Recommendations</CardTitle>
          <CardDescription>
            Apply, edit or ignore each one. Applying saves a new version and re-runs the analysis; nothing is added that
            your resume or profile does not already show unless you confirm it.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <SuggestionList analysis={analysis} readOnly={!analysis.is_current} onApplied={onApplied} />
        </CardContent>
      </Card>

      <ConfirmDialog
        open={confirmAuto}
        onOpenChange={setConfirmAuto}
        title="Create a tailored resume?"
        description={`A new resume is created from “${analysis.resume_name}” with the ${proposedSafe} safe changes applied and the posting's skills first. Suggestions that need your confirmation are not applied. Your original resume is not changed.`}
        confirmLabel="Create tailored resume"
        onConfirm={runAutoOptimize}
      />
    </div>
  )
}
