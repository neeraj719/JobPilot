import { AlertTriangle, Copy, Download, ExternalLink, FileText, Lock, PencilLine, RefreshCw, Star } from 'lucide-react'
import * as React from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ErrorState } from '@/components/common/ErrorState'
import { SkeletonLine, SkeletonRegion } from '@/components/common/skeletons'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { toast } from '@/components/ui/toaster'
import { formatBytes } from '@/features/resume/api'
import { errorMessage, isApiError } from '@/lib/api'
import { cn, formatDate } from '@/lib/utils'
import type { ResumeRead } from '@/types/api'

import { downloadOriginal, useEditCopy, useFileInfo, useOriginalFileUrl, useReplaceFile } from './api'
import { ResumeDropzone, useCheckedFile } from './components/ResumeDropzone'
import { UploadProgressBar } from './components/UploadProgressBar'
import type { ResumeFileInfo } from './types'
import { parseSummary } from './validation'

type UploadedResume = Pick<
  ResumeRead,
  'id' | 'name' | 'is_default' | 'archived_at' | 'original_filename' | 'current_version' | 'parse_status' | 'parsed_data' | 'kind'
>

const PREVIEW_HEIGHT = 'h-[70vh] min-h-[28rem] lg:h-[min(80vh,62rem)]'

/* ------------------------------------------------------------------ actions */

/** "Edit a copy in the editor": a CREATED copy, so the uploaded original is never modified. */
export function EditCopyButton({ resume, size = 'sm', className }: { resume: UploadedResume; size?: 'sm' | 'default'; className?: string }) {
  const navigate = useNavigate()
  const copy = useEditCopy()
  return (
    <Button
      size={size}
      className={className}
      loading={copy.isPending}
      onClick={() =>
        void copy
          .mutateAsync({ id: resume.id })
          .then((created) => {
            toast.success(`Made an editable copy: “${created.name}”`, {
              description: 'Your uploaded original stays exactly as it is.',
            })
            navigate(`/resume/my/${created.id}/edit`)
          })
          .catch((error) => toast.error('Could not make a copy', { description: errorMessage(error) }))
      }
    >
      <Copy aria-hidden /> Edit a copy in the editor
    </Button>
  )
}

async function download(resume: UploadedResume) {
  try {
    await downloadOriginal(resume)
  } catch (error) {
    toast.error('Could not download the file', { description: errorMessage(error) })
  }
}

/* ------------------------------------------------------------------ preview */

function PageSkeleton({ label }: { label: string }) {
  return (
    <SkeletonRegion label={label} className={cn('flex justify-center overflow-hidden rounded-xl border border-border bg-surface-2 p-4 sm:p-8', PREVIEW_HEIGHT)}>
      <div className="w-full max-w-2xl space-y-3 rounded-lg border border-border bg-card p-6 shadow-xs sm:p-10">
        <SkeletonLine size="lg" className="w-1/2" />
        <SkeletonLine size="sm" className="w-2/3" />
        <div className="pt-4" />
        {Array.from({ length: 4 }).map((_, block) => (
          <div key={block} className="space-y-2 pt-2">
            <SkeletonLine size="base" className="w-1/3" />
            <SkeletonLine size="sm" className="w-full" />
            <SkeletonLine size="sm" className="w-11/12" />
            <SkeletonLine size="sm" className="w-4/5" />
          </div>
        ))}
      </div>
    </SkeletonRegion>
  )
}

function ExtractedText({ info }: { info: ResumeFileInfo }) {
  if (!info.extracted_text) {
    return (
      <p className="rounded-xl border border-border bg-surface-2 p-6 text-sm text-muted-foreground">
        We could not read any text from this file. You can still download it and use it as-is.
      </p>
    )
  }
  return (
    <div
      className={cn('overflow-y-auto rounded-xl border border-border bg-surface-2 p-3 sm:p-6', PREVIEW_HEIGHT)}
      tabIndex={0}
      aria-label="Text we read from your file"
      data-extracted-text
    >
      <div className="mx-auto max-w-2xl whitespace-pre-wrap break-words rounded-lg border border-border bg-card p-5 text-sm leading-relaxed shadow-xs sm:p-8">
        {info.extracted_text}
        {info.text_truncated ? <p className="mt-4 text-xs text-muted-foreground">…the rest is in the file.</p> : null}
      </div>
    </div>
  )
}

