import { Crosshair, FileCheck2, LayoutGrid, List, Plus, Search, Sparkles } from 'lucide-react'
import * as React from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { toast } from '@/components/ui/toaster'
import { useDebounce } from '@/hooks/useDebounce'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { cn, formatDate, formatRelative } from '@/lib/utils'
import { useTargets } from '@/features/ats/api'
import { TargetDueBadges, TargetStatusBadge } from '@/features/ats/components/TargetBadges'
import { TargetBoardSkeleton, TargetTableSkeleton } from '@/features/ats/components/AtsSkeletons'
import { TargetFormDialog } from '@/features/ats/components/TargetFormDialog'
import { scoreTone, TARGET_STATUS_LABELS, TONE_TEXT } from '@/features/ats/labels'
import { JOB_TARGET_STATUSES, type JobTarget, type JobTargetStatus } from '@/features/ats/types'

const VIEW_KEY = 'jobpilot.ats.targetsView'

function Score({ target }: { target: JobTarget }) {
  if (target.last_score === null) return <span className="whitespace-nowrap text-xs text-muted-foreground">Not analysed</span>
  return (
    <span className={cn('whitespace-nowrap text-sm font-semibold tabular-nums', TONE_TEXT[scoreTone(target.last_score)])} title="Estimated ATS compatibility">
      {target.last_score}
      <span className="text-[10px] font-normal text-muted-foreground"> est.</span>
    </span>
  )
}

/** Memoised list row: react-query keeps unchanged targets referentially equal across refetches. */
const TargetCard = React.memo(function TargetCard({ target }: { target: JobTarget }) {
  return (
    <Link
      to={`/resume/targets/${target.id}`}
      className="block rounded-lg border border-border bg-card p-3 shadow-xs transition-[border-color,box-shadow] hover:border-primary/40 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="min-w-0">
        <p className="truncate text-sm font-medium" title={target.role_title}>
          {target.role_title}
        </p>
        <p className="truncate text-xs text-muted-foreground">{target.company_name}</p>
      </div>
      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        <Score target={target} />
        {target.tailored_resume ? (
          <span
            className="inline-flex items-center gap-1 whitespace-nowrap rounded-full bg-success-soft px-2 py-0.5 text-[11px] font-medium text-success-soft-foreground"
            title={target.tailored_resume.name}
          >
            <FileCheck2 className="size-3" aria-hidden />
            Tailored v{target.tailored_resume.current_version}
          </span>
        ) : null}
        <TargetDueBadges target={target} />
      </div>
      {target.missing_requirements.length ? (
        <p className="mt-2 line-clamp-1 text-[11px] text-muted-foreground">Missing: {target.missing_requirements.join(', ')}</p>
      ) : null}
    </Link>
  )
})

/** Memoised: typing in the search / company filters must not re-render every card. */
const Board = React.memo(function Board({ targets }: { targets: JobTarget[] }) {
  const columns = JOB_TARGET_STATUSES.map((status) => ({ status, items: targets.filter((t) => t.status === status) }))
  return (
    <div className="-mx-4 overflow-x-auto px-4 pb-2 sm:mx-0 sm:px-0">
      {/* Eight stages never fit legibly in one screen width: each column keeps a readable
          minimum (11rem) and the board scrolls sideways instead of squeezing the cards. */}
      <div className="grid grid-cols-[repeat(8,minmax(11rem,1fr))] gap-3">
        {columns.map(({ status, items }) => (
          <section key={status} aria-label={TARGET_STATUS_LABELS[status]} className="flex min-h-40 flex-col gap-2 rounded-xl bg-surface-2 p-2">
            <h2 className="flex min-h-8 items-center justify-between gap-2 px-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
              <span className="leading-tight">{TARGET_STATUS_LABELS[status]}</span>
              <span className="rounded-full bg-card px-1.5 tabular-nums text-foreground shadow-xs">{items.length}</span>
            </h2>
            {items.map((target) => (
              <TargetCard key={target.id} target={target} />
            ))}
          </section>
        ))}
      </div>
    </div>
  )
})

