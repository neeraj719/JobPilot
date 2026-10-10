import { ChevronLeft, ChevronRight } from 'lucide-react'
import * as React from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export interface PaginationProps extends React.HTMLAttributes<HTMLDivElement> {
  /** 1-based, matching the backend contract. */
  page: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
  disabled?: boolean
}

/**
 * Simple prev/next pagination with a "x–y of z" readout — enough for every list endpoint
 * in the API, which all return `{items, total, page, page_size}`.
 */
export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
  disabled = false,
  className,
  ...props
}: PaginationProps) {
  const pageCount = Math.max(1, Math.ceil(total / Math.max(pageSize, 1)))
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, total)

  if (total <= pageSize && page === 1) return null

  return (
    <div
      className={cn('flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground', className)}
      {...props}
    >
      <p>
        Showing <span className="font-medium text-foreground">{from}</span>–
        <span className="font-medium text-foreground">{to}</span> of{' '}
        <span className="font-medium text-foreground">{total}</span>
      </p>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page - 1)}
          disabled={disabled || page <= 1}
          aria-label="Previous page"
        >
          <ChevronLeft />
          Previous
        </Button>
        <span className="px-1 text-xs tabular-nums">
          Page {page} of {pageCount}
        </span>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page + 1)}
          disabled={disabled || page >= pageCount}
          aria-label="Next page"
        >
          Next
          <ChevronRight />
        </Button>
      </div>
    </div>
  )
}
