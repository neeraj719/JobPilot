import { FilterX, SlidersHorizontal } from 'lucide-react'
import * as React from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Slider } from '@/components/ui/slider'
import {
  APPLICATION_STATUS_LABELS,
  PRIORITY_LABELS,
  WORK_MODE_LABELS,
  cn,
  formatNumber,
  sourceLabel,
} from '@/lib/utils'
import {
  COMMON_LOCATIONS,
  POSTED_WITHIN_OPTIONS,
  type JobFiltersState,
} from '@/features/jobs/filters'
import { APPLICATION_STATUSES, COMPANY_PRIORITIES, WORK_MODES, type AdapterInfo } from '@/types/api'

/** Radix Select has no "empty" value, so the placeholder option uses this sentinel. */
const ANY = '__any__'

export interface JobFiltersProps {
  filters: JobFiltersState
  setFilter: <K extends keyof JobFiltersState>(key: K, value: JobFiltersState[K]) => void
  reset: () => void
  activeCount: number
  sources: AdapterInfo[] | undefined
  className?: string
}

function FilterBlock({ label, htmlFor, children }: { label: string; htmlFor?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={htmlFor} className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </Label>
      {children}
    </div>
  )
}

/**
 * The jobs filter rail. Collapsed behind a toggle below `lg`, always visible above it.
 * Every control writes straight through to the URL-synced state.
 */
