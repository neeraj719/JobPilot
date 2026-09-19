/**
 * URL-synced filter state for the Jobs page.
 *
 * Everything lives in `?search=params` so a filtered view is shareable and survives a
 * reload / back-navigation. The hook hands the page a plain object it can feed straight
 * into `useJobs` (which drops empty values before building the query key).
 */
import * as React from 'react'
import { useSearchParams } from 'react-router-dom'

import type {
  ApplicationStatus,
  CompanyPriority,
  JobListParams,
  JobSortOption,
  JobSourceType,
  WorkMode,
} from '@/types/api'

export const JOBS_PAGE_SIZE = 12

/** Suggestions for the location box — the user can still type anything. */
export const COMMON_LOCATIONS = [
  'Remote',
  'Bangalore',
  'Hyderabad',
  'Pune',
  'Chennai',
  'Mumbai',
  'Delhi NCR',
  'Noida',
  'Gurgaon',
  'Ahmedabad',
  'Kolkata',
  'Jaipur',
] as const

export const POSTED_WITHIN_OPTIONS = [
  { value: '', label: 'Any time' },
  { value: '24', label: 'Last 24 hours' },
  { value: '72', label: 'Last 3 days' },
  { value: '168', label: 'Last 7 days' },
] as const

export interface JobFiltersState {
  q: string
  min_score: number
  salary_min: string
  location: string
  work_mode: WorkMode | ''
  company: string
  experience_min: string
  experience_max: string
  source: JobSourceType | ''
  posted_within_hours: string
  status: ApplicationStatus | 'NONE' | ''
  priority: CompanyPriority | ''
  sort: JobSortOption
  page: number
}

export const DEFAULT_JOB_FILTERS: JobFiltersState = {
  q: '',
  min_score: 0,
  salary_min: '',
  location: '',
  work_mode: '',
  company: '',
  experience_min: '',
  experience_max: '',
  source: '',
  posted_within_hours: '',
  status: '',
  priority: '',
  sort: 'match',
  page: 1,
}

/** Keys that, when changed, should send the user back to page 1. */
const RESET_PAGE_KEYS = new Set<keyof JobFiltersState>([
  'q',
  'min_score',
  'salary_min',
  'location',
  'work_mode',
  'company',
  'experience_min',
  'experience_max',
  'source',
  'posted_within_hours',
  'status',
  'priority',
  'sort',
])

function readNumber(value: string | null, fallback: number): number {
  if (value === null || value === '') return fallback
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function parse(params: URLSearchParams): JobFiltersState {
  return {
    q: params.get('q') ?? '',
    min_score: Math.max(0, Math.min(100, readNumber(params.get('min_score'), 0))),
    salary_min: params.get('salary_min') ?? '',
    location: params.get('location') ?? '',
    work_mode: (params.get('work_mode') as WorkMode | null) ?? '',
    company: params.get('company') ?? '',
    experience_min: params.get('experience_min') ?? '',
    experience_max: params.get('experience_max') ?? '',
    source: (params.get('source') as JobSourceType | null) ?? '',
    posted_within_hours: params.get('posted_within_hours') ?? '',
    status: (params.get('status') as ApplicationStatus | 'NONE' | null) ?? '',
    priority: (params.get('priority') as CompanyPriority | null) ?? '',
    sort: (params.get('sort') as JobSortOption | null) ?? 'match',
    page: Math.max(1, readNumber(params.get('page'), 1)),
  }
}

/** Number of filters the user has actually set (sort and page do not count). */
export function countActiveFilters(state: JobFiltersState): number {
  let count = 0
  if (state.q) count += 1
  if (state.min_score > 0) count += 1
  if (state.salary_min) count += 1
  if (state.location) count += 1
  if (state.work_mode) count += 1
  if (state.company) count += 1
  if (state.experience_min) count += 1
  if (state.experience_max) count += 1
  if (state.source) count += 1
  if (state.posted_within_hours) count += 1
  if (state.status) count += 1
  if (state.priority) count += 1
  return count
}

/** Turn the UI state into the query the API understands. */
export function toJobListParams(state: JobFiltersState): JobListParams {
  const params: JobListParams = {
    page: state.page,
    page_size: JOBS_PAGE_SIZE,
    sort: state.sort,
  }
  if (state.q) params.q = state.q
  if (state.min_score > 0) params.min_score = state.min_score
  if (state.salary_min) params.salary_min = Number(state.salary_min)
  if (state.location) params.location = state.location
  if (state.work_mode) params.work_mode = state.work_mode
  if (state.company) params.company = state.company
  if (state.experience_min) params.experience_min = Number(state.experience_min)
  if (state.experience_max) params.experience_max = Number(state.experience_max)
  if (state.source) params.source = state.source
  if (state.posted_within_hours) params.posted_within_hours = Number(state.posted_within_hours)
  if (state.status) params.status = state.status
  if (state.priority) params.priority = state.priority
  return params
}

export interface UseJobFiltersResult {
  filters: JobFiltersState
  setFilter: <K extends keyof JobFiltersState>(key: K, value: JobFiltersState[K]) => void
  setFilters: (patch: Partial<JobFiltersState>) => void
  reset: () => void
  activeCount: number
}

export function useJobFilters(): UseJobFiltersResult {
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = React.useMemo(() => parse(searchParams), [searchParams])

  const setFilters = React.useCallback(
    (patch: Partial<JobFiltersState>) => {
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current)
          const touchesFilter = Object.keys(patch).some((key) => RESET_PAGE_KEYS.has(key as keyof JobFiltersState))
          for (const [key, value] of Object.entries(patch)) {
            const isDefault = value === '' || value === undefined || value === null || (key === 'min_score' && value === 0)
            if (isDefault) next.delete(key)
            else next.set(key, String(value))
          }
          if (touchesFilter && patch.page === undefined) next.delete('page')
          if (next.get('page') === '1') next.delete('page')
          if (next.get('sort') === 'match') next.delete('sort')
          return next
        },
        { replace: true },
      )
    },
    [setSearchParams],
  )

  const setFilter = React.useCallback(
    <K extends keyof JobFiltersState>(key: K, value: JobFiltersState[K]) => {
      setFilters({ [key]: value } as Partial<JobFiltersState>)
    },
    [setFilters],
  )

  const reset = React.useCallback(() => {
    setSearchParams(new URLSearchParams(), { replace: true })
  }, [setSearchParams])

  return { filters, setFilter, setFilters, reset, activeCount: countActiveFilters(filters) }
}
