import { FileUp, Upload, X } from 'lucide-react'
import * as React from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { toast } from '@/components/ui/toaster'
import { errorMessage } from '@/lib/api'
import { cn } from '@/lib/utils'
import { ACCEPTED_RESUME_TYPES, MAX_RESUME_BYTES, formatBytes, useUploadResume } from '@/features/resume/api'
import { TargetRoleSelect } from '@/features/resume/components/TargetRoleSelect'

export interface ResumeUploadCardProps {
  /** True when the account has no resume yet — the copy changes to a first-run nudge. */
  isFirstResume: boolean
  onUploaded?: (resumeId: string) => void
}

const ACCEPT_ATTR = '.pdf,.docx,.doc,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document'

function looksLikeResume(file: File): boolean {
  if ((ACCEPTED_RESUME_TYPES as readonly string[]).includes(file.type)) return true
  return /\.(pdf|docx|doc)$/i.test(file.name)
}

export function ResumeUploadCard({ isFirstResume, onUploaded }: ResumeUploadCardProps) {
  const upload = useUploadResume()
  const inputRef = React.useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = React.useState(false)
  const [file, setFile] = React.useState<File | null>(null)
  const [name, setName] = React.useState('')
  const [targetRole, setTargetRole] = React.useState('')
  // `null` = untouched, so the box follows `isFirstResume` as the resume list loads
  // instead of freezing the value it had on the very first render.
  const [defaultChoice, setDefaultChoice] = React.useState<boolean | null>(null)
  const setDefault = defaultChoice ?? isFirstResume

  const accept = React.useCallback((candidate: File | null | undefined) => {
    if (!candidate) return
    if (!looksLikeResume(candidate)) {
      toast.error('Unsupported file type', { description: 'Upload a PDF or DOCX resume.' })
      return
    }
    if (candidate.size > MAX_RESUME_BYTES) {
      toast.error('File is too large', { description: `Maximum size is ${formatBytes(MAX_RESUME_BYTES)}.` })
      return
    }
    setFile(candidate)
    setName((current) => current || candidate.name.replace(/\.[^.]+$/, ''))
  }, [])

  const reset = () => {
    setFile(null)
    setName('')
    setTargetRole('')
    setDefaultChoice(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!file) {
      toast.error('Choose a file first')
      return
    }
    try {
      const resume = await upload.mutateAsync({
        file,
        name: name.trim() || undefined,
        targetRole: targetRole.trim() || undefined,
        setDefault,
      })
      toast.success('Resume uploaded', {
        description:
          resume.parse_status === 'PARSED'
            ? 'Extraction finished — review the details below.'
            : 'Extraction did not finish; you can edit the details by hand.',
      })
      reset()
      onUploaded?.(resume.id)
    } catch (error) {
      toast.error('Upload failed', { description: errorMessage(error) })
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Upload a resume</CardTitle>
        <CardDescription>
          PDF or DOCX, up to {formatBytes(MAX_RESUME_BYTES)}. It is parsed on upload so applications can be answered
          from it.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-4">
          <div
            role="button"
            tabIndex={0}
            aria-label="Choose a resume file"
            onClick={() => inputRef.current?.click()}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                inputRef.current?.click()
              }
            }}
            onDragOver={(event) => {
              event.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault()
              setDragging(false)
              accept(event.dataTransfer.files?.[0])
            }}
            className={cn(
              'flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-8 text-center transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
              dragging ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/40 hover:bg-muted/40',
            )}
          >
            <FileUp className="size-6 text-muted-foreground" aria-hidden />
            <p className="text-sm font-medium">
              {file ? file.name : 'Drag a file here, or click to browse'}
            </p>
            <p className="text-xs text-muted-foreground">
              {file ? formatBytes(file.size) : 'PDF or DOCX'}
            </p>
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT_ATTR}
              className="sr-only"
              onChange={(event) => accept(event.target.files?.[0])}
            />
          </div>

          {file ? (
            <div className="flex items-center justify-between rounded-md border border-border bg-muted/30 px-3 py-2 text-sm">
              <span className="truncate">{file.name}</span>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                onClick={reset}
                aria-label="Clear selected file"
                disabled={upload.isPending}
              >
                <X aria-hidden />
              </Button>
            </div>
          ) : null}

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="resume-name">Name</Label>
              <Input
                id="resume-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Software Engineer — Full Stack"
                disabled={upload.isPending}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="resume-target-role">Target role</Label>
              <TargetRoleSelect
                id="resume-target-role"
                value={targetRole}
                onChange={(role) => setTargetRole(role ?? '')}
                disabled={upload.isPending}
              />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="resume-set-default"
              checked={setDefault}
              onCheckedChange={(checked) => setDefaultChoice(checked === true)}
              disabled={upload.isPending || isFirstResume}
            />
            <Label htmlFor="resume-set-default" className="font-normal">
              Use this as my default resume
              {isFirstResume ? <span className="ml-1 text-muted-foreground">(your first resume always is)</span> : null}
            </Label>
          </div>

          {upload.isPending ? (
            <div className="space-y-1.5" aria-live="polite">
              <Progress value={70} className="h-1.5" indicatorClassName="animate-pulse" />
              <p className="text-xs text-muted-foreground">Uploading and extracting…</p>
            </div>
          ) : null}

          <div className="flex justify-end">
            <Button type="submit" loading={upload.isPending} disabled={!file}>
              <Upload aria-hidden />
              Upload resume
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}
