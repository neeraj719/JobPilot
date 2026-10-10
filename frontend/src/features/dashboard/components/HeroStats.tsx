import { useNavigate } from 'react-router-dom'

import { StatCard } from '@/components/common/StatCard'
import { formatNumber, formatPercent, pluralize } from '@/lib/utils'
import type { DashboardStats, ReviewCounts } from '@/types/api'

/**
 * The KPI row.
 *
 * Every tile carries a second line that says *why* the number is what it is, so the row
 * answers "how many, and what happened" without a chart. No tile invents a delta the
 * API cannot support — the secondary line is a real, related count.
 *
 * No icons here on purpose: at seven tiles across, an icon chip eats the width the
 * label needs and the titles start truncating ("Respo…"). The label *is* the tile.
 */
export function HeroStats({
  stats,
  review,
  loading = false,
}: {
  stats: DashboardStats | undefined
  review: ReviewCounts | undefined
  loading?: boolean
}) {
  const navigate = useNavigate()
  const today = stats?.today
  const week = stats?.week
  const month = stats?.month
  const totals = stats?.totals

  const pending = (totals?.pending_review ?? 0) + (totals?.requires_input ?? 0) + (totals?.queued ?? 0)

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7">
      <StatCard
        title="Applied today"
        value={formatNumber(today?.applications ?? 0)}
        loading={loading}
        description={`${formatNumber(today?.responses ?? 0)} ${pluralize(today?.responses ?? 0, 'response')} today`}
        onClick={() => navigate('/applications')}
      />
      <StatCard
        title="This week"
        value={formatNumber(week?.applications ?? 0)}
        loading={loading}
        description={`${formatNumber(week?.responses ?? 0)} ${pluralize(week?.responses ?? 0, 'response')} this week`}
        onClick={() => navigate('/applications')}
      />
      <StatCard
        title="This month"
        value={formatNumber(month?.applications ?? 0)}
        loading={loading}
        description={`${formatNumber(month?.jobs_found ?? 0)} jobs found`}
        onClick={() => navigate('/applications')}
      />
      <StatCard
        title="Response rate"
        value={formatPercent(stats?.response_rate ?? 0, 1)}
        loading={loading}
        description={`${formatNumber(totals?.responses ?? 0)} of ${formatNumber(totals?.applications ?? 0)} replied`}
        onClick={() => navigate('/analytics')}
      />
      <StatCard
        title="Interviews"
        value={formatNumber(totals?.interviews ?? 0)}
        loading={loading}
        description={`${formatPercent(stats?.interview_rate ?? 0, 1)} of applications`}
        onClick={() => navigate('/interviews')}
      />
      <StatCard
        title="Offers"
        value={formatNumber(totals?.offers ?? 0)}
        loading={loading}
        description={`${formatPercent(stats?.offer_rate ?? 0, 1)} of applications`}
        onClick={() => navigate('/applications')}
      />
      <StatCard
        title="Pending"
        value={formatNumber(pending)}
        loading={loading}
        description={`${formatNumber(totals?.queued ?? 0)} queued · ${formatNumber(review?.requires_input ?? totals?.requires_input ?? 0)} need input`}
        onClick={() => navigate('/queue')}
      />
    </div>
  )
}
