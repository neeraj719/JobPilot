import { ArrowLeft, ArrowRight, ClipboardPaste, FilePlus2, FileUp, Linkedin, ShieldCheck, UserRound } from 'lucide-react'
import * as React from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { SkeletonLine, SkeletonRegion } from '@/components/common/skeletons'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { toast } from '@/components/ui/toaster'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { errorMessage } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useUploadOriginal } from '@/features/resume-upload/api'
import { AfterUploadChoice } from '@/features/resume-upload/components/AfterUploadChoice'
import { ResumeDropzone, useCheckedFile } from '@/features/resume-upload/components/ResumeDropzone'
import { UploadProgressBar } from '@/features/resume-upload/components/UploadProgressBar'
import type { AfterUpload } from '@/features/resume-upload/types'
import { parseSummary } from '@/features/resume-upload/validation'
import { TargetRoleSelect } from '@/features/resume/components/TargetRoleSelect'
import { useJobPreferences } from '@/features/profile/api'
import {
  useBuildResume,
  useImportLinkedin,
  useImportText,
  usePrefill,
  useTemplates,
  useUpdateStudioResume,
} from '@/features/resume-studio/api'
import { TemplatePicker } from '@/features/resume-studio/components/TemplatePicker'
import { EMPTY_RESUME } from '@/features/resume-studio/schema'
import type { StudioResume } from '@/features/resume-studio/types'
import { useAiChoice } from '@/features/ai-providers/useAiChoice'
import { LinkedInConnectPanel } from '@/features/linkedin/components/LinkedInConnectPanel'

type Mode = 'profile' | 'upload' | 'paste' | 'connect' | 'linkedin' | 'blank'

const MODES: { id: Mode; title: string; description: string; Icon: typeof UserRound }[] = [
  { id: 'upload', title: 'Upload my resume', description: 'Keep your original file as-is. We also read it so scoring and tailoring work.', Icon: FileUp },
  { id: 'profile', title: 'Start from my profile', description: 'Your saved profile and preferences: verified facts only.', Icon: UserRound },
  { id: 'paste', title: 'Paste resume text', description: 'Copy the text from any document or site you wrote it in.', Icon: ClipboardPaste },
  { id: 'connect', title: 'Connect LinkedIn', description: 'Sign in with LinkedIn to fill your name, email and photo; review before anything is saved.', Icon: Linkedin },
  { id: 'linkedin', title: 'Import LinkedIn export', description: '…or upload the ZIP export for your full history.', Icon: Linkedin },
  { id: 'blank', title: 'Blank resume', description: 'Start with empty sections and fill them in yourself.', Icon: FilePlus2 },
]

const isMode = (value: string | null): value is Mode => MODES.some((m) => m.id === value)

function count(data: StudioResume | undefined): string[] {
  if (!data) return []
  const bits: string[] = []
  if (data.experience?.length) bits.push(`${data.experience.length} role${data.experience.length === 1 ? '' : 's'}`)
  if (data.skills?.length) bits.push(`${data.skills.length} skills`)
  if (data.education?.length) bits.push(`${data.education.length} education`)
  if (data.projects?.length) bits.push(`${data.projects.length} project${data.projects.length === 1 ? '' : 's'}`)
  if (data.certifications?.length) bits.push(`${data.certifications.length} certification${data.certifications.length === 1 ? '' : 's'}`)
  return bits
}