function PdfPreview({ resume }: { resume: UploadedResume }) {
  const file = useOriginalFileUrl(resume.id, resume.current_version, true)
  if (file.loading) return <PageSkeleton label="Loading the PDF preview" />
  if (file.error || !file.url) {
    return <ErrorState size="sm" title="Could not load the preview" error={file.error} onRetry={file.retry} />
  }
  return (
    <object
      // Viewer hints (Chrome / Edge / Firefox): no thumbnail pane, fit the page width.
      data={`${file.url}#navpanes=0&view=FitH`}
      type="application/pdf"
      aria-label={`Preview of ${resume.original_filename ?? 'your resume'}`}
      className={cn('w-full rounded-xl border border-border bg-surface-2', PREVIEW_HEIGHT)}
      data-pdf-preview
    >
      {/* Shown by browsers that cannot display a PDF inline (most phones). */}
      <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
        <FileText className="size-10 text-muted-foreground" aria-hidden />
        <p className="text-sm text-muted-foreground">This browser cannot show the PDF here.</p>
        <div className="flex flex-wrap justify-center gap-2">
          <Button variant="outline" size="sm" asChild>
            <a href={file.url} target="_blank" rel="noreferrer">
              <ExternalLink aria-hidden /> Open the PDF
            </a>
          </Button>
          <Button variant="outline" size="sm" onClick={() => void download(resume)}>
            <Download aria-hidden /> Download
          </Button>
        </div>
      </div>
    </object>
  )
}

function OriginalPreview({ resume, info }: { resume: UploadedResume; info: ResumeFileInfo }) {
  if (info.file_missing) {
    return (
      <Alert variant="warning">
        <AlertTriangle className="size-4" aria-hidden />
        <AlertTitle>The stored file is missing</AlertTitle>
        <AlertDescription>Replace the file to restore the preview and downloads. The data we read earlier is still here.</AlertDescription>
      </Alert>
    )
  }
  if (info.format === 'pdf' && info.previewable) return <PdfPreview resume={resume} />
  if (info.format === 'pdf' && info.encrypted) {
    return (
      <div className="space-y-3">
        <Alert variant="warning">
          <Lock className="size-4" aria-hidden />
          <AlertTitle>This PDF is password protected</AlertTitle>
          <AlertDescription>
            Browsers and applicant tracking systems cannot open it without the password. Replace it with an unprotected copy
            (Print → Save as PDF).
          </AlertDescription>
        </Alert>
        <ExtractedText info={info} />
      </div>
    )
  }
  return (
    <div className="space-y-3">
      <Alert variant="info">
        <FileText className="size-4" aria-hidden />
        <AlertTitle>Browsers cannot preview Word files</AlertTitle>
        <AlertDescription className="flex flex-wrap items-center justify-between gap-2">
          <span>Below is the text we read from your DOCX. Download it to see the original layout.</span>
          <Button variant="outline" size="sm" onClick={() => void download(resume)}>
            <Download aria-hidden /> Download DOCX
          </Button>
        </AlertDescription>
      </Alert>
      <ExtractedText info={info} />
    </div>
  )
}

/* ------------------------------------------------------------------ replace */

function ReplaceFileDialog({ resume, open, onOpenChange }: { resume: UploadedResume; open: boolean; onOpenChange: (open: boolean) => void }) {
  const replace = useReplaceFile(resume.id)
  const picked = useCheckedFile()
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (!open) {
      void picked.setFile(null)
      setError(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && replace.isPending) replace.cancel()
        onOpenChange(next)
      }}
    >
      <DialogContent className="max-w-lg max-sm:bottom-0 max-sm:top-auto max-sm:translate-y-0 max-sm:rounded-t-3xl">
        <DialogHeader>
          <DialogTitle>Replace the original file</DialogTitle>
          <DialogDescription>
            The new file becomes version {resume.current_version + 1}. The current file stays with version {resume.current_version} in
            the history, so nothing is lost.
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (!picked.file || !picked.ok) return
            setError(null)
            replace
              .mutateAsync(picked.file)
              .then((updated) => {
                const summary = parseSummary(updated)
                toast.success('File replaced', { description: summary.text })
                onOpenChange(false)
              })
              .catch((err: unknown) => {
                if (isApiError(err) && err.code === 'aborted') return
                setError(errorMessage(err, 'Could not replace the file.'))
              })
          }}
        >
          {replace.isPending ? (
            <UploadProgressBar progress={replace.progress} fileName={picked.file?.name} />
          ) : (
            <ResumeDropzone id="replace-file" label="New file" file={picked.file} problem={picked.problem} onFile={(f) => void picked.setFile(f)} />
          )}
          {error ? (
            <p role="alert" className="rounded-lg bg-destructive-soft px-3 py-2 text-sm text-destructive-soft-foreground">
              {error}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {replace.isPending ? 'Cancel upload' : 'Cancel'}
            </Button>
            <Button type="submit" disabled={!picked.ok} loading={replace.isPending}>
              Replace file
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/* ------------------------------------------------------------------ facts */

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-2 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 truncate text-right font-medium tabular-nums">{children}</dd>
    </div>
  )
}

