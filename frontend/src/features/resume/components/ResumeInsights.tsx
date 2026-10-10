import { Compass } from 'lucide-react'
import { Link } from 'react-router-dom'

import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { LoadingState } from '@/components/common/LoadingState'
import { Button } from '@/components/ui/button'
import { toast } from '@/components/ui/toaster'
import { errorMessage } from '@/lib/api'
import { useRefreshRecommendations, useResumeRecommendations } from '@/features/resume/api'
import { RecommendationList } from '@/features/resume/components/RecommendationList'
import { ResumeHealthCard } from '@/features/resume/components/ResumeHealthCard'
import { ResumeScoreHistoryChart } from '@/features/resume/components/ResumeScoreHistoryChart'
import type { ResumeRead } from '@/types/api'

/** Resume health, recommendations and the before/after chart for one resume. */
export function ResumeInsights({ resume }: { resume: ResumeRead }) {
  const query = useResumeRecommendations(resume.parse_status === 'PARSED' ? resume.id : null)
  const refresh = useRefreshRecommendations()

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

  return (
    <div className="space-y-6">
      <ResumeHealthCard data={data} refreshing={refresh.isPending} onRefresh={() => void onRefresh()} />
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
      <RecommendationList resumeId={resume.id} items={data.recommendations} />
      <ResumeScoreHistoryChart resumeId={resume.id} />
    </div>
  )
}
