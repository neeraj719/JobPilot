/**
 * Loading skeletons for the resume feature (insights, version list, score chart, and the
 * Resume Dashboard's list cards). Sized from the loaded markup so nothing shifts on arrival.
 */
import type * as React from 'react'

import { SkeletonLine, SkeletonRegion } from '@/components/common/skeletons'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

/** The `role="status"` region, or a plain box when nested inside a bigger skeleton (`bare`). */
function Region({ bare, label, className, children }: { bare?: boolean; label: string; className?: string; children: React.ReactNode }) {
  return bare ? (
    <div className={className} aria-hidden>
      {children}
    </div>
  ) : (
    <SkeletonRegion label={label} className={className}>
      {children}
    </SkeletonRegion>
  )
}

/** Card header: title + description, optional `size="sm"` button on the right. */
function HeaderSkeleton({ title = 'w-36', description = 'w-72', action }: { title?: string; description?: string; action?: string }) {
  return (
    <div className="flex flex-row flex-wrap items-start justify-between gap-3 p-6">
      <div className="min-w-0 flex-1 space-y-1">
        <SkeletonLine size="title" className={title} />
        <SkeletonLine size="sm" className={cn(description, 'max-w-full')} />
      </div>
      {action ? <Skeleton className={cn('h-8 shrink-0 rounded-md', action)} /> : null}
    </div>
  )
}

/** `ResumeVersionHistory` rows: bordered `px-3 py-2` items, title + badge over a caption, time on the right. */
export function VersionListSkeleton({ rows = 3, label = 'Loading versions', bare }: { rows?: number; label?: string; bare?: boolean }) {
  return (
    <Region bare={bare} label={label}>
      <ol className="space-y-2" aria-hidden>
        {Array.from({ length: rows }, (_, index) => (
          <li key={index} className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2">
            <div className="min-w-0 flex-1">
              <div className="flex h-[22px] items-center gap-2">
                <Skeleton className="h-3.5 w-20" />
                {index === 0 ? <Skeleton className="h-[22px] w-16 rounded-full" /> : null}
              </div>
              <SkeletonLine size="xs" className={index % 2 ? 'w-1/3' : 'w-1/2'} />
            </div>
            <Skeleton className="h-3 w-16 shrink-0" />
          </li>
        ))}
      </ol>
    </Region>
  )
}

/** The 220 px line chart + legend inside "Before and after". */
export function ScoreHistoryPlotSkeleton({ bare }: { bare?: boolean }) {
  return (
    <Region bare={bare} label="Loading score history" className="space-y-3">
      <Skeleton className="h-[220px] w-full rounded-lg" />
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5" aria-hidden>
        {[20, 24, 16].map((width, index) => (
          <div key={index} className="flex h-4 items-center gap-1.5">
            <Skeleton className="h-0.5 w-3.5 rounded-full" />
            <Skeleton className="h-3" style={{ width: `${width * 0.25}rem` }} />
          </div>
        ))}
      </div>
    </Region>
  )
}

