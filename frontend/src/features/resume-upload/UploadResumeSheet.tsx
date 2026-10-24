import { AlertTriangle, CheckCircle2, Eye, PencilRuler, ScanSearch } from 'lucide-react'
import * as React from 'react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import { toast } from '@/components/ui/toaster'
import { useAiChoiceForUpload } from '@/features/ai-providers/useAiChoiceForUpload'
import { useResumes } from '@/features/resume/api'
import { TargetRoleSelect } from '@/features/resume/components/TargetRoleSelect'
import { errorMessage, isApiError } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { ResumeRead } from '@/types/api'

import { useUploadOriginal } from './api'
import { AfterUploadChoice } from './components/AfterUploadChoice'
import { OriginalFileBadge } from './components/OriginalFileBadge'
import { ResumeDropzone, useCheckedFile } from './components/ResumeDropzone'
import { UploadProgressBar } from './components/UploadProgressBar'
import type { AfterUpload } from './types'
import { nameFromFile, parseSummary } from './validation'

export interface UploadResumeSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** A file dropped on the page: the sheet opens with it attached. */
  initialFile?: File | null
}

/**
 * "Upload my resume": dropzone, name, target role, default switch and the After-upload
 * choice (keep as the original / review in the editor), real upload progress, then a
 * success state with the parse result in one line. Used by the dashboard, My Resumes and
 * the page-wide drop overlay. A right sheet on desktop, a bottom sheet under 640 px.
 */
