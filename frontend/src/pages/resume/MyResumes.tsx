import { ArrowLeft, FilePlus2, FileText, History, PencilRuler, Search, Target, Upload } from 'lucide-react'
import * as React from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { LoadingState } from '@/components/common/LoadingState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { toast } from '@/components/ui/toaster'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useDebounce } from '@/hooks/useDebounce'
import { errorMessage, isApiError } from '@/lib/api'
import { formatRelative } from '@/lib/utils'
import { ParsedDataPanel } from '@/features/resume/components/ParsedDataPanel'
import { ResumeInsights } from '@/features/resume/components/ResumeInsights'
import { ResumeVersionHistory } from '@/features/resume/components/ResumeVersionHistory'
import { TargetRoleSelect } from '@/features/resume/components/TargetRoleSelect'
import {
  exportResume,
  useArchiveResume,
  useDeleteStudioResume,
  useDiscardDraft,
  useDuplicateResume,
  useStudioResume,
  useStudioResumes,
  useTemplates,
  useUnarchiveResume,
  useUpdateStudioResume,
} from '@/features/resume-studio/api'
import { ArchivedBadge, KindBadge } from '@/features/resume-studio/components/badges'
import { ExportMenu } from '@/features/resume-studio/components/ExportMenu'
import { StudioResumeCard } from '@/features/resume-studio/components/StudioResumeCard'
import type { ExportFormat, StudioResumeRead } from '@/features/resume-studio/types'
import type { ResumeKind, ResumeRead } from '@/types/api'

/** `/resume/my` (list) and `/resume/my/:id` (one resume's detail). */
export default function MyResumesPage() {
  const { id } = useParams<{ id: string }>()
  return id ? <ResumeDetail id={id} /> : <ResumeList />
}

/* ------------------------------------------------------------------ shared actions */

