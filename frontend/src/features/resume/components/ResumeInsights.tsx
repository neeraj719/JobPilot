import { Compass } from 'lucide-react'
import * as React from 'react'
import { Link } from 'react-router-dom'

import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { LoadingState } from '@/components/common/LoadingState'
import { Button } from '@/components/ui/button'
import { toast } from '@/components/ui/toaster'
import { errorMessage } from '@/lib/api'
import {
  useApplyPlan,
  useApplySuggestions,
  useRefreshRecommendations,
  useResumeRecommendations,
  useSaveParsedData,
} from '@/features/resume/api'
import {
  ApplySuggestionsButton,
  ApplySuggestionsDialog,
  safeChanges,
} from '@/features/resume/components/ApplySuggestionsDialog'
import { RecommendationList } from '@/features/resume/components/RecommendationList'
import { ResumeHealthCard } from '@/features/resume/components/ResumeHealthCard'
import { ResumeScoreHistoryChart } from '@/features/resume/components/ResumeScoreHistoryChart'
import type { ParsedResume, ResumeRead } from '@/types/api'

/** Resume health, recommendations and the before/after chart for one resume. */
export function ResumeInsights({ resume }: { resume: ResumeRead }) {
  const query = useResumeRecommendations(resume.parse_status === 'PARSED' ? resume.id : null)
  const refresh = useRefreshRecommendations()
  const plan = useApplyPlan(resume.parse_status === 'PARSED' && query.data ? resume.id : null)
  const [applyOpen, setApplyOpen] = React.useState(false)
  const applyMutation = useApplySuggestions(resume.id)
  const saveParsed = useSaveParsedData()

  if (resume.parse_status !== 'PARSED') return null

  if (query.isLoading) return <LoadingState variant="list" rows={3} />
  if (query.error || !query.data) {
    return (
      <ErrorState
        error={query.error}
        title="Could not analyse this resume"
        onRetry={() => void query.refetch()}
      />
    )
  }

  const data = query.data
  const onRefresh = async () => {
    try {
      await refresh.mutateAsync(resume.id)
      toast.success('Analysis refreshed')
    } catch (error) {
      toast.error('Could not refresh the analysis', { description: errorMessage(error) })
    }
  }

  const currentPlan = plan.data && plan.data.resume_version === resume.current_version ? plan.data : undefined
  const safe = safeChanges(currentPlan)
  const reviewCount = currentPlan?.changes.length ?? 0

  // One click: apply every safe change and save a new version. The previous data is kept so
  // Undo can save it back (as another version, so the history is never rewritten).
  const onApply = async () => {
    if (!currentPlan || safe.length === 0) return
    const previousData = resume.parsed_data as ParsedResume
    const previousVersion = resume.current_version
    try {
      const result = await applyMutation.mutateAsync({
        resume_version: currentPlan.resume_version,
        changes: safe.map((change) => ({ id: change.id })),
      })
      const applied = result.applied.length
      if (applied === 0) {
        toast.warning('Nothing was applied', { description: 'The resume already had these changes.' })
        return
      }
      toast.success(`Applied ${applied} suggestion${applied === 1 ? '' : 's'}`, {
        description: `Saved as version ${result.resume.current_version}. Version ${previousVersion} is kept in the history.`,
        duration: 10000,
        action: {
          label: 'Undo',
          onClick: () => {
            void saveParsed
              .mutateAsync({ id: resume.id, data: previousData })
              .then((restored) =>
                toast.success('Undone', {
                  description: `Restored the previous content as version ${restored.current_version}.`,
                }),
              )
              .catch((error) => toast.error('Could not undo', { description: errorMessage(error) }))
          },
        },
      })
    } catch (error) {
      toast.error('Could not apply the suggestions', { description: errorMessage(error) })
      void plan.refetch()
    }
  }

  const applyButton = (
    <ApplySuggestionsButton
      safeCount={safe.length}
      reviewCount={reviewCount}
      applying={applyMutation.isPending || saveParsed.isPending}
      onApply={() => void onApply()}
      onReview={() => setApplyOpen(true)}
    />
  )

  return (
    <div className="space-y-6">
      <ResumeHealthCard
        data={data}
        refreshing={refresh.isPending}
        onRefresh={() => void onRefresh()}
        action={applyButton}
      />
      {data.target_summary.jobs_analysed === 0 ? (
        <EmptyState
          size="sm"
          icon={Compass}
          title="No target jobs yet"
          description="Advice about missing skills, keywords and match scores needs jobs to compare against. Run discovery or set your desired titles; the resume checks below already apply."
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Button size="sm" asChild>
                <Link to="/jobs">Discover jobs</Link>
              </Button>
              <Button size="sm" variant="outline" asChild>
                <Link to="/profile?tab=preferences">Set preferences</Link>
              </Button>
            </div>
          }
        />
      ) : null}
      <RecommendationList resumeId={resume.id} items={data.recommendations} action={applyButton} />
      <ResumeScoreHistoryChart resumeId={resume.id} />
      <ApplySuggestionsDialog resumeId={resume.id} open={applyOpen} onOpenChange={setApplyOpen} />
    </div>
  )
}
