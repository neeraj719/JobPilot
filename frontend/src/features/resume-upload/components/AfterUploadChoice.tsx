import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { cn } from '@/lib/utils'

import type { AfterUpload } from '../types'

const OPTIONS: { value: AfterUpload; title: string; description: string }[] = [
  {
    value: 'original',
    title: 'Keep as my original — use this file as-is',
    description: 'Applications send this exact file. We also read it so scoring and tailoring work.',
  },
  {
    value: 'editor',
    title: 'Open in the editor to review what we extracted',
    description: 'Check the sections we read from the file. The file itself is kept unchanged.',
  },
]

export function AfterUploadChoice({
  id,
  value,
  onChange,
  disabled,
}: {
  id: string
  value: AfterUpload
  onChange: (value: AfterUpload) => void
  disabled?: boolean
}) {
  return (
    <fieldset className="space-y-2" disabled={disabled}>
      <legend id={`${id}-legend`} className="mb-2 text-sm font-medium">
        After upload
      </legend>
      <RadioGroup value={value} onValueChange={(v) => onChange(v as AfterUpload)} aria-labelledby={`${id}-legend`} className="gap-2">
        {OPTIONS.map((option) => {
          const itemId = `${id}-${option.value}`
          return (
            <label
              key={option.value}
              htmlFor={itemId}
              className={cn(
                'flex cursor-pointer items-start gap-3 rounded-xl border p-3 transition-colors',
                value === option.value ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/40',
              )}
            >
              <RadioGroupItem id={itemId} value={option.value} className="mt-0.5" aria-describedby={`${itemId}-desc`} />
              <span className="min-w-0">
                <span className="block text-sm font-medium">{option.title}</span>
                <span id={`${itemId}-desc`} className="block text-xs text-muted-foreground">
                  {option.description}
                </span>
              </span>
            </label>
          )
        })}
      </RadioGroup>
    </fieldset>
  )
}