export function UploadResumeSheet({ open, onOpenChange, initialFile = null }: UploadResumeSheetProps) {
  const navigate = useNavigate()
  const resumes = useResumes()
  const upload = useUploadOriginal()
  // Reading the file may call the AI model: with several usable models the picker asks first.
  const parseChoice = useAiChoiceForUpload()
  const picked = useCheckedFile(initialFile)

  const [name, setName] = React.useState('')
  const [nameTouched, setNameTouched] = React.useState(false)
  const [targetRole, setTargetRole] = React.useState<string | null>(null)
  const [after, setAfter] = React.useState<AfterUpload>('original')
  const hasDefault = Boolean(resumes.data?.some((r) => r.is_default && !r.archived_at))
  const [setDefault, setSetDefault] = React.useState<boolean | null>(null)
  const [created, setCreated] = React.useState<ResumeRead | null>(null)
  const [serverError, setServerError] = React.useState<string | null>(null)

  const defaultOn = setDefault ?? !hasDefault
  const uploading = upload.isPending

  // Prefill the name from the file until the user types one.
  React.useEffect(() => {
    if (!nameTouched) setName(nameFromFile(picked.file))
  }, [picked.file, nameTouched])

  // A fresh sheet every time it opens.
  React.useEffect(() => {
    if (open) return
    const timer = window.setTimeout(() => {
      void picked.setFile(null)
      setName('')
      setNameTouched(false)
      setTargetRole(null)
      setAfter('original')
      setSetDefault(null)
      setCreated(null)
      setServerError(null)
    }, 250)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const close = () => {
    if (uploading) upload.cancel()
    onOpenChange(false)
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!picked.file || !picked.ok || uploading) return
    setServerError(null)
    try {
      const file = picked.file
      const resume = await parseChoice.runWithModel((ai) =>
        upload.mutateAsync({
          file,
          name: name.trim() || undefined,
          targetRole,
          setDefault: defaultOn,
          ai,
        }),
      )
      if (!resume) return // the user closed the "Which model?" dialog
      if (after === 'editor') {
        toast.success('Resume uploaded', { description: 'Review what we read. Your file is kept unchanged.' })
        onOpenChange(false)
        navigate(`/resume/my/${resume.id}/edit`)
        return
      }
      setCreated(resume)
    } catch (error) {
      if (isApiError(error) && error.code === 'aborted') return
      setServerError(errorMessage(error, 'The upload failed. Please try again.'))
    }
  }

  const go = (to: string) => {
    onOpenChange(false)
    navigate(to)
  }

  const summary = created ? parseSummary(created) : null

  return (
    <Sheet open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())}>
      <SheetContent
        side="right"
        aria-describedby="upload-sheet-desc"
        className={cn(
          'flex w-full flex-col gap-0 p-0 sm:max-w-md',
          // Bottom sheet on phones.
          'max-sm:inset-x-0 max-sm:bottom-0 max-sm:top-auto max-sm:h-auto max-sm:max-h-[92dvh] max-sm:rounded-t-3xl max-sm:border-l-0 max-sm:border-t',
          'max-sm:data-[state=open]:slide-in-from-bottom max-sm:data-[state=closed]:slide-out-to-bottom',
          'max-sm:data-[state=open]:slide-in-from-right-0 max-sm:data-[state=closed]:slide-out-to-right-0',
        )}
        data-upload-sheet
      >
        <SheetHeader className="border-b border-border pb-4 pr-12">
          <SheetTitle className="font-display text-lg">{created ? 'Your resume is uploaded' : 'Upload my resume'}</SheetTitle>
          <SheetDescription id="upload-sheet-desc">
            {created
              ? 'The file is saved exactly as you uploaded it.'
              : 'Use the resume file you already have. We keep it as-is and read it so scoring and tailoring work.'}
          </SheetDescription>
        </SheetHeader>

        {created && summary ? (
          <div className="flex-1 space-y-5 overflow-y-auto p-6" data-upload-success>
            <div className="flex items-start gap-3 rounded-xl border border-success/25 bg-success-soft p-4 text-success-soft-foreground">
              <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-success" aria-hidden />
              <div className="min-w-0 space-y-1">
                <p className="truncate font-medium" title={created.name}>
                  {created.name}
                </p>
                <p className="flex flex-wrap items-center gap-1.5 text-sm">
                  <OriginalFileBadge />
                  {created.is_default ? <span>Default resume</span> : null}
                </p>
              </div>
            </div>
            <p
              role="status"
              className={cn('flex items-start gap-2 text-sm', summary.ok ? 'text-foreground' : 'text-warning-soft-foreground')}
              data-parse-summary
            >
              {summary.ok ? (
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
              ) : (
                <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
              )}
              <span>{summary.text}</span>
            </p>
            <div className="grid gap-2">
              <Button autoFocus onClick={() => go(`/resume/my/${created.id}`)}>
                <Eye aria-hidden /> View
              </Button>
              <Button variant="outline" onClick={() => go(`/resume/ats?resume=${created.id}`)}>
                <ScanSearch aria-hidden /> Check against a job
              </Button>
              <Button variant="ghost" onClick={() => go(`/resume/my/${created.id}/edit`)}>
                <PencilRuler aria-hidden /> Open in editor
              </Button>
            </div>
          </div>
        ) : (
          <form id="upload-sheet-form" onSubmit={(e) => void submit(e)} className="flex min-h-0 flex-1 flex-col">
            <div className="flex-1 space-y-5 overflow-y-auto p-6">
              {uploading ? (
                <UploadProgressBar progress={upload.progress} fileName={picked.file?.name} />
              ) : (
                <ResumeDropzone
                  id="upload-sheet-file"
                  file={picked.file}
                  problem={picked.problem}
                  onFile={(file) => {
                    setServerError(null)
                    void picked.setFile(file)
                  }}
                />
              )}
              {serverError ? (
                <p role="alert" className="rounded-lg bg-destructive-soft px-3 py-2 text-sm text-destructive-soft-foreground">
                  {serverError}
                </p>
              ) : null}

              <div className="space-y-1.5">
                <Label htmlFor="upload-sheet-name">Name</Label>
                <Input
                  id="upload-sheet-name"
                  value={name}
                  maxLength={255}
                  disabled={uploading}
                  placeholder="e.g. Backend Engineer resume"
                  onChange={(e) => {
                    setNameTouched(true)
                    setName(e.target.value)
                  }}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="upload-sheet-role">
                  Target role <span className="font-normal text-muted-foreground">(optional)</span>
                </Label>
                <TargetRoleSelect id="upload-sheet-role" allowNone value={targetRole} onChange={setTargetRole} disabled={uploading} />
              </div>
              <label className="flex items-start gap-3 text-sm">
                <Switch
                  checked={defaultOn}
                  onCheckedChange={(v) => setSetDefault(v)}
                  disabled={uploading}
                  aria-describedby="upload-sheet-default-hint"
                  className="mt-0.5"
                />
                <span>
                  <span className="block font-medium">Set as default</span>
                  <span id="upload-sheet-default-hint" className="block text-xs text-muted-foreground">
                    Matching and applications use the default resume.
                  </span>
                </span>
              </label>
              <AfterUploadChoice id="upload-sheet-after" value={after} onChange={setAfter} disabled={uploading} />
            </div>
            <SheetFooter className="border-t border-border px-6 py-4 max-sm:pb-[max(1rem,env(safe-area-inset-bottom))]">
              <Button type="button" variant="outline" onClick={close}>
                {uploading ? 'Cancel upload' : 'Cancel'}
              </Button>
              <Button type="submit" disabled={!picked.ok} loading={uploading}>
                Upload resume
              </Button>
            </SheetFooter>
          </form>
        )}
      </SheetContent>
    </Sheet>
  )
}

/** Open the upload sheet from anywhere on a page (button, empty state, drop overlay). */
export function useUploadSheet() {
  const [open, setOpen] = React.useState(false)
  const [file, setFile] = React.useState<File | null>(null)
  const openSheet = React.useCallback((next?: File | null) => {
    setFile(next ?? null)
    setOpen(true)
  }, [])
  const element = <UploadResumeSheet open={open} onOpenChange={setOpen} initialFile={file} />
  return { open, openSheet, element }
}