/** `ResumeInsights` while the analysis loads: health card, recommendations, before/after chart. */
export function ResumeInsightsSkeleton({ bare }: { bare?: boolean }) {
  return (
    <Region bare={bare} label="Analysing resume" className="space-y-6">
      <Card aria-hidden>
        <HeaderSkeleton title="w-32" description="w-80" action="w-36" />
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-6">
            <Skeleton className="size-28 shrink-0 rounded-full" />
            <div className="min-w-0 flex-1 space-y-3">
              <SkeletonLine size="sm" className="w-28" />
              <div className="space-y-1">
                <SkeletonLine size="xs" className="w-36" />
                <SkeletonLine size="2xl" className="w-48" />
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
      <Card aria-hidden>
        <HeaderSkeleton title="w-40" description="w-96" action="w-36" />
        <CardContent>
          <div className="space-y-2">
            <SkeletonLine size="xs" className="w-28" />
            <ul className="space-y-2">
              {Array.from({ length: 3 }, (_, index) => (
                <li key={index} className="rounded-md border border-border p-3">
                  <div className="flex items-start gap-3">
                    <Skeleton className="mt-0.5 size-5 shrink-0 rounded-full" />
                    <div className="min-w-0 flex-1 space-y-2">
                      <div className="flex h-[22px] items-center gap-2">
                        <Skeleton className="h-3.5 w-48 max-w-[60%]" />
                        <Skeleton className="h-[22px] w-16 rounded-full" />
                      </div>
                      <SkeletonLine size="sm" className={index === 1 ? 'w-1/2' : 'w-4/5'} />
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </CardContent>
      </Card>
      <Card aria-hidden>
        <HeaderSkeleton title="w-32" description="w-80" />
        <CardContent>
          <ScoreHistoryPlotSkeleton bare />
        </CardContent>
      </Card>
    </Region>
  )
}

/* ------------------------------------------------------------------ Resume Dashboard */

/**
 * A `divide-y` list of `py-2.5` link rows: optional leading score (w-10, text-lg), a title
 * (text-sm) over a caption (text-xs), optional trailing badge.
 */
export function DividedRowsSkeleton({
  rows = 3,
  leading = false,
  trailing = false,
  label = 'Loading',
}: {
  rows?: number
  leading?: boolean
  trailing?: boolean
  label?: string
}) {
  return (
    <SkeletonRegion label={label}>
      <ul className="divide-y" aria-hidden>
        {Array.from({ length: rows }, (_, index) => (
          <li key={index} className="flex items-center gap-3 py-2.5">
            {leading ? (
              <div className="flex h-[1.625rem] w-10 shrink-0 items-center justify-center">
                <Skeleton className="h-[1.125rem] w-7" />
              </div>
            ) : null}
            <div className="min-w-0 flex-1">
              <SkeletonLine size="sm" className={index % 2 ? 'w-2/5' : 'w-3/5'} />
              <SkeletonLine size="xs" className={index % 2 ? 'w-1/2' : 'w-2/5'} />
            </div>
            {trailing ? <Skeleton className="h-[22px] w-16 shrink-0 rounded-full" /> : null}
          </li>
        ))}
      </ul>
    </SkeletonRegion>
  )
}

/** "Job-specific resumes": status pills, then the in-progress rows. */
export function TargetSummarySkeleton() {
  return (
    <SkeletonRegion label="Loading job targets" className="space-y-4">
      <div className="flex flex-wrap gap-2" aria-hidden>
        {[20, 24, 18].map((width, index) => (
          <Skeleton key={index} className="h-[26px] rounded-full" style={{ width: `${width * 0.25}rem` }} />
        ))}
      </div>
      <ul className="divide-y" aria-hidden>
        {Array.from({ length: 2 }, (_, index) => (
          <li key={index} className="flex items-center gap-3 py-2.5">
            <div className="min-w-0 flex-1">
              <SkeletonLine size="sm" className={index ? 'w-2/5' : 'w-1/2'} />
              <SkeletonLine size="xs" className="w-1/4" />
            </div>
            <Skeleton className="h-[22px] w-20 shrink-0 rounded-full" />
          </li>
        ))}
      </ul>
    </SkeletonRegion>
  )
}

/** "Coming up": stacked `text-sm` + `text-xs` items. */
export function UpcomingSkeleton({ rows = 2 }: { rows?: number }) {
  return (
    <SkeletonRegion label="Loading deadlines">
      <ul className="space-y-2" aria-hidden>
        {Array.from({ length: rows }, (_, index) => (
          <li key={index}>
            <SkeletonLine size="sm" className={index ? 'w-1/2' : 'w-2/3'} />
            <SkeletonLine size="xs" className="w-24" />
          </li>
        ))}
      </ul>
    </SkeletonRegion>
  )
}

/* ------------------------------------------------------------------ one resume's panels */

/** The three stacked panels of a resume: insights, extracted information, version history. */
export function ResumePanelsSkeleton({ bare }: { bare?: boolean }) {
  return (
    <Region bare={bare} label="Loading resume" className="space-y-6">
      <ResumeInsightsSkeleton bare />
      {/* ParsedDataPanel: header + button, a 3-up field grid, the summary textarea. */}
      <Card aria-hidden>
        <div className="flex flex-col gap-3 p-6 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 flex-1 space-y-1">
            <SkeletonLine size="title" className="w-44" />
            <SkeletonLine size="sm" className="w-96 max-w-full" />
          </div>
          <Skeleton className="h-8 w-36 shrink-0 rounded-md" />
        </div>
        <CardContent className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }, (_, index) => (
              <div key={index} className="space-y-1.5">
                <SkeletonLine size="sm" className="w-16" />
                <Skeleton className="h-9 w-full rounded-lg" />
              </div>
            ))}
          </div>
          <div className="space-y-1.5">
            <SkeletonLine size="sm" className="w-20" />
            <Skeleton className="h-[98px] w-full rounded-lg" />
          </div>
        </CardContent>
      </Card>
      <Card aria-hidden>
        <div className="flex flex-col space-y-1.5 p-6">
          <SkeletonLine size="title" className="w-36" />
          <SkeletonLine size="sm" className="w-96 max-w-full" />
        </div>
        <CardContent>
          <VersionListSkeleton rows={3} bare />
        </CardContent>
      </Card>
    </Region>
  )
}

/** `ResumeCard` (the compact list card): name + menu, target select, badges, file facts. */
export function ResumeListCardsSkeleton({ count = 2 }: { count?: number }) {
  return (
    <SkeletonRegion label="Loading your resumes" className="space-y-3">
      {Array.from({ length: count }, (_, index) => (
        <Card key={index} aria-hidden>
          <CardContent className="space-y-3 p-4">
            <div className="flex items-start justify-between gap-2">
              <SkeletonLine size="sm" className="w-2/3" boxClassName="flex-1" />
              <Skeleton className="size-8 shrink-0 rounded-md" />
            </div>
            <div className="flex items-center gap-2">
              <Skeleton className="h-3 w-10 shrink-0" />
              <Skeleton className="h-8 flex-1 rounded-lg" />
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <Skeleton className="h-[22px] w-16 rounded-full" />
              <Skeleton className="h-[22px] w-9 rounded-full" />
            </div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1">
              <SkeletonLine size="xs" className="w-1/2" boxClassName="col-span-2" />
              <SkeletonLine size="xs" className="w-12" />
              <SkeletonLine size="xs" className="ml-auto w-20" />
            </div>
          </CardContent>
        </Card>
      ))}
    </SkeletonRegion>
  )
}
