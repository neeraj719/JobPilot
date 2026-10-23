import { zodResolver } from '@hookform/resolvers/zod'
import {
  ArrowLeft,
  CircleAlert,
  CheckCircle2,
  GitCompareArrows,
  Loader2,
  Maximize2,
  Minus,
  Plus,
  Save,
  ShieldCheck,
  Undo2,
} from 'lucide-react'
import * as React from 'react'
import { FormProvider, useForm, useWatch } from 'react-hook-form'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { LoadingState } from '@/components/common/LoadingState'
import { PageContainer } from '@/components/layout/PageContainer'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { toast } from '@/components/ui/toaster'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { errorMessage, isApiError } from '@/lib/api'
import { formatRelative } from '@/lib/utils'
import { useResumeVersions } from '@/features/resume/api'
import {
  useDiscardDraft,
  useDraft,
  useRestoreVersion,
  useSaveDraft,
  useSaveVersion,
  useStudioResume,
  useTemplates,
  useUpdateStudioResume,
} from '@/features/resume-studio/api'
import { KindBadge } from '@/features/resume-studio/components/badges'
import { CompareDialog } from '@/features/resume-studio/components/CompareDialog'
import { ExportMenu } from '@/features/resume-studio/components/ExportMenu'
import { PAGE_WIDTH_PX, ResumePreview } from '@/features/resume-studio/components/ResumePreview'
import { SectionList, type EditorPanel } from '@/features/resume-studio/components/editor/SectionList'
import {
  AchievementFields,
  CertificationFields,
  EducationFields,
  ExperienceFields,
  HeaderFields,
  ProjectFields,
  SummaryFields,
  TagsField,
} from '@/features/resume-studio/components/editor/SectionForms'
import { useAutosave, useMediaQuery, useUnsavedGuard } from '@/features/resume-studio/hooks'
import { effectiveOrder } from '@/features/resume-studio/layout'
import { editorSchema, toEditorValues, toStudioResume, type EditorValues } from '@/features/resume-studio/schema'
import {
  SECTION_LABELS,
  type ResumeDraftRead,
  type ResumeTemplate,
  type SectionKey,
  type StudioResume,
  type StudioResumeRead,
} from '@/features/resume-studio/types'

/** `/resume/my/:id/edit` — split-screen editor with a live, template-rendered preview. */
export default function ResumeEditorPage() {
  const { id } = useParams<{ id: string }>()
  const resume = useStudioResume(id)
  const draft = useDraft(id)
  const templates = useTemplates()
  useDocumentTitle(resume.data ? `Edit · ${resume.data.name}` : 'Resume editor')

  if (resume.isLoading || draft.isLoading || templates.isLoading) {
    return (
      <PageContainer width="wide">
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
            description="It may have been deleted, or it belongs to another account."
            action={
              <Button asChild variant="outline">
                <Link to="/resume/my">Back to My Resumes</Link>
              </Button>
            }
          />
        ) : (
          <ErrorState error={resume.error} title="Could not open the editor" onRetry={() => void resume.refetch()} />
        )}
      </PageContainer>
    )
  }
  if (templates.error || !templates.data?.length) {
    return (
      <PageContainer>
        <ErrorState error={templates.error} title="Could not load the templates" onRetry={() => void templates.refetch()} />
      </PageContainer>
    )
  }
  return <Editor key={resume.data.id} resume={resume.data} draft={draft.data ?? null} templates={templates.data} />
}

function countOf(values: StudioResume, key: SectionKey): number {
  switch (key) {
    case 'summary':
      return values.summary ? 1 : 0
    case 'skills':
      return values.skills.length
    case 'experience':
      return values.experience.length
    case 'projects':
      return values.projects.length
    case 'education':
      return values.education.length
    case 'certifications':
      return values.certifications.length
    case 'achievements':
      return values.achievements?.length ?? 0
    case 'languages':
      return values.languages?.length ?? 0
  }
}