/** `/resume/new` — pick a starting point, name it, choose a template, land in the editor. */
export default function CreateResumePage() {
  useDocumentTitle('Create Resume')
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  // `?source=linkedin` is where the LinkedIn OAuth callback (and its notification) lands.
  const mode: Mode | null = params.get('source') === 'linkedin' ? 'connect' : isMode(params.get('mode')) ? (params.get('mode') as Mode) : null
  const setMode = (next: Mode | null) => setParams(next ? { mode: next } : {}, { replace: true })

  const templates = useTemplates()
  const prefs = useJobPreferences()
  const prefill = usePrefill(mode === 'profile')
  const build = useBuildResume()
  const importText = useImportText()
  const parseChoice = useAiChoice('parse_resume')
  const importLinkedin = useImportLinkedin()
  const upload = useUploadOriginal()
  const update = useUpdateStudioResume()

  const [name, setName] = React.useState('')
  const [targetRole, setTargetRole] = React.useState<string | null>(null)
  const [template, setTemplate] = React.useState('classic')
  const [setDefault, setSetDefault] = React.useState(false)
  const [text, setText] = React.useState('')
  const picked = useCheckedFile()
  const file = picked.file
  const [after, setAfter] = React.useState<AfterUpload>('original')
  const keepOriginal = mode === 'upload' && after === 'original'
  const [linkedinFiles, setLinkedinFiles] = React.useState<File[]>([])

  React.useEffect(() => {
    if (!targetRole && prefs.data?.desired_titles?.[0]) setTargetRole(prefs.data.desired_titles[0])
  }, [prefs.data, targetRole])

  const busy = build.isPending || importText.isPending || importLinkedin.isPending || upload.isPending
  const profileEmpty = mode === 'profile' && prefill.data && !prefill.data.name && !(prefill.data.experience ?? []).length

  const canSubmit = (() => {
    switch (mode) {
      case 'upload':
        return picked.ok
      case 'paste':
        return text.trim().length >= 30
      case 'linkedin':
        return linkedinFiles.length > 0
      case 'profile':
        return Boolean(prefill.data)
      case 'blank':
        return true
      default:
        return false
    }
  })()

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!mode || !canSubmit) return
    const displayName = name.trim() || undefined
    try {
      let id: string
      if (mode === 'upload' && file) {
        const created = await parseChoice.runWithModel((ai) => upload.mutateAsync({ file, name: displayName, targetRole: targetRole ?? undefined, setDefault, ai }))
        if (!created) return // the "Which model?" dialog was cancelled
        if (template !== 'classic') await update.mutateAsync({ id: created.id, template })
        id = created.id
        if (after === 'original') {
          // Keep as original: the flow ends on the uploaded resume's page, not in the editor.
          toast.success('Resume uploaded — kept as your original file', { description: parseSummary(created).text })
          navigate(`/resume/my/${created.id}`)
          return
        }
        if (created.parse_status !== 'PARSED') {
          toast.warning('We could not read everything from that file', { description: created.parse_error ?? 'Fill in the sections in the editor.' })
        }
      } else if (mode === 'paste') {
        // Parsing pasted text may call the AI model: ask which one when the user has several.
        const created = await parseChoice.runWithModel((ai) => importText.mutateAsync({ text, name: displayName, target_role: targetRole, template, ai }))
        if (!created) return
        id = created.id
      } else if (mode === 'linkedin') {
        id = (await importLinkedin.mutateAsync({ files: linkedinFiles, name: displayName, targetRole, template })).id
      } else {
        const data = mode === 'profile' && prefill.data ? prefill.data : EMPTY_RESUME
        id = (
          await build.mutateAsync({
            name: displayName ?? (mode === 'profile' ? `${data.name ?? 'My'} resume` : 'Untitled resume'),
            target_role: targetRole,
            template,
            parsed_data: data,
            set_default: setDefault,
          })
        ).id
      }
      toast.success('Resume created', { description: 'Review every section, then save a version or export it.' })
      navigate(`/resume/my/${id}/edit`)
    } catch (error) {
      toast.error('Could not create the resume', { description: errorMessage(error) })
    }
  }

  return (
    <PageContainer width="default">
      <PageHeader
        eyebrow="Resume"
        title="Create Resume"
        description="Choose where to start. Whatever you pick, the resume holds only facts you provided — JobPilot never invents experience, numbers or qualifications."
      />

      <div role="radiogroup" aria-label="How do you want to start?" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {MODES.map(({ id, title, description, Icon }) => (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={mode === id}
            onClick={() => setMode(id)}
            className={cn(
              'flex flex-col gap-2 rounded-lg border bg-card p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              mode === id ? 'border-primary ring-1 ring-primary/40' : 'border-border hover:border-primary/40',
            )}
          >
            <span className={cn('flex size-9 items-center justify-center rounded-md', mode === id ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground')}>
              <Icon className="size-5" aria-hidden />
            </span>
            <span className="text-sm font-semibold">{title}</span>
            <span className="text-xs text-muted-foreground">{description}</span>
          </button>
        ))}
      </div>

      {mode === 'connect' ? (
        <LinkedInConnectPanel onBack={() => setMode(null)} />
      ) : mode ? (
        <form onSubmit={(e) => void submit(e)} className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{MODES.find((m) => m.id === mode)?.title}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {mode === 'profile' ? (
                prefill.isLoading ? (
                  <SkeletonRegion label="Reading your profile" className="flex items-start gap-2">
                    <Skeleton className="mt-0.5 size-4 shrink-0 rounded-full" />
                    <div className="min-w-0 flex-1">
                      <SkeletonLine size="sm" className="w-full" />
                      <SkeletonLine size="sm" className="w-1/2" />
                    </div>
                  </SkeletonRegion>
                ) : prefill.error ? (
                  <p className="text-sm text-destructive">{errorMessage(prefill.error)}</p>
                ) : profileEmpty ? (
                  <Alert>
                    <AlertTitle>Your profile is mostly empty</AlertTitle>
                    <AlertDescription>
                      Fill in your <Link className="underline" to="/profile">profile</Link> first, or start with a blank resume — nothing will be made up for you.
                    </AlertDescription>
                  </Alert>
                ) : (
                  <p className="flex items-start gap-2 text-sm">
                    <ShieldCheck className="mt-0.5 size-4 text-success" aria-hidden />
                    <span>
                      Filled from your profile: <strong>{prefill.data?.name}</strong>
                      {count(prefill.data).length ? ` · ${count(prefill.data).join(' · ')}` : ''}. You can edit everything next.
                    </span>
                  </p>
                )
              ) : null}

              {mode === 'upload' ? (
                <div className="space-y-4">
                  {upload.isPending ? (
                    <UploadProgressBar progress={upload.progress} fileName={file?.name} />
                  ) : (
                    <ResumeDropzone id="create-file" file={file} problem={picked.problem} onFile={(f) => void picked.setFile(f)} />
                  )}
                  <AfterUploadChoice id="create-after" value={after} onChange={setAfter} disabled={upload.isPending} />
                </div>
              ) : null}

              {mode === 'paste' ? (
                <div className="space-y-1">
                  <Label htmlFor="create-text">Resume text</Label>
                  <Textarea
                    id="create-text"
                    rows={12}
                    value={text}
                    maxLength={60000}
                    placeholder={'Your Name\nemail@example.com | +91 …\n\nExperience\nSoftware Engineer | Company\nMar 2023 - Present\n- What you did…'}
                    onChange={(e) => setText(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    Section headings (Experience, Education, Skills…) help the parser. Text is treated as data only.
                  </p>
                </div>
              ) : null}

              {mode === 'linkedin' ? (
                <div className="space-y-3">
                  <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
                    <li>On LinkedIn open <strong>Settings &amp; Privacy → Data privacy → Get a copy of your data</strong>.</li>
                    <li>Choose the files you want (Profile, Positions, Education, Skills…) or the full archive, and request it.</li>
                    <li>LinkedIn emails you a download link (usually within minutes). Download the ZIP.</li>
                    <li>Upload the ZIP here — or just its CSV files.</li>
                  </ol>
                  <Alert>
                    <ShieldCheck className="size-4" aria-hidden />
                    <AlertDescription>
                      JobPilot never logs in to LinkedIn and never scrapes it. The export is read in memory and not stored; only the
                      resume made from it is saved (and, if you connected LinkedIn, the same details on that connection for syncing).
                    </AlertDescription>
                  </Alert>
                  <div className="space-y-1">
                    <Label htmlFor="create-linkedin">LinkedIn export (.zip or .csv files)</Label>
                    <Input
                      id="create-linkedin"
                      type="file"
                      multiple
                      accept=".zip,.csv,application/zip,text/csv"
                      onChange={(e) => setLinkedinFiles(Array.from(e.target.files ?? []))}
                    />
                  </div>
                </div>
              ) : null}

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label htmlFor="create-name">Resume name</Label>
                  <Input
                    id="create-name"
                    value={name}
                    maxLength={255}
                    placeholder={targetRole ? `${targetRole} resume` : 'e.g. Backend Engineer resume'}
                    onChange={(e) => setName(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <Label>Target role</Label>
                  <TargetRoleSelect allowNone value={targetRole} onChange={setTargetRole} />
                </div>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <Switch checked={setDefault} onCheckedChange={setSetDefault} />
                Make it my default resume (used by matching and applications)
              </label>
            </CardContent>
          </Card>

          {keepOriginal ? null : (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Template</CardTitle>
              <CardDescription>All templates are single-column with real headings, so applicant tracking systems read them correctly. You can switch later.</CardDescription>
            </CardHeader>
            <CardContent>
              <TemplatePicker
                templates={templates.data}
                loading={templates.isLoading}
                value={template}
                onChange={setTemplate}
                data={mode === 'profile' ? prefill.data : undefined}
              />
            </CardContent>
          </Card>
          )}

          <div className="flex flex-wrap justify-between gap-2">
            <Button type="button" variant="ghost" onClick={() => setMode(null)}>
              <ArrowLeft aria-hidden /> Choose another start
            </Button>
            <Button type="submit" disabled={!canSubmit} loading={busy}>
              {keepOriginal ? 'Upload and keep as original' : 'Create and open the editor'} <ArrowRight aria-hidden />
            </Button>
          </div>
        </form>
      ) : (
        <p className="text-sm text-muted-foreground">Pick a starting point above to continue.</p>
      )}
    </PageContainer>
  )
}
