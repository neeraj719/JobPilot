import { AlertCircle, FileText, FileUp, X } from 'lucide-react'
import * as React from 'react'

import { Button } from '@/components/ui/button'
import { MAX_RESUME_BYTES, formatBytes } from '@/features/resume/api'
import { cn } from '@/lib/utils'

import { RESUME_ACCEPT, checkResumeFile, type FileProblem } from '../validation'

/** A picked/dropped resume file plus the result of the client-side checks. */
export function useCheckedFile(initial: File | null = null) {
  const [file, setFileState] = React.useState<File | null>(null)
  const [problem, setProblem] = React.useState<FileProblem | null>(null)
  const [checking, setChecking] = React.useState(false)
  const token = React.useRef(0)

  const setFile = React.useCallback(async (next: File | null) => {
    const mine = ++token.current
    setFileState(next)
    setProblem(null)
    if (!next) return
    setChecking(true)
    const found = await checkResumeFile(next)
    if (mine !== token.current) return
    setProblem(found)
    setChecking(false)
  }, [])

  React.useEffect(() => {
    if (initial) void setFile(initial)
  }, [initial, setFile])

  return { file, problem, checking, setFile, ok: Boolean(file) && !problem && !checking }
}

export interface ResumeDropzoneProps {
  id: string
  file: File | null
  problem: FileProblem | null
  onFile: (file: File | null) => void
  disabled?: boolean
  className?: string
  /** Visible label above the zone. */
  label?: string
}

/**
 * Focusable drop target for one PDF/DOCX: click, Enter or Space opens the file picker; a
 * dragged file highlights it. Errors (type, size, protected PDF) are announced.
 */
export function ResumeDropzone({ id, file, problem, onFile, disabled, className, label = 'Resume file' }: ResumeDropzoneProps) {
  const input = React.useRef<HTMLInputElement>(null)
  const [over, setOver] = React.useState(false)
  const hintId = `${id}-hint`
  const errorId = `${id}-error`

  const open = () => {
    if (!disabled) input.current?.click()
  }

  return (
    <div className={cn('space-y-2', className)}>
      <p id={`${id}-label`} className="text-sm font-medium">
        {label}
      </p>
      {file ? (
        <div
          className={cn(
            'flex items-center gap-3 rounded-xl border bg-surface-2 p-3',
            problem ? 'border-destructive/50' : 'border-border',
          )}
        >
          <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <FileText className="size-5" aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium" title={file.name}>
              {file.name}
            </p>
            <p className="text-xs tabular-nums text-muted-foreground">{formatBytes(file.size)}</p>
          </div>
          <Button type="button" variant="ghost" size="sm" onClick={open} disabled={disabled}>
            Change
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={`Remove ${file.name}`}
            onClick={() => {
              if (input.current) input.current.value = ''
              onFile(null)
            }}
            disabled={disabled}
          >
            <X aria-hidden />
          </Button>
        </div>
      ) : (
        <div
          id={id}
          role="button"
          tabIndex={disabled ? -1 : 0}
          aria-labelledby={`${id}-label`}
          aria-describedby={problem ? `${hintId} ${errorId}` : hintId}
          aria-disabled={disabled || undefined}
          data-dropzone
          onClick={open}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault()
              open()
            }
          }}
          onDragEnter={(event) => {
            event.preventDefault()
            event.stopPropagation()
            if (!disabled) setOver(true)
          }}
          onDragOver={(event) => {
            event.preventDefault()
            event.stopPropagation()
            event.dataTransfer.dropEffect = disabled ? 'none' : 'copy'
          }}
          onDragLeave={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOver(false)
          }}
          onDrop={(event) => {
            event.preventDefault()
            event.stopPropagation()
            setOver(false)
            const dropped = event.dataTransfer.files?.[0]
            if (dropped && !disabled) onFile(dropped)
          }}
          className={cn(
            'flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
            over ? 'border-primary bg-primary/10' : problem ? 'border-destructive/60 bg-surface-2' : 'border-input/60 bg-surface-2 hover:border-primary/60 hover:bg-primary/5',
            disabled && 'cursor-not-allowed opacity-60',
          )}
        >
          <span className="flex size-11 items-center justify-center rounded-full bg-primary/10 text-primary">
            <FileUp className="size-5" aria-hidden />
          </span>
          <span className="text-sm font-medium">
            {over ? 'Drop it here' : (
              <>
                Drag your resume here, or <span className="text-primary underline underline-offset-4">choose a file</span>
              </>
            )}
          </span>
          <span id={hintId} className="text-xs text-muted-foreground">
            PDF or DOCX, up to {formatBytes(MAX_RESUME_BYTES)}
          </span>
        </div>
      )}
      <input
        ref={input}
        type="file"
        accept={RESUME_ACCEPT}
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        data-testid={`${id}-input`}
        onChange={(event) => {
          const picked = event.target.files?.[0] ?? null
          if (picked) onFile(picked)
          event.target.value = ''
        }}
      />
      {problem ? (
        <p id={errorId} role="alert" className="flex items-start gap-2 rounded-lg bg-destructive-soft px-3 py-2 text-sm text-destructive-soft-foreground">
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>{problem.message}</span>
        </p>
      ) : null}
    </div>
  )
}