const PLACEHOLDER_RE = /\[[^[\]]*\]/

/** A `[result]`-style placeholder left in any text of the resume. */
function hasPlaceholder(value: unknown): boolean {
  if (typeof value === 'string') return PLACEHOLDER_RE.test(value)
  if (Array.isArray(value)) return value.some(hasPlaceholder)
  if (value && typeof value === 'object') return Object.values(value).some(hasPlaceholder)
  return false
}

function Editor({ resume, draft, templates }: { resume: StudioResumeRead; draft: ResumeDraftRead | null; templates: ResumeTemplate[] }) {
  const navigate = useNavigate()
  const fromDraft = Boolean(draft?.draft_data)
  const [initial] = React.useState(() => toEditorValues((fromDraft ? draft?.draft_data : resume.parsed_data) as Partial<StudioResume>))
  const [baseline, setBaseline] = React.useState(() => JSON.stringify(toStudioResume(toEditorValues(resume.parsed_data as Partial<StudioResume>))))
  const [showDraftBanner, setShowDraftBanner] = React.useState(fromDraft)
  const [templateId, setTemplateId] = React.useState(resume.template)
  const [panel, setPanel] = React.useState<EditorPanel>('header')
  const [scale, setScale] = React.useState<number | 'fit'>('fit')
  const [fitScale, setFitScale] = React.useState(0.7)
  const [note, setNote] = React.useState('')
  const [saveOpen, setSaveOpen] = React.useState(false)
  const [compare, setCompare] = React.useState<number | null>(null)
  const aiApplied = React.useRef(0)
  const [previewBox, setPreviewBox] = React.useState<HTMLDivElement | null>(null)
  const isDesktop = useMediaQuery('(min-width: 1024px)')
  const [mobileTab, setMobileTab] = React.useState<'edit' | 'preview'>('edit')

  const form = useForm<EditorValues>({ resolver: zodResolver(editorSchema), defaultValues: initial, mode: 'onChange' })
  const watched = useWatch({ control: form.control }) as EditorValues
  const serialized = JSON.stringify(watched)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const studio = React.useMemo(() => toStudioResume(watched), [serialized])
  const template = templates.find((t) => t.id === templateId) ?? templates[0]

  const saveDraft = useSaveDraft(resume.id)
  const discardDraft = useDiscardDraft()
  const saveVersion = useSaveVersion(resume.id)
  const restore = useRestoreVersion()
  const updateResume = useUpdateStudioResume()
  const versions = useResumeVersions(resume.id)

  const [initialStudio] = React.useState(() => toStudioResume(initial))
  const autosave = useAutosave(studio, (data) => saveDraft.mutateAsync(data), { initial: initialStudio })
  useUnsavedGuard(autosave.status === 'pending' || autosave.status === 'saving' || autosave.status === 'error')

  const hasChanges = JSON.stringify(studio) !== baseline
  const order = effectiveOrder(studio.section_order, template)
  const counts = Object.fromEntries(order.concat(['summary', 'skills', 'experience', 'projects', 'education', 'certifications', 'achievements', 'languages'] as SectionKey[]).map((k) => [k, countOf(studio, k)]))

  React.useLayoutEffect(() => {
    const node = previewBox
    if (!node) return
    const update = () => setFitScale(Math.max(0.35, Math.min(1.2, (node.clientWidth - 24) / PAGE_WIDTH_PX)))
    update()
    const observer = new ResizeObserver(update)
    observer.observe(node)
    return () => observer.disconnect()
  }, [previewBox])
  const effectiveScale = scale === 'fit' ? fitScale : scale

  const setOrder = (next: SectionKey[]) => form.setValue('section_order', next, { shouldDirty: true })

  const changeTemplate = async (next: string) => {
    const previous = templateId
    setTemplateId(next)
    try {
      await updateResume.mutateAsync({ id: resume.id, template: next })
    } catch (error) {
      setTemplateId(previous)
      toast.error('Could not switch the template', { description: errorMessage(error) })
    }
  }

  const doSaveVersion = async (versionNote: string) => {
    const valid = await form.trigger()
    if (!valid) {
      toast.error('Fix the highlighted fields first')
      return false
    }
    if (hasPlaceholder(studio)) {
      toast.error('Replace the [placeholders] first', {
        description: 'A bracketed placeholder like [result] is left in your resume. Put in the real outcome or remove it.',
      })
      return false
    }
    try {
      const usedAi = aiApplied.current > 0
      const saved = await saveVersion.mutateAsync({
        data: studio,
        note:
          versionNote.trim() ||
          (usedAi ? `Edited in the editor (${aiApplied.current} AI suggestion${aiApplied.current === 1 ? '' : 's'} applied)` : 'Edited in the editor'),
        changeSource: usedAi ? 'AI' : 'USER',
      })
      aiApplied.current = 0
      autosave.markClean(studio)
      setBaseline(JSON.stringify(studio))
      setShowDraftBanner(false)
      setNote('')
      const previous = saved.current_version - 1
      toast.success(`Saved as version ${saved.current_version}`, {
        description: 'The previous version stays in the history.',
        action:
          previous >= 1
            ? {
                label: 'Undo',
                onClick: () => {
                  void restore
                    .mutateAsync({ id: resume.id, version: previous })
                    .then((restored) => {
                      const values = toEditorValues(restored.parsed_data as Partial<StudioResume>)
                      form.reset(values)
                      const restoredStudio = toStudioResume(values)
                      autosave.markClean(restoredStudio)
                      setBaseline(JSON.stringify(restoredStudio))
                      toast.success(`Restored v${previous} as v${restored.current_version}`)
                    })
                    .catch((error) => toast.error('Could not undo', { description: errorMessage(error) }))
                },
              }
            : undefined,
      })
      return true
    } catch (error) {
      toast.error('Could not save the version', { description: errorMessage(error) })
      return false
    }
  }

  const onDiscardDraft = async () => {
    try {
      await discardDraft.mutateAsync(resume.id)
      const values = toEditorValues(resume.parsed_data as Partial<StudioResume>)
      form.reset(values)
      autosave.markClean(toStudioResume(values))
      setShowDraftBanner(false)
      toast.success('Draft discarded', { description: `Back to version ${resume.current_version}.` })
    } catch (error) {
      toast.error('Could not discard the draft', { description: errorMessage(error) })
    }
  }

  const beforeExport = async () => {
    if (!hasChanges) return
    if (window.confirm('Exports use the last saved version. Save your edits as a new version first?')) {
      await doSaveVersion('')
    }
  }

  const status = (() => {
    switch (autosave.status) {
      case 'pending':
      case 'saving':
        return (
          <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground" role="status">
            <Loader2 className="size-3.5 animate-spin" aria-hidden /> Saving draft…
          </span>
        )
      case 'error':
        return (
          <span className="inline-flex items-center gap-1.5 text-xs text-destructive" role="status">
            <CircleAlert className="size-3.5" aria-hidden /> Draft not saved
            <Button type="button" variant="link" size="sm" className="h-auto p-0 text-xs" onClick={autosave.retry}>
              Retry
            </Button>
          </span>
        )
      case 'saved':
        return (
          <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground" role="status">
            <CheckCircle2 className="size-3.5 text-success" aria-hidden /> Saved draft ·{' '}
            {autosave.savedAt?.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        )
      default:
        return (
          <span className="text-xs text-muted-foreground" role="status">
            {hasChanges ? 'Unsaved draft' : `Version ${resume.current_version} · all changes saved`}
          </span>
        )
    }
  })()

  const sectionForm = (() => {
    const onAi = () => {
      aiApplied.current += 1
    }
    switch (panel) {
      case 'header':
        return <HeaderFields />
      case 'summary':
        return <SummaryFields resumeId={resume.id} onAiApplied={onAi} />
      case 'skills':
        return <TagsField name="skills" label="Skills" placeholder="React, Node.js, PostgreSQL… (Enter to add)" />
      case 'experience':
        return <ExperienceFields resumeId={resume.id} onAiApplied={onAi} />
      case 'projects':
        return <ProjectFields resumeId={resume.id} onAiApplied={onAi} />
      case 'education':
        return <EducationFields />
      case 'certifications':
        return <CertificationFields />
      case 'achievements':
        return <AchievementFields resumeId={resume.id} onAiApplied={onAi} />
      case 'languages':
        return <TagsField name="languages" label="Languages" placeholder="English, Hindi… (Enter to add)" />
    }
  })()

  const versionNumbers = (versions.data ?? []).map((v) => v.version_number)

  const editPane = (
    <div className="grid gap-4 xl:grid-cols-[11rem_minmax(0,1fr)]">
      <SectionList
        order={order}
        counts={counts}
        active={panel}
        onSelect={setPanel}
        onReorder={setOrder}
        onRemove={(key) => {
          setOrder(order.filter((k) => k !== key))
          if (panel === key) setPanel('header')
          toast(`${SECTION_LABELS[key]} hidden from the resume`, {
            description: 'Its content is kept. Add the section again to show it.',
            action: { label: 'Undo', onClick: () => setOrder(order) },
          })
        }}
        onAdd={(key) => {
          setOrder([...order, key])
          setPanel(key)
        }}
      />
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{panel === 'header' ? 'Name & contact' : SECTION_LABELS[panel]}</CardTitle>
          {panel !== 'header' && !order.includes(panel) ? (
            <CardDescription>This section is hidden from the resume.</CardDescription>
          ) : null}
        </CardHeader>
        <CardContent>{sectionForm}</CardContent>
      </Card>
    </div>
  )

  const previewPane = (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Select value={templateId} onValueChange={(v) => void changeTemplate(v)}>
          <SelectTrigger className="h-8 w-44" aria-label="Template">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {templates.map((t) => (
              <SelectItem key={t.id} value={t.id}>
                {t.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="flex items-center gap-1" role="group" aria-label="Zoom">
          <Button type="button" variant="ghost" size="icon-sm" aria-label="Zoom out" onClick={() => setScale(Math.max(0.35, Math.round((effectiveScale - 0.1) * 10) / 10))}>
            <Minus aria-hidden />
          </Button>
          <span className="w-12 text-center text-xs tabular-nums text-muted-foreground">{Math.round(effectiveScale * 100)}%</span>
          <Button type="button" variant="ghost" size="icon-sm" aria-label="Zoom in" onClick={() => setScale(Math.min(1.5, Math.round((effectiveScale + 0.1) * 10) / 10))}>
            <Plus aria-hidden />
          </Button>
          <Button type="button" variant={scale === 'fit' ? 'secondary' : 'ghost'} size="icon-sm" aria-label="Fit to width" onClick={() => setScale('fit')}>
            <Maximize2 aria-hidden />
          </Button>
        </div>
      </div>
      <div ref={setPreviewBox} className="overflow-auto rounded-lg border border-border bg-muted/50 p-3 pb-8">
        <ResumePreview data={studio} template={template} scale={effectiveScale} />
      </div>
    </div>
  )

  return (
    <FormProvider {...form}>
      <PageContainer width="wide" className="space-y-4">
        <header className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0 space-y-1">
            <Link to={`/resume/my/${resume.id}`} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
              <ArrowLeft className="size-4" aria-hidden /> {resume.name}
            </Link>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="truncate text-xl font-semibold tracking-tight">Edit resume</h1>
              <KindBadge kind={resume.kind} />
              {status}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {versionNumbers.length > 1 ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm">
                    <GitCompareArrows aria-hidden /> Compare
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
                    v{resume.current_version} (saved) compared with…
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  {versionNumbers
                    .filter((v) => v !== resume.current_version)
                    .slice(0, 12)
                    .map((v) => (
                      <DropdownMenuItem key={v} onSelect={() => setCompare(v)}>
                        Version {v}
                      </DropdownMenuItem>
                    ))}
                </DropdownMenuContent>
              </DropdownMenu>
            ) : null}
            <ExportMenu resume={resume} template={templateId} beforeExport={beforeExport} />
            <Popover open={saveOpen} onOpenChange={setSaveOpen}>
              <PopoverTrigger asChild>
                <Button size="sm" disabled={!hasChanges} loading={saveVersion.isPending}>
                  <Save aria-hidden /> Save version
                </Button>
              </PopoverTrigger>
              <PopoverContent align="end" className="w-80 space-y-3">
                <form
                  className="space-y-3"
                  onSubmit={(event) => {
                    event.preventDefault()
                    void doSaveVersion(note).then((ok) => ok && setSaveOpen(false))
                  }}
                >
                  <div className="space-y-1">
                    <Label htmlFor="version-note">Note (optional)</Label>
                    <Input id="version-note" value={note} maxLength={500} placeholder="e.g. Tightened bullets for backend roles" onChange={(e) => setNote(e.target.value)} />
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Saves v{resume.current_version + 1}. Earlier versions stay in the history and can be restored.
                  </p>
                  <Button type="submit" size="sm" className="w-full" loading={saveVersion.isPending}>
                    Save version
                  </Button>
                </form>
              </PopoverContent>
            </Popover>
          </div>
        </header>

        {showDraftBanner && draft?.draft_saved_at ? (
          <Alert>
            <Undo2 className="size-4" aria-hidden />
            <AlertDescription className="flex flex-wrap items-center justify-between gap-2">
              <span>
                Resumed your unsaved draft from {formatRelative(draft.draft_saved_at)}
                {draft.current_version !== resume.current_version ? ' (made on an older version)' : ''}.
              </span>
              <span className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => void onDiscardDraft()} loading={discardDraft.isPending}>
                  Discard draft
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setShowDraftBanner(false)}>
                  Keep editing
                </Button>
              </span>
            </AlertDescription>
          </Alert>
        ) : null}

        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-success" aria-hidden />
          Everything here is what you typed, imported or keep in your profile. AI suggestions are marked with ✦ and change nothing until you
          press Apply; they never add numbers, employers, skills or claims you have not written.
        </p>

        {/* Desktop: side by side. Mobile/tablet: Edit / Preview tabs (one copy of the form either way). */}
        {isDesktop ? (
          <div className="grid grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)] gap-5">
            {editPane}
            <div className="sticky top-4 self-start">{previewPane}</div>
          </div>
        ) : (
          <Tabs value={mobileTab} onValueChange={(v) => setMobileTab(v as 'edit' | 'preview')}>
            <TabsList className="w-full">
              <TabsTrigger value="edit" className="flex-1">
                Edit
              </TabsTrigger>
              <TabsTrigger value="preview" className="flex-1">
                Preview
              </TabsTrigger>
            </TabsList>
            <TabsContent value="edit" className="mt-4" forceMount hidden={mobileTab !== 'edit'}>
              {editPane}
            </TabsContent>
            <TabsContent value="preview" className="mt-4">
              {previewPane}
            </TabsContent>
          </Tabs>
        )}

        <div className="flex justify-between">
          <Button variant="ghost" size="sm" onClick={() => navigate(`/resume/my/${resume.id}`)}>
            <ArrowLeft aria-hidden /> Done
          </Button>
        </div>
      </PageContainer>
      {compare !== null ? (
        <CompareDialog
          open
          onOpenChange={(open) => !open && setCompare(null)}
          resumeId={resume.id}
          resumeName={resume.name}
          version={resume.current_version}
          versions={versionNumbers}
          against={compare}
        />
      ) : null}
    </FormProvider>
  )
}
