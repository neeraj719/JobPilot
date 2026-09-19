import type { LucideIcon } from 'lucide-react'
import * as React from 'react'

import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'

export interface DataTableColumn<T> {
  /** Stable key for the column. */
  id: string
  header: React.ReactNode
  /** Renderer for one cell. Keep it pure — it runs on every render. */
  cell: (row: T, rowIndex: number) => React.ReactNode
  align?: 'left' | 'center' | 'right'
  /** Applied to the `<td>`. */
  className?: string
  /** Applied to the `<th>`. */
  headerClassName?: string
  /** Hide below the `md` breakpoint — useful for secondary columns. */
  hideBelowMd?: boolean
}

export interface DataTableProps<T> {
  data: T[] | undefined
  columns: DataTableColumn<T>[]
  getRowId?: (row: T, index: number) => string
  loading?: boolean
  /** Anything thrown by the API client; renders `ErrorState` when set. */
  error?: unknown
  onRetry?: () => void
  onRowClick?: (row: T, index: number) => void
  emptyTitle?: string
  emptyDescription?: string
  emptyIcon?: LucideIcon
  emptyAction?: React.ReactNode
  caption?: string
  className?: string
  skeletonRows?: number
}

const alignClass: Record<NonNullable<DataTableColumn<unknown>['align']>, string> = {
  left: 'text-left',
  center: 'text-center',
  right: 'text-right',
}

/**
 * Typed table with built-in loading / empty / error states.
 *
 * ```tsx
 * <DataTable
 *   data={page?.items}
 *   loading={isLoading}
 *   error={error}
 *   onRetry={refetch}
 *   onRowClick={(row) => navigate(`/applications/${row.id}`)}
 *   columns={[
 *     { id: 'role', header: 'Role', cell: (row) => row.job_title },
 *     { id: 'status', header: 'Status', cell: (row) => <StatusBadge status={row.status} /> },
 *   ]}
 * />
 * ```
 */
export function DataTable<T>({
  data,
  columns,
  getRowId,
  loading = false,
  error,
  onRetry,
  onRowClick,
  emptyTitle = 'Nothing here yet',
  emptyDescription,
  emptyIcon,
  emptyAction,
  caption,
  className,
  skeletonRows = 6,
}: DataTableProps<T>) {
  if (error) {
    return <ErrorState error={error} onRetry={onRetry} size="sm" className={className} />
  }

  const rows = data ?? []
  const showEmpty = !loading && rows.length === 0

  return (
    <div className={cn('overflow-hidden rounded-lg border border-border bg-card', className)}>
      <Table>
        {caption ? <TableCaption>{caption}</TableCaption> : null}
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {columns.map((column) => (
              <TableHead
                key={column.id}
                className={cn(
                  alignClass[column.align ?? 'left'],
                  column.hideBelowMd && 'hidden md:table-cell',
                  column.headerClassName,
                )}
                scope="col"
              >
                {column.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading
            ? Array.from({ length: skeletonRows }, (_, rowIndex) => (
                <TableRow key={`skeleton-${rowIndex}`} className="hover:bg-transparent">
                  {columns.map((column) => (
                    <TableCell key={column.id} className={cn(column.hideBelowMd && 'hidden md:table-cell')}>
                      <Skeleton className="h-4 w-full max-w-40" />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            : rows.map((row, rowIndex) => (
                <TableRow
                  key={getRowId ? getRowId(row, rowIndex) : rowIndex}
                  className={cn(onRowClick && 'cursor-pointer')}
                  onClick={onRowClick ? () => onRowClick(row, rowIndex) : undefined}
                  tabIndex={onRowClick ? 0 : undefined}
                  onKeyDown={
                    onRowClick
                      ? (event) => {
                          if (event.key === 'Enter') {
                            event.preventDefault()
                            onRowClick(row, rowIndex)
                          }
                        }
                      : undefined
                  }
                >
                  {columns.map((column) => (
                    <TableCell
                      key={column.id}
                      className={cn(
                        alignClass[column.align ?? 'left'],
                        column.hideBelowMd && 'hidden md:table-cell',
                        column.className,
                      )}
                    >
                      {column.cell(row, rowIndex)}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
        </TableBody>
      </Table>

      {showEmpty ? (
        <EmptyState
          title={emptyTitle}
          {...(emptyDescription ? { description: emptyDescription } : {})}
          {...(emptyIcon ? { icon: emptyIcon } : {})}
          {...(emptyAction ? { action: emptyAction } : {})}
          size="sm"
          className="border-0 border-t border-border bg-transparent"
        />
      ) : null}
    </div>
  )
}