const TargetTable = React.memo(function TargetTable({ targets }: { targets: JobTarget[] }) {
  const navigate = useNavigate()
  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Role</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Estimate</TableHead>
              <TableHead className="hidden md:table-cell">Resume</TableHead>
              <TableHead className="hidden lg:table-cell">Deadline</TableHead>
              <TableHead className="hidden lg:table-cell">Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {targets.map((target) => (
              <TableRow key={target.id} className="cursor-pointer" onClick={() => navigate(`/resume/targets/${target.id}`)}>
                <TableCell>
                  <Link to={`/resume/targets/${target.id}`} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>
                    {target.role_title}
                  </Link>
                  <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                    {target.company_name}
                    <TargetDueBadges target={target} />
                  </div>
                </TableCell>
                <TableCell>
                  <TargetStatusBadge status={target.status} />
                </TableCell>
                <TableCell className="text-right">
                  <Score target={target} />
                </TableCell>
                <TableCell className="hidden text-sm md:table-cell">
                  {target.tailored_resume ? `${target.tailored_resume.name} (v${target.tailored_resume.current_version})` : target.source_resume?.name ?? '—'}
                </TableCell>
                <TableCell className="hidden text-sm lg:table-cell">{formatDate(target.deadline)}</TableCell>
                <TableCell className="hidden text-sm text-muted-foreground lg:table-cell">{formatRelative(target.updated_at)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
})

const NO_TARGETS: JobTarget[] = []

/** `/resume/targets` — saved job opportunities and their tailored resumes, by status. */
export default function JobTargetsPage() {
  useDocumentTitle('Job-Specific Resumes')
  const navigate = useNavigate()
  const [search, setSearch] = React.useState('')
  const [company, setCompany] = React.useState('')
  const [view, setView] = React.useState<'board' | 'table'>(() => {
    try {
      return (localStorage.getItem(VIEW_KEY) as 'board' | 'table') || 'board'
    } catch {
      return 'board'
    }
  })
  const [dialogOpen, setDialogOpen] = React.useState(false)
  const debouncedSearch = useDebounce(search, 300)
  const debouncedCompany = useDebounce(company, 300)
  const query = useTargets({ search: debouncedSearch || undefined, company: debouncedCompany || undefined, page_size: 100 })
  const targets = query.data?.items ?? NO_TARGETS
  const filtered = Boolean(debouncedSearch || debouncedCompany)

  const chooseView = (next: 'board' | 'table') => {
    // Board <-> table re-renders every target: a transition keeps the buttons responsive.
    React.startTransition(() => setView(next))
    try {
      localStorage.setItem(VIEW_KEY, next)
    } catch {
      /* per-viewer convenience only */
    }
  }

  const counts = JOB_TARGET_STATUSES.reduce(
    (acc, status) => ({ ...acc, [status]: targets.filter((t) => t.status === status).length }),
    {} as Record<JobTargetStatus, number>,
  )

  return (
    <PageContainer width="wide">
      <PageHeader
        title="Job-Specific Resumes"
        description="Each target is one company and role with its job description, a tailored resume and where you are in the process."
        actions={
          <>
            <Button variant="outline" onClick={() => setDialogOpen(true)}>
              <Plus aria-hidden />
              New target
            </Button>
            <Button asChild>
              <Link to="/resume/targets/new">
                <Sparkles aria-hidden />
                Optimize a resume for a job
              </Link>
            </Button>
          </>
        }
      />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative sm:w-72">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" aria-hidden />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search role or company" className="pl-8" aria-label="Search targets" />
        </div>
        <Input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Filter by company" className="sm:w-56" aria-label="Filter by company" />
        <div className="flex gap-1 sm:ml-auto" role="group" aria-label="View">
          <Button variant={view === 'board' ? 'secondary' : 'ghost'} size="sm" onClick={() => chooseView('board')} aria-pressed={view === 'board'}>
            <LayoutGrid aria-hidden />
            Board
          </Button>
          <Button variant={view === 'table' ? 'secondary' : 'ghost'} size="sm" onClick={() => chooseView('table')} aria-pressed={view === 'table'}>
            <List aria-hidden />
            Table
          </Button>
        </div>
      </div>
      {targets.length ? (
        <p className="text-xs text-muted-foreground">
          {query.data?.total} target{query.data?.total === 1 ? '' : 's'} · {counts.READY} ready to apply · {counts.APPLIED + counts.INTERVIEW} in process
        </p>
      ) : null}

      {query.isLoading ? (
        view === 'board' ? <TargetBoardSkeleton /> : <TargetTableSkeleton />
      ) : query.error ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : targets.length === 0 ? (
        <EmptyState
          icon={Crosshair}
          title={filtered ? 'No targets match' : 'No job targets yet'}
          description={
            filtered
              ? 'Try another search or clear the company filter.'
              : 'Paste a job description and pick a resume: JobPilot saves the job here and makes a copy optimized for it. Or save a company and role first.'
          }
          action={
            filtered ? undefined : (
              <div className="flex flex-wrap justify-center gap-2">
                <Button asChild>
                  <Link to="/resume/targets/new">
                    <Sparkles aria-hidden />
                    Optimize a resume for a job
                  </Link>
                </Button>
                <Button variant="outline" onClick={() => setDialogOpen(true)}>
                  <Plus aria-hidden />
                  New target
                </Button>
              </div>
            )
          }
        />
      ) : view === 'board' ? (
        <Board targets={targets} />
      ) : (
        <TargetTable targets={targets} />
      )}

      <TargetFormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onCreated={(target) => {
          toast.success(`Saved ${target.role_title} at ${target.company_name}`)
          navigate(`/resume/targets/${target.id}`)
        }}
      />
    </PageContainer>
  )
}
