import { Check, Pencil, X } from 'lucide-react'
import * as React from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

export interface InlineEditProps {
  value: string
  /** Accessible name of the field ("Resume name", "Company"). */
  label: string
  onSave: (next: string) => Promise<unknown> | unknown
  className?: string
  /** Classes of the read-only text. */
  textClassName?: string
  maxLength?: number
  saving?: boolean
}

/** Text with a pencil: click (or Enter on the button) to edit, Enter saves, Esc cancels. */
export function InlineEdit({ value, label, onSave, className, textClassName, maxLength = 255, saving = false }: InlineEditProps) {
  const [editing, setEditing] = React.useState(false)
  const [draft, setDraft] = React.useState(value)
  const inputRef = React.useRef<HTMLInputElement>(null)
  const buttonRef = React.useRef<HTMLButtonElement>(null)

  React.useEffect(() => {
    if (!editing) setDraft(value)
  }, [value, editing])
  React.useEffect(() => {
    if (editing) inputRef.current?.select()
  }, [editing])

  const close = () => {
    setEditing(false)
    window.requestAnimationFrame(() => buttonRef.current?.focus())
  }
  const save = async () => {
    const next = draft.trim()
    if (!next || next === value) return close()
    try {
      await onSave(next)
      close()
    } catch {
      inputRef.current?.focus() // the caller toasts the error; keep the draft
    }
  }

  if (editing) {
    return (
      <form
        className={cn('flex min-w-0 items-center gap-1.5', className)}
        onSubmit={(event) => {
          event.preventDefault()
          void save()
        }}
      >
        <Input
          ref={inputRef}
          value={draft}
          maxLength={maxLength}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              event.preventDefault()
              event.stopPropagation()
              close()
            }
          }}
          aria-label={label}
          className="h-8 min-w-0 flex-1"
        />
        <Button type="submit" size="icon-sm" variant="soft" aria-label={`Save ${label.toLowerCase()}`} loading={saving} disabled={!draft.trim()}>
          <Check />
        </Button>
        <Button type="button" size="icon-sm" variant="ghost" aria-label="Cancel" onClick={close}>
          <X />
        </Button>
      </form>
    )
  }
  return (
    <span className={cn('inline-flex min-w-0 max-w-full items-center gap-1', className)}>
      <span className={cn('min-w-0 truncate', textClassName)} title={value}>
        {value}
      </span>
      <Button
        ref={buttonRef}
        type="button"
        size="icon-sm"
        variant="ghost"
        className="size-7 shrink-0 text-muted-foreground hover:text-foreground"
        aria-label={`Rename: ${label}`}
        onClick={() => setEditing(true)}
      >
        <Pencil className="size-3.5" />
      </Button>
    </span>
  )
}
