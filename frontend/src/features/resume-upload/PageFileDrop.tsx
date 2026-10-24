import { FileUp } from 'lucide-react'
import * as React from 'react'

function carriesFiles(event: DragEvent): boolean {
  return Array.from(event.dataTransfer?.types ?? []).includes('Files')
}

/**
 * Drag a file anywhere on the page: a full-page overlay with the dashed brand border
 * appears, and dropping hands the file to `onFile` (the upload sheet opens with it). Esc or
 * leaving the window cancels. Dropping a file never makes the browser navigate away to it.
 */
export function PageFileDrop({ onFile, disabled = false }: { onFile: (file: File) => void; disabled?: boolean }) {
  const [active, setActive] = React.useState(false)
  const depth = React.useRef(0)
  const cancelled = React.useRef(false)
  const onFileRef = React.useRef(onFile)
  onFileRef.current = onFile

  React.useEffect(() => {
    const reset = () => {
      depth.current = 0
      setActive(false)
    }
    const onEnter = (event: DragEvent) => {
      if (!carriesFiles(event)) return
      event.preventDefault()
      // Entering from outside the window: start counting afresh (a drop handled by an inner
      // dropzone never reaches this listener, so the counter can be stale).
      if (event.relatedTarget === null) depth.current = 0
      depth.current += 1
      if (depth.current === 1) cancelled.current = false
      if (!disabled && !cancelled.current) setActive(true)
    }
    const onOver = (event: DragEvent) => {
      if (!carriesFiles(event)) return
      event.preventDefault()
      if (event.dataTransfer) event.dataTransfer.dropEffect = disabled || cancelled.current ? 'none' : 'copy'
    }
    const onLeave = (event: DragEvent) => {
      if (!carriesFiles(event)) return
      depth.current = Math.max(0, depth.current - 1)
      if (depth.current === 0) setActive(false)
    }
    const onDrop = (event: DragEvent) => {
      if (!carriesFiles(event)) return
      event.preventDefault()
      const file = event.dataTransfer?.files?.[0]
      const wasCancelled = cancelled.current
      reset()
      cancelled.current = false
      if (file && !disabled && !wasCancelled) onFileRef.current(file)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && depth.current > 0) {
        cancelled.current = true
        setActive(false)
      }
    }
    window.addEventListener('dragenter', onEnter)
    window.addEventListener('dragover', onOver)
    window.addEventListener('dragleave', onLeave)
    window.addEventListener('drop', onDrop)
    window.addEventListener('dragend', reset)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('dragenter', onEnter)
      window.removeEventListener('dragover', onOver)
      window.removeEventListener('dragleave', onLeave)
      window.removeEventListener('drop', onDrop)
      window.removeEventListener('dragend', reset)
      window.removeEventListener('keydown', onKey)
    }
  }, [disabled])

  if (!active) return null
  return (
    <div
      role="dialog"
      aria-modal="false"
      aria-label="Drop your resume to upload it"
      data-drop-overlay
      className="pointer-events-none fixed inset-0 z-[60] flex items-center justify-center bg-overlay/35 p-4 backdrop-blur-sm motion-safe:animate-in motion-safe:fade-in-0 dark:bg-overlay/55"
    >
      <div className="flex h-full w-full flex-col items-center justify-center gap-3 rounded-3xl border-[3px] border-dashed border-primary bg-card/90 p-6 text-center shadow-xl">
        <span className="flex size-16 items-center justify-center rounded-full bg-gradient-brand text-gradient-foreground shadow-glow">
          <FileUp className="size-7" aria-hidden />
        </span>
        <p className="font-display text-2xl font-semibold tracking-tight">Drop your resume to upload it</p>
        <p className="max-w-md text-sm text-muted-foreground">
          PDF or DOCX. It is kept as your original file — you choose the name and what happens next. Press Esc to cancel.
        </p>
      </div>
    </div>
  )
}
