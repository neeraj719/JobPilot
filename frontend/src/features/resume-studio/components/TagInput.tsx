import { X } from 'lucide-react'
import * as React from 'react'

import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

export interface TagInputProps {
  id?: string
  value: string[]
  onChange: (next: string[]) => void
  placeholder?: string
  /** Accessible name of the text box. */
  label: string
  className?: string
}

/** Chips with a text box: Enter or comma adds, Backspace on empty removes the last one. */
export function TagInput({ id, value, onChange, placeholder, label, className }: TagInputProps) {
  const [draft, setDraft] = React.useState('')

  const add = (raw: string) => {
    const items = raw
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
    if (!items.length) return
    const seen = new Set(value.map((v) => v.toLowerCase()))
    const next = [...value]
    for (const item of items) {
      if (!seen.has(item.toLowerCase())) {
        next.push(item)
        seen.add(item.toLowerCase())
      }
    }
    onChange(next)
    setDraft('')
  }

  return (
    <div className={cn('rounded-md border border-input bg-background p-1.5 focus-within:ring-2 focus-within:ring-ring', className)}>
      <ul className="flex flex-wrap gap-1.5" aria-label={label}>
        {value.map((item, index) => (
          <li key={`${item}-${index}`} className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 text-xs">
            {item}
            <button
              type="button"
              className="rounded-sm text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label={`Remove ${item}`}
              onClick={() => onChange(value.filter((_, i) => i !== index))}
            >
              <X className="size-3" aria-hidden />
            </button>
          </li>
        ))}
        <li className="min-w-[8rem] flex-1">
          <Input
            id={id}
            aria-label={label}
            value={draft}
            placeholder={value.length ? '' : placeholder}
            className="h-7 border-0 px-1 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
            onChange={(event) => {
              const next = event.target.value
              if (next.includes(',')) add(next)
              else setDraft(next)
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                add(draft)
              } else if (event.key === 'Backspace' && !draft && value.length) {
                onChange(value.slice(0, -1))
              }
            }}
            onBlur={() => add(draft)}
          />
        </li>
      </ul>
    </div>
  )
}