function useResumeActions() {
  const navigate = useNavigate()
  const update = useUpdateStudioResume()
  const duplicate = useDuplicateResume()
  const archive = useArchiveResume()
  const unarchive = useUnarchiveResume()
  const remove = useDeleteStudioResume()
  const [renaming, setRenaming] = React.useState<StudioResumeRead | null>(null)
  const [deleting, setDeleting] = React.useState<StudioResumeRead | null>(null)
  const [busyId, setBusyId] = React.useState<string | null>(null)

  const busy = async (id: string, fn: () => Promise<void>) => {
    setBusyId(id)
    try {
      await fn()
    } finally {
      setBusyId(null)
    }
  }

  const actions = {
    rename: (resume: StudioResumeRead) => setRenaming(resume),
    duplicate: (resume: StudioResumeRead) =>
      busy(resume.id, async () => {
        try {
          const copy = await duplicate.mutateAsync({ id: resume.id })
          toast.success(`Duplicated as “${copy.name}”`, {
            action: { label: 'Open', onClick: () => navigate(`/resume/my/${copy.id}`) },
          })
        } catch (error) {
          toast.error('Could not duplicate the resume', { description: errorMessage(error) })
        }
      }),
    setDefault: (resume: StudioResumeRead) =>
      busy(resume.id, async () => {
        try {
          await update.mutateAsync({ id: resume.id, is_default: true })
          toast.success(`“${resume.name}” is now your default resume`, {
            description: 'Applications and matching use the default resume.',
          })
        } catch (error) {
          toast.error('Could not set the default resume', { description: errorMessage(error) })
        }
      }),
    archive: (resume: StudioResumeRead) =>
      busy(resume.id, async () => {
        try {
          await archive.mutateAsync(resume.id)
          toast.success(`Archived “${resume.name}”`, {
            description: 'Hidden from lists, matching and applications. Restore it any time.',
            action: { label: 'Undo', onClick: () => void unarchive.mutateAsync(resume.id) },
          })
        } catch (error) {
          toast.error('Could not archive the resume', { description: errorMessage(error) })
        }
      }),
    unarchive: (resume: StudioResumeRead) =>
      busy(resume.id, async () => {
        try {
          await unarchive.mutateAsync(resume.id)
          toast.success(`Restored “${resume.name}” from the archive`)
        } catch (error) {
          toast.error('Could not restore the resume', { description: errorMessage(error) })
        }
      }),
    remove: (resume: StudioResumeRead) => setDeleting(resume),
    export: (resume: StudioResumeRead, format: ExportFormat) =>
      busy(resume.id, async () => {
        try {
          await exportResume(resume, format)
        } catch (error) {
          toast.error(`Could not export the ${format.toUpperCase()}`, { description: errorMessage(error) })
        }
      }),
  }

  const dialogs = (
    <>
      <RenameDialog
        resume={renaming}
        onClose={() => setRenaming(null)}
        onSave={async (name) => {
          if (!renaming) return
          try {
            await update.mutateAsync({ id: renaming.id, name })
            toast.success('Resume renamed')
            setRenaming(null)
          } catch (error) {
            toast.error('Could not rename the resume', { description: errorMessage(error) })
          }
        }}
        saving={update.isPending}
      />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete “${deleting?.name ?? ''}”?`}
        description="The resume and its versions are removed from your workspace. Applications already submitted keep their own copy. To keep it out of the way without deleting, archive it instead."
        confirmLabel="Delete resume"
        variant="destructive"
        loading={remove.isPending}
        onConfirm={async () => {
          if (!deleting) return
          try {
            await remove.mutateAsync(deleting.id)
            toast.success(`Deleted “${deleting.name}”`)
            setDeleting(null)
            navigate('/resume/my')
          } catch (error) {
            toast.error('Could not delete the resume', { description: errorMessage(error) })
          }
        }}
      />
    </>
  )
  return { actions, dialogs, busyId }
}

function RenameDialog({
  resume,
  onClose,
  onSave,
  saving,
}: {
  resume: StudioResumeRead | null
  onClose: () => void
  onSave: (name: string) => Promise<void>
  saving: boolean
}) {
  const [name, setName] = React.useState('')
  React.useEffect(() => setName(resume?.name ?? ''), [resume])
  return (
    <Dialog open={resume !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Rename resume</DialogTitle>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (name.trim()) void onSave(name.trim())
          }}
        >
          <div className="space-y-1">
            <Label htmlFor="rename-input">Name</Label>
            <Input id="rename-input" autoFocus value={name} maxLength={255} onChange={(e) => setName(e.target.value)} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={saving} disabled={!name.trim()}>
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/* ------------------------------------------------------------------ list */

type SortKey = 'edited' | 'name' | 'created'
const KIND_FILTERS: { value: 'ALL' | ResumeKind; label: string }[] = [
  { value: 'ALL', label: 'All kinds' },
  { value: 'UPLOADED', label: 'Uploaded' },
  { value: 'CREATED', label: 'Built' },
  { value: 'TAILORED', label: 'Tailored' },
]

function ResumeList() {
  useDocumentTitle('My Resumes')
  const [showArchived, setShowArchived] = React.useState(false)
  const [query, setQuery] = React.useState('')
  const [kind, setKind] = React.useState<'ALL' | ResumeKind>('ALL')
  const [role, setRole] = React.useState<string>('ALL')
  const [sort, setSort] = React.useState<SortKey>('edited')
  const search = useDebounce(query, 150).trim().toLowerCase()
  const list = useStudioResumes(showArchived)
  const templates = useTemplates()
  const { actions, dialogs, busyId } = useResumeActions()

  const resumes = React.useMemo(() => list.data ?? [], [list.data])
  const names = React.useMemo(() => new Map(resumes.map((r) => [r.id, r.name])), [resumes])
  const roles = React.useMemo(() => [...new Set(resumes.map((r) => r.target_role).filter(Boolean) as string[])].sort(), [resumes])
  const visible = React.useMemo(() => {
    const edited = (r: StudioResumeRead) => (r.draft_saved_at && r.draft_saved_at > r.updated_at ? r.draft_saved_at : r.updated_at)
    return resumes
      .filter((r) => kind === 'ALL' || r.kind === kind)
      .filter((r) => role === 'ALL' || (role === 'NONE' ? !r.target_role : r.target_role === role))
      .filter((r) => {
        if (!search) return true
        const parsed = r.parsed_data ?? {}
        const hay = [r.name, r.target_role, parsed.headline, parsed.name, ...(parsed.skills ?? [])].join(' ').toLowerCase()
        return hay.includes(search)
      })
      .sort((a, b) => {
        if (sort === 'name') return a.name.localeCompare(b.name)
        if (sort === 'created') return b.created_at.localeCompare(a.created_at)
        return edited(b).localeCompare(edited(a))
      })
  }, [resumes, kind, role, search, sort])

  const templateOf = (id: string) => templates.data?.find((t) => t.id === id) ?? templates.data?.[0]
  const filtered = kind !== 'ALL' || role !== 'ALL' || Boolean(search)

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Resume"
        title="My Resumes"
        description="Every resume you have uploaded, built or tailored. The default resume is the one matching and applications use."
        actions={
          <>
            <Button variant="outline" asChild>
              <Link to="/resume/new?mode=upload">
                <Upload aria-hidden /> Upload
              </Link>
            </Button>
            <Button asChild>
              <Link to="/resume/new">
                <FilePlus2 aria-hidden /> Create resume
              </Link>
            </Button>
          </>
        }
      />

      <div className="flex flex-col gap-3 md:flex-row md:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by name, role or skill"
            aria-label="Search resumes"
            className="pl-8"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={kind} onValueChange={(v) => setKind(v as 'ALL' | ResumeKind)}>
            <SelectTrigger className="h-9 w-36" aria-label="Filter by kind">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {KIND_FILTERS.map((k) => (
                <SelectItem key={k.value} value={k.value}>
                  {k.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={role} onValueChange={setRole}>
            <SelectTrigger className="h-9 w-44" aria-label="Filter by target role">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">All target roles</SelectItem>
              <SelectItem value="NONE">No target role</SelectItem>
              {roles.map((r) => (
                <SelectItem key={r} value={r}>
                  {r}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={sort} onValueChange={(v) => setSort(v as SortKey)}>
            <SelectTrigger className="h-9 w-40" aria-label="Sort">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="edited">Recently edited</SelectItem>
              <SelectItem value="created">Newest first</SelectItem>
              <SelectItem value="name">Name A–Z</SelectItem>
            </SelectContent>
          </Select>
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={showArchived} onCheckedChange={setShowArchived} aria-label="Show archived resumes" />
            Archived
          </label>
        </div>
      </div>

      {list.isLoading ? (
        <LoadingState variant="cards" rows={3} />
      ) : list.error ? (
        <ErrorState error={list.error} title="Could not load your resumes" onRetry={() => void list.refetch()} />
      ) : resumes.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No resumes yet"
          description="Start from your profile, upload a PDF or DOCX, paste text or import your LinkedIn data. Nothing is added that you did not provide."
          action={
            <Button asChild>
              <Link to="/resume/new">
                <FilePlus2 aria-hidden /> Create your first resume
              </Link>
            </Button>
          }
        />
      ) : visible.length === 0 ? (
        <EmptyState
          icon={Search}
          title="No resumes match"
          description={filtered ? 'Try another search or clear the filters.' : 'Nothing to show.'}
          action={
            filtered ? (
              <Button
                variant="outline"
                onClick={() => {
                  setQuery('')
                  setKind('ALL')
                  setRole('ALL')
                }}
              >
                Clear filters
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {visible.map((resume) => (
            <StudioResumeCard
              key={resume.id}
              resume={resume}
              sourceName={resume.source_resume_id ? names.get(resume.source_resume_id) : null}
              template={templateOf(resume.template)}
              busy={busyId === resume.id}
              onRename={() => actions.rename(resume)}
              onDuplicate={() => void actions.duplicate(resume)}
              onSetDefault={() => void actions.setDefault(resume)}
              onArchive={() => void actions.archive(resume)}
              onUnarchive={() => void actions.unarchive(resume)}
              onDelete={() => actions.remove(resume)}
              onExport={(format) => void actions.export(resume, format)}
            />
          ))}
        </div>
      )}
      {dialogs}
    </PageContainer>
  )
}

/* ------------------------------------------------------------------ detail */

function ResumeDetail({ id }: { id: string }) {
  const resume = useStudioResume(id)
  const all = useStudioResumes(true)
  const update = useUpdateStudioResume()
  const discard = useDiscardDraft()
  const { actions, dialogs, busyId } = useResumeActions()
  useDocumentTitle(resume.data?.name ?? 'Resume')

  if (resume.isLoading) {
    return (
      <PageContainer>
        <LoadingState variant="cards" rows={2} />
      </PageContainer>
    )
  }
  if (resume.error || !resume.data) {
    const notFound = isApiError(resume.error) && resume.error.isNotFound
    return (
      <PageContainer>
        {notFound ? (
          <EmptyState
            title="Resume not found"
            description="It may have been deleted."
            action={
              <Button variant="outline" asChild>
                <Link to="/resume/my">Back to My Resumes</Link>
              </Button>
            }
          />
        ) : (
          <ErrorState error={resume.error} onRetry={() => void resume.refetch()} />
        )}
      </PageContainer>
    )
  }

  const r = resume.data
  const source = r.source_resume_id ? all.data?.find((x) => x.id === r.source_resume_id) : null
  const archived = Boolean(r.archived_at)

  return (
    <PageContainer>
      <PageHeader
        eyebrow={
          <Link to="/resume/my" className="inline-flex items-center gap-1 hover:text-foreground">
            <ArrowLeft className="size-4" aria-hidden /> My Resumes
          </Link>
        }
        title={r.name}
        description={
          <span className="flex flex-wrap items-center gap-1.5">
            {r.is_default ? <Badge>Default</Badge> : null}
            <KindBadge kind={r.kind} sourceName={source?.name} />
            {archived ? <ArchivedBadge /> : null}
            <Badge variant="outline">v{r.current_version}</Badge>
            <span>Edited {formatRelative(r.updated_at)}</span>
          </span>
        }
        actions={
          <>
            <Button variant="outline" size="sm" asChild>
              <Link to={`/resume/targets?resume=${r.id}`}>
                <Target aria-hidden /> Tailor for a job
              </Link>
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link to={`/resume/history?resume=${r.id}`}>
                <History aria-hidden /> History
              </Link>
            </Button>
            <ExportMenu resume={r} template={r.template} />
            <Button size="sm" asChild>
              <Link to={`/resume/my/${r.id}/edit`}>
                <PencilRuler aria-hidden /> Edit in editor
              </Link>
            </Button>
          </>
        }
      />

      {r.draft_saved_at ? (
        <Alert>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-2">
            <span>Unsaved draft from {formatRelative(r.draft_saved_at)} — not yet a version.</span>
            <span className="flex gap-2">
              <Button size="sm" asChild>
                <Link to={`/resume/my/${r.id}/edit`}>Resume editing</Link>
              </Button>
              <Button
                size="sm"
                variant="outline"
                loading={discard.isPending}
                onClick={() =>
                  void discard
                    .mutateAsync(r.id)
                    .then(() => toast.success('Draft discarded'))
                    .catch((error) => toast.error('Could not discard the draft', { description: errorMessage(error) }))
                }
              >
                Discard
              </Button>
            </span>
          </AlertDescription>
        </Alert>
      ) : null}
      {archived ? (
        <Alert>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-2">
            <span>This resume is archived: matching and applications do not use it.</span>
            <Button size="sm" variant="outline" onClick={() => void actions.unarchive(r)} loading={busyId === r.id}>
              Restore from archive
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border p-3">
        <span className="text-sm text-muted-foreground">Target role</span>
        <TargetRoleSelect
          size="sm"
          allowNone
          value={r.target_role}
          className="w-64"
          onChange={(role) =>
            void update
              .mutateAsync({ id: r.id, target_role: role ?? '' })
              .then(() => toast.success(role ? `Target role set to ${role}` : 'Target role cleared'))
              .catch((error) => toast.error('Could not update the target role', { description: errorMessage(error) }))
          }
        />
        <div className="ml-auto flex flex-wrap gap-2">
          <Button size="sm" variant="ghost" onClick={() => actions.rename(r)}>
            Rename
          </Button>
          <Button size="sm" variant="ghost" onClick={() => void actions.duplicate(r)}>
            Duplicate
          </Button>
          {!r.is_default && !archived ? (
            <Button size="sm" variant="ghost" onClick={() => void actions.setDefault(r)}>
              Set as default
            </Button>
          ) : null}
          {!archived ? (
            <Button size="sm" variant="ghost" onClick={() => void actions.archive(r)}>
              Archive
            </Button>
          ) : null}
          <Button size="sm" variant="ghost" className="text-destructive" onClick={() => actions.remove(r)}>
            Delete
          </Button>
        </div>
      </div>

      <div className="space-y-6">
        <ResumeInsights resume={r as unknown as ResumeRead} />
        <ParsedDataPanel resume={r as unknown as ResumeRead} />
        <ResumeVersionHistory resumeId={r.id} currentVersion={r.current_version} />
      </div>
      {dialogs}
    </PageContainer>
  )
}