function FactsSkeleton() {
  return (
    <SkeletonRegion label="Loading file details" className="divide-y divide-border">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="flex items-center justify-between gap-3 py-2">
          <Skeleton className="h-3.5 w-20" />
          <Skeleton className="h-3.5 w-28" />
        </div>
      ))}
    </SkeletonRegion>
  )
}

/**
 * The uploaded-resume page body (`/resume/my/:id` when `kind === 'UPLOADED'`): the original
 * file inline (PDF) or its extracted text (DOCX), file facts, Download original, Replace
 * file and Set as default. The page header carries "Edit a copy in the editor".
 */
export function UploadedResumeView({
  resume,
  onSetDefault,
  busy,
}: {
  resume: UploadedResume
  onSetDefault: () => void
  busy?: boolean
}) {
  const info = useFileInfo(resume.id)
  const [replacing, setReplacing] = React.useState(false)
  const archived = Boolean(resume.archived_at)
  const summary = parseSummary(resume)
  const data = info.data

  return (
    <section aria-labelledby="original-file-title" className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]" data-uploaded-view>
      <div className="min-w-0 space-y-2">
        <h2 id="original-file-title" className="sr-only">
          Original file
        </h2>
        {info.isLoading ? (
          <PageSkeleton label="Loading your file" />
        ) : info.error || !data ? (
          <ErrorState title="Could not load the file details" error={info.error} onRetry={() => void info.refetch()} />
        ) : (
          <OriginalPreview resume={resume} info={data} />
        )}
      </div>

      <div className="space-y-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Original file</CardTitle>
            <CardDescription>Kept exactly as you uploaded it. Applications send this file.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {info.isLoading || !data ? (
              <FactsSkeleton />
            ) : (
              <dl className="divide-y divide-border" data-file-facts>
                <Fact label="File">
                  <span title={data.original_filename ?? undefined}>{data.original_filename ?? '—'}</span>
                </Fact>
                <Fact label="Type">{data.format ? data.format.toUpperCase() : '—'}</Fact>
                <Fact label="Size">{formatBytes(data.size_bytes)}</Fact>
                <Fact label="Pages">{data.page_count ?? 'Unknown'}</Fact>
                <Fact label="Uploaded">{formatDate(data.uploaded_at)}</Fact>
                {data.previous_files ? (
                  <Fact label="Earlier files">
                    <Link to={`/resume/history?resume=${resume.id}`} className="text-primary hover:underline">
                      {data.previous_files} in history
                    </Link>
                  </Fact>
                ) : null}
              </dl>
            )}
            <div className="grid gap-2">
              <Button variant="outline" onClick={() => void download(resume)} disabled={!data || data.file_missing}>
                <Download aria-hidden /> Download original
              </Button>
              <Button variant="outline" onClick={() => setReplacing(true)}>
                <RefreshCw aria-hidden /> Replace file
              </Button>
              {resume.is_default ? (
                <p className="flex items-center justify-center gap-1.5 py-1 text-sm text-muted-foreground">
                  <Star className="size-4 text-primary" aria-hidden /> Your default resume
                </p>
              ) : !archived ? (
                <Button variant="ghost" onClick={onSetDefault} loading={busy}>
                  <Star aria-hidden /> Set as default
                </Button>
              ) : null}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">What we read</CardTitle>
            <CardDescription>Used for scoring and tailoring. The file is not changed.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className={cn('flex items-start gap-2 text-sm', summary.ok ? '' : 'text-warning-soft-foreground')}>
              {summary.ok ? null : <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />}
              {summary.text}
            </p>
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline">v{resume.current_version}</Badge>
              <Button variant="link" size="sm" className="h-auto p-0" asChild>
                <Link to={`/resume/my/${resume.id}/edit`}>
                  <PencilLine aria-hidden /> Review what we extracted
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
      <ReplaceFileDialog resume={resume} open={replacing} onOpenChange={setReplacing} />
    </section>
  )
}
