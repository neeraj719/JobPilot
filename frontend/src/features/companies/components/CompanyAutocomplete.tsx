import { Plus } from 'lucide-react'
import * as React from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useDebounce } from '@/hooks/useDebounce'
import { PRIORITY_LABELS } from '@/lib/utils'
import { useCompanySuggestions } from '@/features/companies/api'
import { COMPANY_PRIORITIES, type CompanyPriority } from '@/types/api'

export interface CompanyAutocompleteProps {
  /** Names already on the board — used to grey out duplicates. */
  existingNames: string[]
  onAdd: (name: string, priority: CompanyPriority) => void
  disabled?: boolean
}

/** Name + priority input with live suggestions from `GET /companies?q=`. */
export function CompanyAutocomplete({ existingNames, onAdd, disabled = false }: CompanyAutocompleteProps) {
  const [name, setName] = React.useState('')
  const [priority, setPriority] = React.useState<CompanyPriority>('P1')
  const [open, setOpen] = React.useState(false)
  const debounced = useDebounce(name, 250)
  const suggestions = useCompanySuggestions(debounced)

  const taken = React.useMemo(
    () => new Set(existingNames.map((item) => item.trim().toLowerCase())),
    [existingNames],
  )

  const options = (suggestions.data?.items ?? []).filter((company) => !taken.has(company.name.trim().toLowerCase()))

  const submit = (value: string) => {
    const trimmed = value.trim()
    if (!trimmed) return
    if (taken.has(trimmed.toLowerCase())) return
    onAdd(trimmed, priority)
    setName('')
    setOpen(false)
  }

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
      <div className="relative flex-1 space-y-1.5">
        <Label htmlFor="company-add-name">Add a company</Label>
        <Input
          id="company-add-name"
          value={name}
          disabled={disabled}
          autoComplete="off"
          placeholder="Start typing, e.g. Google"
          onChange={(event) => {
            setName(event.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 120)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              submit(name)
            }
            if (event.key === 'Escape') setOpen(false)
          }}
          aria-expanded={open && options.length > 0}
          aria-controls="company-suggestions"
        />
        {open && options.length > 0 ? (
          <ul
            id="company-suggestions"
            className="absolute z-20 mt-1 max-h-60 w-full overflow-auto rounded-md border border-border bg-popover p-1 shadow-md"
          >
            {options.map((company) => (
              <li key={company.id}>
                <button
                  type="button"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => submit(company.name)}
                  className="flex w-full items-center justify-between gap-2 rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground focus-visible:bg-accent focus-visible:outline-none"
                >
                  <span className="truncate">{company.name}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {company.open_jobs} open {company.open_jobs === 1 ? 'job' : 'jobs'}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      <div className="space-y-1.5 sm:w-44">
        <Label htmlFor="company-add-priority">Priority</Label>
        <Select value={priority} onValueChange={(value) => setPriority(value as CompanyPriority)} disabled={disabled}>
          <SelectTrigger id="company-add-priority">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {COMPANY_PRIORITIES.map((value) => (
              <SelectItem key={value} value={value}>
                {PRIORITY_LABELS[value]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Button type="button" onClick={() => submit(name)} disabled={disabled || name.trim() === ''}>
        <Plus aria-hidden />
        Add
      </Button>
    </div>
  )
}
