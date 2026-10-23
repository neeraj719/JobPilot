import { GitCompareArrows, History, RotateCcw } from 'lucide-react'
import * as React from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { LoadingState } from '@/components/common/LoadingState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { toast } from '@/components/ui/toaster'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { errorMessage } from '@/lib/api'
import { cn, formatDate, formatDateTime, formatRelative } from '@/lib/utils'
import { useHistory, useRestoreVersion, useStudioResumes } from '@/features/resume-studio/api'
import { ArchivedBadge, ChangeSourceBadge, KindBadge } from '@/features/resume-studio/components/badges'
import { CompareDialog } from '@/features/resume-studio/components/CompareDialog'
import type { HistoryItem } from '@/features/resume-studio/types'
import type { ResumeChangeSource } from '@/types/api'

const SOURCES: { value: 'ALL' | ResumeChangeSource; label: string }[] = [
  { value: 'ALL', label: 'All changes' },
  { value: 'USER', label: 'Edited by you' },
  { value: 'AI', label: 'Made by AI' },
  { value: 'SYSTEM', label: 'System (upload, restore…)' },
]

/** `/resume/history` — every version of every resume; compare and restore. Deep link `?resume=<id>&v=<n>`. */
export default function VersionHistoryPage() {
  useDocumentTitle('Version History')
  const [params, setParams] = useSearchParams()
  const resumeId = params.get('resume') || undefined
  const source = (params.get('source') as ResumeChangeSource | null) || undefined
  const deepVersion = Number(params.get('v')) || null

  const resumes = useStudioResumes(true)
  const history = useHistory({ resume_id: resumeId, change_source: source })
  const restore = useRestoreVersion()
  const [compare, setCompare] = React.useState<HistoryItem | null>(null)
  const [restoring, setRestoring] = React.useState<HistoryItem | null>(null)

  const items = React.useMemo(() => history.data?.pages.flatMap((p) => p.items) ?? [], [history.data])

  // Deep link: open the comparison for ?resume=&v= once the row is loaded.
  const opened = React.useRef(false)
  React.useEffect(() => {
    if (opened.current || !deepVersion || !resumeId) return
    const row = items.find((i) => i.resume_id === resumeId && i.version_number === deepVersion)
    if (row) {
      opened.current = true
      setCompare(row)
    }
  }, [items, deepVersion, resumeId])


  const setFilter = (key: 'resume' | 'source', value: string | undefined) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    next.delete('v')
    setParams(next, { replace: true })
  }

  const groups = React.useMemo(() => {
    const map = new Map<string, HistoryItem[]>()
    for (const item of items) {
      const day = formatDate(item.created_at, 'EEEE, d MMM yyyy')
      map.set(day, [...(map.get(day) ?? []), item])
    }
    return [...map.entries()]
  }, [items])

  const confirmRestore = async () => {
    if (!restoring) return
    const target = restoring
    try {
      const resume = await restore.mutateAsync({ id: target.resume_id, version: target.version_number })
      const previous = resume.current_version - 1
      toast.success(`Restored v${target.version_number} as v${resume.current_version}`, {
        description: `${target.resume_name}: nothing was overwritten.`,
        action: {
          label: 'Undo',
          onClick: () =>
            void restore
              .mutateAsync({ id: target.resume_id, version: previous })
              .then(() => toast.success(`Back to the content of v${previous}`))
              .catch((error) => toast.error('Could not undo', { description: errorMessage(error) })),
        },
      })
      setRestoring(null)
    } catch (error) {
      toast.error('Could not restore the version', { description: errorMessage(error) })
    }
  }

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Resume"
        title="Version History"
        description="Every saved version of every resume, newest first. AI-made versions are marked so you can review them; restoring never overwrites anything — it saves a new version."
      />

      <div className="flex flex-wrap items-center gap-2">
        <Select value={resumeId ?? 'ALL'} onValueChange={(v) => setFilter('resume', v === 'ALL' ? undefined : v)}>
          <SelectTrigger className="h-9 w-64" aria-label="Filter by resume">
            <SelectValue placeholder="All resumes" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All resumes</SelectItem>
            {(resumes.data ?? []).map((r) => (
              <SelectItem key={r.id} value={r.id}>
                {r.name}
                {r.archived_at ? ' (archived)' : ''}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={source ?? 'ALL'} onValueChange={(v) => setFilter('source', v === 'ALL' ? undefined : v)}>
          <SelectTrigger className="h-9 w-56" aria-label="Filter by who made the change">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SOURCES.map((s) => (
              <SelectItem key={s.value} value={s.value}>
                {s.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {resumeId || source ? (
          <Button variant="ghost" size="sm" onClick={() => setParams({}, { replace: true })}>
            Clear filters
          </Button>
        ) : null}
      </div>

      {history.isLoading ? (
        <LoadingState rows={6} />
      ) : history.error ? (
        <ErrorState error={history.error} title="Could not load the history" onRetry={() => void history.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={History}
          title={resumeId || source ? 'No versions match' : 'No versions yet'}
          description={
            resumeId || source
              ? 'Try another filter.'
              : 'Create or upload a resume. Every save, applied suggestion and restore appears here.'
          }
          action={
            resumeId || source ? undefined : (
              <Button asChild>
                <Link to="/resume/new">Create a resume</Link>
              </Button>
            )
          }
        />
      ) : (
        <div className="space-y-6">
          {groups.map(([day, rows]) => (
            <section key={day} className="space-y-2" aria-label={day}>
              <h2 className="text-sm font-semibold text-muted-foreground">{day}</h2>
              <ol className="relative space-y-2 border-l border-border pl-4">
                {rows.map((item) => (
                  <li key={item.id} className="relative">
                    <span
                      className={cn(
                        'absolute -left-[21px] top-4 size-2.5 rounded-full ring-4 ring-background',
                        item.change_source === 'AI' ? 'bg-violet-500' : item.change_source === 'SYSTEM' ? 'bg-muted-foreground' : 'bg-primary',
                      )}
                      aria-hidden
                    />
                    <Card className={cn(item.change_source === 'AI' && 'border-violet-500/30')}>
                      <CardContent className="flex flex-col gap-3 p-3 sm:flex-row sm:items-center">
                        <div className="min-w-0 flex-1 space-y-1">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <Link to={`/resume/my/${item.resume_id}`} className="truncate font-medium hover:underline">
                              {item.resume_name}
                            </Link>
                            <Badge variant="outline">v{item.version_number}</Badge>
                            {item.is_current ? <Badge variant="muted">Current</Badge> : null}
                            <ChangeSourceBadge source={item.change_source} />
                            <KindBadge kind={item.resume_kind} />
                            {item.resume_archived ? <ArchivedBadge /> : null}
                          </div>
                          <p className="text-sm">{item.change_summary}</p>
                          {item.note ? <p className="text-xs text-muted-foreground">“{item.note}”</p> : null}
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          <time className="text-xs text-muted-foreground" dateTime={item.created_at} title={formatDateTime(item.created_at)}>
                            {formatRelative(item.created_at)}
                          </time>
                          <Button size="sm" variant="outline" onClick={() => setCompare(item)}>
                            <GitCompareArrows aria-hidden /> Compare
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => setRestoring(item)} disabled={item.is_current}>
                            <RotateCcw aria-hidden /> Restore
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  </li>
                ))}
              </ol>
            </section>
          ))}
          {history.hasNextPage ? (
            <div className="flex justify-center">
              <Button variant="outline" onClick={() => void history.fetchNextPage()} loading={history.isFetchingNextPage}>
                Load older versions
              </Button>
            </div>
          ) : null}
        </div>
      )}

      {compare ? (
        <CompareDialog
          open
          onOpenChange={(open) => !open && setCompare(null)}
          resumeId={compare.resume_id}
          resumeName={compare.resume_name}
          version={compare.version_number}
        />
      ) : null}
      <ConfirmDialog
        open={restoring !== null}
        onOpenChange={(open) => !open && setRestoring(null)}
        title={`Restore v${restoring?.version_number ?? ''} of “${restoring?.resume_name ?? ''}”?`}
        description="Its content becomes a new version on top of the history. The current version stays in the history, so you can switch back at any time."
        confirmLabel="Restore as new version"
        loading={restore.isPending}
        onConfirm={confirmRestore}
      />
    </PageContainer>
  )
}
