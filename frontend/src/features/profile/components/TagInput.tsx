import { Plus, X } from 'lucide-react'
import * as React from 'react'

import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

export interface TagInputProps {
  id?: string
  value: string[]
  onChange: (next: string[]) => void
  placeholder?: string
  /** Rendered under the field as one-click "add this" chips (e.g. skills from the resume). */
  suggestions?: string[]
  suggestionsLabel?: string
  maxSuggestions?: number
  disabled?: boolean
  className?: string
  'aria-describedby'?: string
}

/**
 * Chip-style multi-value input. Enter or comma commits the draft, Backspace on an empty
 * draft removes the last chip, and duplicates (case-insensitive) are silently ignored.
 */
export function TagInput({
  id,
  value,
  onChange,
  placeholder = 'Type and press Enter',
  suggestions = [],
  suggestionsLabel = 'Suggestions',
  maxSuggestions = 12,
  disabled = false,
  className,
  'aria-describedby': describedBy,
}: TagInputProps) {
  const [draft, setDraft] = React.useState('')

  const add = React.useCallback(
    (raw: string) => {
      const parts = raw
        .split(',')
        .map((part) => part.trim())
        .filter(Boolean)
      if (parts.length === 0) return
      const seen = new Set(value.map((item) => item.toLowerCase()))
      const next = [...value]
      for (const part of parts) {
        if (seen.has(part.toLowerCase())) continue
        seen.add(part.toLowerCase())
        next.push(part)
      }
      if (next.length !== value.length) onChange(next)
    },
    [onChange, value],
  )

  const remove = (index: number) => onChange(value.filter((_, i) => i !== index))

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault()
      add(draft)
      setDraft('')
      return
    }
    if (event.key === 'Backspace' && draft === '' && value.length > 0) {
      event.preventDefault()
      remove(value.length - 1)
    }
  }

  const unusedSuggestions = React.useMemo(() => {
    const taken = new Set(value.map((item) => item.toLowerCase()))
    return suggestions.filter((item) => item && !taken.has(item.toLowerCase())).slice(0, maxSuggestions)
  }, [maxSuggestions, suggestions, value])

  return (
    <div className={cn('space-y-2', className)}>
      <div
        className={cn(
          'flex min-h-10 flex-wrap items-center gap-1.5 rounded-md border border-input bg-background p-1.5',
          'focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2 focus-within:ring-offset-background',
          disabled && 'pointer-events-none opacity-60',
        )}
      >
        {value.map((item, index) => (
          <Badge key={`${item}-${index}`} variant="secondary" className="gap-1 pr-1">
            <span className="max-w-[16rem] truncate">{item}</span>
            <button
              type="button"
              onClick={() => remove(index)}
              className="rounded-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              aria-label={`Remove ${item}`}
            >
              <X className="size-3" aria-hidden />
            </button>
          </Badge>
        ))}
        <Input
          id={id}
          value={draft}
          disabled={disabled}
          aria-describedby={describedBy}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={() => {
            if (draft.trim()) {
              add(draft)
              setDraft('')
            }
          }}
          placeholder={value.length === 0 ? placeholder : ''}
          className="h-7 min-w-[8rem] flex-1 border-0 bg-transparent px-1 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
        />
      </div>

      {unusedSuggestions.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-muted-foreground">{suggestionsLabel}:</span>
          {unusedSuggestions.map((item) => (
            <button
              key={item}
              type="button"
              disabled={disabled}
              onClick={() => add(item)}
              className="inline-flex items-center gap-1 rounded-full border border-dashed border-border px-2 py-0.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Plus className="size-3" aria-hidden />
              {item}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}
