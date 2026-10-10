import { useQueries } from '@tanstack/react-query'
import { Building2, Check, Search } from 'lucide-react'
import * as React from 'react'

import { StatusBadge } from '@/components/common/StatusBadge'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { useDebounce } from '@/hooks/useDebounce'
import { cn } from '@/lib/utils'
import { applicationOptionsQuery } from '@/features/emails/api'
import type { ApplicationRead, ApplicationStatus, UUID } from '@/types/api'

export interface ApplicationPickerProps {
  value: UUID | null
  onChange: (applicationId: UUID, application: ApplicationRead) => void
  /** Restrict to these statuses — one query per status, merged and de-duplicated. */
  statuses?: ApplicationStatus[]
  /** Rendered above the search box. */
  label?: string
  disabled?: boolean
  className?: string
  emptyHint?: string
}

/**
 * Searchable list of the user's applications — used to link an email to one and to pick
 * the application an interview belongs to. Shared by the emails and interviews pages.
 *
 * `/applications` only filters by a single status, and the default `recent` sort puts
 * freshly queued rows first, so filtering one page client-side would hide older
 * interview-stage applications. Each requested status therefore gets its own query.
 */
export function ApplicationPicker({
  value,
  onChange,
  statuses,
  label = 'Application',
  disabled = false,
  className,
  emptyHint = 'No applications match that search.',
}: ApplicationPickerProps) {
  const [search, setSearch] = React.useState('')
  const debouncedSearch = useDebounce(search, 300)
  const searchId = React.useId()

  const statusList: (ApplicationStatus | undefined)[] = statuses?.length ? statuses : [undefined]
  const results = useQueries({
    queries: statusList.map((status) =>
      applicationOptionsQuery({ q: debouncedSearch || undefined, status, page_size: 50 }),
    ),
  })

  const isLoading = results.some((result) => result.isLoading)
  const isError = results.length > 0 && results.every((result) => result.isError)
  const partialFailure = !isError && results.some((result) => result.isError)

  const applications = React.useMemo(() => {
    const byId = new Map<UUID, ApplicationRead>()
    for (const result of results) {
      for (const application of result.data?.items ?? []) byId.set(application.id, application)
    }
    return [...byId.values()].sort((a, b) =>
      (a.company_name ?? '').localeCompare(b.company_name ?? '') ||
      (a.job_title ?? '').localeCompare(b.job_title ?? ''),
    )
    // `results` is a fresh array each render; the data identities are what matter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [results.map((result) => result.dataUpdatedAt).join('|')])

  return (
    <div className={cn('space-y-2', className)}>
      <label htmlFor={searchId} className="text-sm font-medium">
        {label}
      </label>
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <Input
          id={searchId}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search by company or role…"
          className="pl-8"
          disabled={disabled}
        />
      </div>

      <div className="max-h-64 overflow-y-auto rounded-md border border-border">
        {isLoading ? (
          <div className="space-y-2 p-3">
            {Array.from({ length: 4 }, (_, index) => (
              <Skeleton key={index} className="h-9 w-full" />
            ))}
          </div>
        ) : isError ? (
          <p className="p-4 text-sm text-destructive">Could not load your applications.</p>
        ) : applications.length === 0 ? (
          <p className="p-4 text-sm text-muted-foreground">{emptyHint}</p>
        ) : (
          <ul role="listbox" aria-label="Applications">
            {applications.map((application) => {
              const selected = application.id === value
              return (
                <li key={application.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={selected}
                    disabled={disabled}
                    onClick={() => onChange(application.id, application)}
                    className={cn(
                      'flex w-full items-center gap-3 border-b border-border/60 px-3 py-2 text-left transition-colors last:border-b-0',
                      'hover:bg-accent focus-visible:bg-accent focus-visible:outline-none',
                      selected && 'bg-primary/5',
                    )}
                  >
                    <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
                      {selected ? (
                        <Check className="size-4 text-primary" aria-hidden />
                      ) : (
                        <Building2 className="size-3.5" aria-hidden />
                      )}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">
                        {application.company_name ?? 'Unknown company'}
                      </span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {application.job_title ?? 'Unknown role'}
                      </span>
                    </span>
                    <StatusBadge status={application.status} className="shrink-0" />
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      {partialFailure ? (
        <p className="text-xs text-warning">Some applications could not be loaded — the list may be incomplete.</p>
      ) : null}
    </div>
  )
}
