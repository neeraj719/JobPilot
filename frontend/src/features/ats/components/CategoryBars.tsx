import { ChevronDown } from 'lucide-react'
import * as React from 'react'

import { cn } from '@/lib/utils'
import { scoreTone, TONE_BAR, TONE_TEXT } from '@/features/ats/labels'
import type { CategoryScore } from '@/features/ats/types'

function CategoryRow({ category }: { category: CategoryScore }) {
  const [open, setOpen] = React.useState(false)
  const id = React.useId()
  const tone = scoreTone(category.score)
  return (
    <li className="py-2">
      <button
        type="button"
        className="group flex w-full items-center gap-3 text-left"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="w-40 shrink-0 truncate text-sm font-medium sm:w-48">{category.label}</span>
        <span className="relative h-2 flex-1 overflow-hidden rounded-full bg-muted">
          {category.applicable ? (
            <span className={cn('absolute inset-y-0 left-0 rounded-full transition-all', TONE_BAR[tone])} style={{ width: `${category.score ?? 0}%` }} />
          ) : null}
        </span>
        <span className={cn('w-10 shrink-0 text-right text-sm font-semibold tabular-nums', TONE_TEXT[tone])}>
          {category.applicable ? category.score : 'n/a'}
        </span>
        <span className="hidden w-10 shrink-0 text-right text-xs tabular-nums text-muted-foreground sm:inline" title="Weight in the overall estimate">
          {category.applicable ? `${Math.round(category.weight * 100)}%` : '—'}
        </span>
        <ChevronDown className={cn('size-4 shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')} aria-hidden />
      </button>
      {open ? (
        <ul id={id} className="mt-2 space-y-1 pl-1 text-sm text-muted-foreground sm:pl-4">
          {category.evidence.map((line) => (
            <li key={line} className="flex gap-2">
              <span aria-hidden className="mt-2 size-1 shrink-0 rounded-full bg-muted-foreground/60" />
              <span>{line}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  )
}

/** Category scores with their evidence on expand. */
export function CategoryBars({ categories }: { categories: CategoryScore[] }) {
  return (
    <ul className="divide-y divide-border" aria-label="Category scores">
      {categories.map((category) => (
        <CategoryRow key={category.key} category={category} />
      ))}
    </ul>
  )
}
