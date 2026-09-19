import { Building2, Search } from 'lucide-react'
import * as React from 'react'

import { DataTable, type DataTableColumn } from '@/components/common/DataTable'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Pagination } from '@/components/ui/pagination'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { toast } from '@/components/ui/toaster'
import { useDebounce } from '@/hooks/useDebounce'
import { errorMessage } from '@/lib/api'
import { PRIORITY_LABELS, formatNumber, initials } from '@/lib/utils'
import { useCompanies, useUpsertCompanyPreference } from '@/features/companies/api'
import { COMPANY_PRIORITIES, type CompanyPriority, type CompanyRead } from '@/types/api'

const PAGE_SIZE = 20
const NO_PRIORITY = '__none__'

export function CompanyDirectory() {
  const [search, setSearch] = React.useState('')
  const [priority, setPriority] = React.useState<CompanyPriority | typeof NO_PRIORITY>(NO_PRIORITY)
  const [page, setPage] = React.useState(1)
  const debouncedSearch = useDebounce(search, 300)

  React.useEffect(() => {
    setPage(1)
  }, [debouncedSearch, priority])

  const companiesQuery = useCompanies({
    page,
    page_size: PAGE_SIZE,
    q: debouncedSearch || undefined,
    priority: priority === NO_PRIORITY ? undefined : priority,
  })
  const upsert = useUpsertCompanyPreference()
  const [savingId, setSavingId] = React.useState<string | null>(null)

  const setCompanyPriority = async (company: CompanyRead, next: CompanyPriority) => {
    setSavingId(company.id)
    try {
      await upsert.mutateAsync({ company_name: company.name, priority: next })
      toast.success(`${company.name} set to ${PRIORITY_LABELS[next]}`)
    } catch (error) {
      toast.error('Could not update the priority', { description: errorMessage(error) })
    } finally {
      setSavingId(null)
    }
  }

  const columns: DataTableColumn<CompanyRead>[] = [
    {
      id: 'name',
      header: 'Company',
      cell: (company) => (
        <div className="flex items-center gap-3">
          <Avatar className="size-8">
            {company.logo_url ? <AvatarImage src={company.logo_url} alt="" /> : null}
            <AvatarFallback className="text-xs">{initials(company.name)}</AvatarFallback>
          </Avatar>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{company.name}</p>
            {company.domain ? <p className="truncate text-xs text-muted-foreground">{company.domain}</p> : null}
          </div>
        </div>
      ),
    },
    {
      id: 'industry',
      header: 'Industry',
      hideBelowMd: true,
      cell: (company) => <span className="text-sm text-muted-foreground">{company.industry ?? '—'}</span>,
    },
    {
      id: 'open_jobs',
      header: 'Open jobs',
      align: 'right',
      cell: (company) => <span className="tabular-nums">{formatNumber(company.open_jobs)}</span>,
    },
    {
      id: 'applications',
      header: 'Your applications',
      align: 'right',
      hideBelowMd: true,
      cell: (company) => <span className="tabular-nums">{formatNumber(company.applications)}</span>,
    },
    {
      id: 'priority',
      header: 'Priority',
      align: 'right',
      cell: (company) => (
        <Select
          value={company.priority ?? NO_PRIORITY}
          disabled={savingId === company.id}
          onValueChange={(value) => {
            if (value === NO_PRIORITY) return
            void setCompanyPriority(company, value as CompanyPriority)
          }}
        >
          <SelectTrigger className="ml-auto h-8 w-[10.5rem] text-xs" aria-label={`Priority for ${company.name}`}>
            <SelectValue placeholder="Not set" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NO_PRIORITY} disabled>
              Not set
            </SelectItem>
            {COMPANY_PRIORITIES.map((value) => (
              <SelectItem key={value} value={value}>
                {PRIORITY_LABELS[value]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ),
    },
  ]

  const total = companiesQuery.data?.total ?? 0

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex-1 space-y-1.5">
          <Label htmlFor="company-search">Search</Label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input
              id="company-search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search companies"
              className="pl-8"
            />
          </div>
        </div>
        <div className="space-y-1.5 sm:w-52">
          <Label htmlFor="company-priority-filter">Filter by priority</Label>
          <Select
            value={priority}
            onValueChange={(value) => setPriority(value as CompanyPriority | typeof NO_PRIORITY)}
          >
            <SelectTrigger id="company-priority-filter">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NO_PRIORITY}>All companies</SelectItem>
              {COMPANY_PRIORITIES.map((value) => (
                <SelectItem key={value} value={value}>
                  {PRIORITY_LABELS[value]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <DataTable
        data={companiesQuery.data?.items}
        columns={columns}
        getRowId={(company) => company.id}
        loading={companiesQuery.isLoading}
        error={companiesQuery.error}
        onRetry={() => void companiesQuery.refetch()}
        emptyIcon={Building2}
        emptyTitle="No companies found"
        emptyDescription={
          debouncedSearch
            ? `Nothing matches “${debouncedSearch}”. Companies appear here once a job from them is discovered.`
            : 'Companies appear here once jobs from them are discovered.'
        }
        caption={total > 0 ? `${formatNumber(total)} companies` : undefined}
      />

      <Pagination
        page={page}
        pageSize={PAGE_SIZE}
        total={total}
        onPageChange={setPage}
        disabled={companiesQuery.isFetching}
      />
    </div>
  )
}
