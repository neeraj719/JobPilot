import { Ban, Info, RotateCcw, Save, Star, X } from 'lucide-react'
import * as React from 'react'

import { ErrorState } from '@/components/common/ErrorState'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { toast } from '@/components/ui/toaster'
import { errorMessage } from '@/lib/api'
import { PRIORITY_LABELS, cn } from '@/lib/utils'
import { CompanyAutocomplete } from '@/features/companies/components/CompanyAutocomplete'
import { useCompanyPreferences, useReplaceCompanyPreferences } from '@/features/companies/api'
import { COMPANY_PRIORITIES, type CompanyPreferenceUpsert, type CompanyPriority } from '@/types/api'
import { PriorityBoardSkeleton } from '@/features/companies/components/CompaniesSkeletons'

interface BoardEntry extends CompanyPreferenceUpsert {
  /** Stable key for React; preference ids disappear on unsaved rows. */
  key: string
}

const COLUMNS: { priority: CompanyPriority; blurb: string; accent: string }[] = [
  { priority: 'P1', blurb: 'Apply to everything that fits.', accent: 'border-primary/40' },
  { priority: 'P2', blurb: 'Worth applying when the role is right.', accent: 'border-info/40' },
  { priority: 'P3', blurb: 'Only for a clear step up.', accent: 'border-border' },
  { priority: 'AVOID', blurb: 'Never queued, never applied to.', accent: 'border-destructive/40' },
]

let keyCounter = 0
const nextKey = () => `entry-${(keyCounter += 1)}`

function sameList(a: BoardEntry[], b: BoardEntry[]): boolean {
  if (a.length !== b.length) return false
  return a.every((entry, index) => {
    const other = b[index]
    return (
      other !== undefined &&
      entry.company_name === other.company_name &&
      entry.priority === other.priority &&
      (entry.notes ?? '') === (other.notes ?? '')
    )
  })
}

export function PriorityBoard() {
  const preferencesQuery = useCompanyPreferences()
  const replace = useReplaceCompanyPreferences()

  const serverEntries = React.useMemo<BoardEntry[]>(
    () =>
      (preferencesQuery.data ?? []).map((preference) => ({
        key: preference.id,
        company_name: preference.company_name,
        priority: preference.priority,
        notes: preference.notes ?? '',
      })),
    [preferencesQuery.data],
  )

  const [entries, setEntries] = React.useState<BoardEntry[]>(serverEntries)

  React.useEffect(() => {
    setEntries(serverEntries)
  }, [serverEntries])

  const dirty = !sameList(entries, serverEntries)

  const add = (name: string, priority: CompanyPriority) => {
    setEntries((current) => [...current, { key: nextKey(), company_name: name, priority, notes: '' }])
  }

  const update = (key: string, patch: Partial<BoardEntry>) => {
    setEntries((current) => current.map((entry) => (entry.key === key ? { ...entry, ...patch } : entry)))
  }

  const remove = (key: string) => setEntries((current) => current.filter((entry) => entry.key !== key))

  const save = async () => {
    try {
      await replace.mutateAsync(
        entries.map(({ company_name, priority, notes }) => ({
          company_name,
          priority,
          notes: notes?.trim() ? notes.trim() : null,
        })),
      )
      toast.success('Company priorities saved', {
        description: 'Your queue will be reordered on the next automation run.',
      })
    } catch (error) {
      toast.error('Could not save company priorities', { description: errorMessage(error) })
    }
  }

  if (preferencesQuery.isLoading) return <PriorityBoardSkeleton />
  if (preferencesQuery.error) {
    return (
      <ErrorState
        error={preferencesQuery.error}
        title="Could not load your company priorities"
        onRetry={() => void preferencesQuery.refetch()}
      />
    )
  }

  return (
    <div className="space-y-4">
      <Alert variant="info">
        <Info aria-hidden />
        <AlertDescription>
          Priority only orders your queue; it never inflates match scores. <strong>Avoid</strong> companies are skipped
          entirely.
        </AlertDescription>
      </Alert>

      <Card>
        <CardContent className="py-4">
          <CompanyAutocomplete
            existingNames={entries.map((entry) => entry.company_name)}
            onAdd={add}
            disabled={replace.isPending}
          />
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {COLUMNS.map((column) => {
          const columnEntries = entries.filter((entry) => entry.priority === column.priority)
          return (
            <Card key={column.priority} className={cn('border-t-4', column.accent)}>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center justify-between gap-2 text-sm">
                  <span className="flex items-center gap-1.5">
                    {column.priority === 'P1' ? <Star className="size-3.5 fill-current text-primary" aria-hidden /> : null}
                    {column.priority === 'AVOID' ? <Ban className="size-3.5 text-destructive" aria-hidden /> : null}
                    {PRIORITY_LABELS[column.priority]}
                  </span>
                  <span className="text-xs font-normal tabular-nums text-muted-foreground">{columnEntries.length}</span>
                </CardTitle>
                <p className="text-xs text-muted-foreground">{column.blurb}</p>
              </CardHeader>
              <CardContent className="space-y-2">
                {columnEntries.length === 0 ? (
                  <p className="rounded-md border border-dashed border-border px-2 py-3 text-center text-xs text-muted-foreground">
                    Nothing here yet
                  </p>
                ) : (
                  columnEntries.map((entry) => (
                    <div key={entry.key} className="space-y-2 rounded-md border border-border bg-muted/20 p-2">
                      <div className="flex items-start justify-between gap-1">
                        <span className="min-w-0 flex-1 truncate text-sm font-medium" title={entry.company_name}>
                          {entry.company_name}
                        </span>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          aria-label={`Remove ${entry.company_name}`}
                          onClick={() => remove(entry.key)}
                          className="text-muted-foreground hover:text-destructive"
                        >
                          <X aria-hidden />
                        </Button>
                      </div>

                      <Input
                        value={entry.notes ?? ''}
                        onChange={(event) => update(entry.key, { notes: event.target.value })}
                        placeholder="Note (optional)"
                        aria-label={`Note for ${entry.company_name}`}
                        className="h-8 text-xs"
                      />

                      <Select
                        value={entry.priority}
                        onValueChange={(value) => update(entry.key, { priority: value as CompanyPriority })}
                      >
                        <SelectTrigger className="h-8 text-xs" aria-label={`Priority for ${entry.company_name}`}>
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
                  ))
                )}
              </CardContent>
            </Card>
          )
        })}
      </div>

      <div className="flex flex-wrap items-center justify-end gap-2">
        {dirty ? <span className="mr-auto text-xs text-warning">Unsaved changes</span> : null}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setEntries(serverEntries)}
          disabled={!dirty || replace.isPending}
        >
          <RotateCcw aria-hidden />
          Discard
        </Button>
        <Button type="button" onClick={() => void save()} loading={replace.isPending} disabled={!dirty}>
          <Save aria-hidden />
          Save priorities
        </Button>
      </div>
    </div>
  )
}