export function JobFilters({ filters, setFilter, reset, activeCount, sources, className }: JobFiltersProps) {
  const [open, setOpen] = React.useState(false)
  // The slider is dragged continuously; commit to the URL only when the user lets go.
  const [scoreDraft, setScoreDraft] = React.useState(filters.min_score)
  React.useEffect(() => setScoreDraft(filters.min_score), [filters.min_score])

  const sourceOptions = (sources ?? []).filter((source) => (source.job_count ?? 0) > 0)

  return (
    <section className={cn('space-y-3', className)} aria-label="Job filters">
      <div className="flex items-center justify-between gap-2 lg:hidden">
        <Button variant="outline" size="sm" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
          <SlidersHorizontal />
          Filters
          {activeCount > 0 ? (
            <Badge variant="secondary" className="ml-1 px-1.5 py-0">
              {activeCount}
            </Badge>
          ) : null}
        </Button>
        {activeCount > 0 ? (
          <Button variant="ghost" size="sm" onClick={reset}>
            <FilterX />
            Clear
          </Button>
        ) : null}
      </div>

      <div
        className={cn(
          'space-y-5 rounded-lg border border-border bg-card p-4',
          open ? 'block' : 'hidden',
          'lg:block',
        )}
      >
        <div className="hidden items-center justify-between lg:flex">
          <h2 className="text-sm font-semibold">Filters</h2>
          {activeCount > 0 ? (
            <Button variant="ghost" size="sm" onClick={reset}>
              <FilterX />
              Clear all
            </Button>
          ) : null}
        </div>

        <FilterBlock label={`Minimum match — ${scoreDraft}%`} htmlFor="filter-min-score">
          <Slider
            id="filter-min-score"
            min={0}
            max={100}
            step={5}
            value={[scoreDraft]}
            onValueChange={(value) => setScoreDraft(value[0] ?? 0)}
            onValueCommit={(value) => setFilter('min_score', value[0] ?? 0)}
            aria-label="Minimum match score"
          />
        </FilterBlock>

        <FilterBlock label="Minimum salary (₹ per year)" htmlFor="filter-salary">
          <Input
            id="filter-salary"
            type="number"
            inputMode="numeric"
            min={0}
            step={100000}
            placeholder="e.g. 1200000"
            value={filters.salary_min}
            onChange={(event) => setFilter('salary_min', event.target.value)}
          />
          {filters.salary_min ? (
            <p className="text-[11px] text-muted-foreground">≈ ₹{formatNumber(Number(filters.salary_min))} per year</p>
          ) : null}
        </FilterBlock>

        <FilterBlock label="Location" htmlFor="filter-location">
          <Input
            id="filter-location"
            list="jobpilot-locations"
            placeholder="Any location"
            value={filters.location}
            onChange={(event) => setFilter('location', event.target.value)}
          />
          <datalist id="jobpilot-locations">
            {COMMON_LOCATIONS.map((location) => (
              <option key={location} value={location} />
            ))}
          </datalist>
        </FilterBlock>

        <FilterBlock label="Work mode">
          <Select
            value={filters.work_mode || ANY}
            onValueChange={(value) => setFilter('work_mode', value === ANY ? '' : (value as JobFiltersState['work_mode']))}
          >
            <SelectTrigger aria-label="Work mode">
              <SelectValue placeholder="Any" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY}>Any work mode</SelectItem>
              {WORK_MODES.map((mode) => (
                <SelectItem key={mode} value={mode}>
                  {WORK_MODE_LABELS[mode]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FilterBlock>

        <FilterBlock label="Company" htmlFor="filter-company">
          <Input
            id="filter-company"
            placeholder="Any company"
            value={filters.company}
            onChange={(event) => setFilter('company', event.target.value)}
          />
        </FilterBlock>

        <FilterBlock label="Experience (years)">
          <div className="flex items-center gap-2">
            <Input
              type="number"
              min={0}
              step={0.5}
              placeholder="Min"
              aria-label="Minimum experience in years"
              value={filters.experience_min}
              onChange={(event) => setFilter('experience_min', event.target.value)}
            />
            <span className="text-muted-foreground">–</span>
            <Input
              type="number"
              min={0}
              step={0.5}
              placeholder="Max"
              aria-label="Maximum experience in years"
              value={filters.experience_max}
              onChange={(event) => setFilter('experience_max', event.target.value)}
            />
          </div>
        </FilterBlock>

        <FilterBlock label="Source">
          <Select
            value={filters.source || ANY}
            onValueChange={(value) => setFilter('source', value === ANY ? '' : (value as JobFiltersState['source']))}
          >
            <SelectTrigger aria-label="Job source">
              <SelectValue placeholder="Any" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY}>All sources</SelectItem>
              {sourceOptions.map((source) => (
                <SelectItem key={source.source} value={source.source}>
                  {sourceLabel(source.source)}
                  <span className="ml-1 text-muted-foreground">({source.job_count})</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FilterBlock>

        <FilterBlock label="Posted within">
          <Select
            value={filters.posted_within_hours || ANY}
            onValueChange={(value) => setFilter('posted_within_hours', value === ANY ? '' : value)}
          >
            <SelectTrigger aria-label="Posted within">
              <SelectValue placeholder="Any time" />
            </SelectTrigger>
            <SelectContent>
              {POSTED_WITHIN_OPTIONS.map((option) => (
                <SelectItem key={option.value || ANY} value={option.value || ANY}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FilterBlock>

        <FilterBlock label="Application status">
          <Select
            value={filters.status || ANY}
            onValueChange={(value) => setFilter('status', value === ANY ? '' : (value as JobFiltersState['status']))}
          >
            <SelectTrigger aria-label="Application status">
              <SelectValue placeholder="Any" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY}>Any status</SelectItem>
              <SelectItem value="NONE">Not applied</SelectItem>
              {APPLICATION_STATUSES.map((status) => (
                <SelectItem key={status} value={status}>
                  {APPLICATION_STATUS_LABELS[status]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FilterBlock>

        <FilterBlock label="Company priority">
          <Select
            value={filters.priority || ANY}
            onValueChange={(value) => setFilter('priority', value === ANY ? '' : (value as JobFiltersState['priority']))}
          >
            <SelectTrigger aria-label="Company priority">
              <SelectValue placeholder="Any" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY}>Any priority</SelectItem>
              {COMPANY_PRIORITIES.map((priority) => (
                <SelectItem key={priority} value={priority}>
                  {PRIORITY_LABELS[priority]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FilterBlock>
      </div>
    </section>
  )
}
