/**
 * Loading skeletons for AI Model Settings: the setup summary, the provider cards, the
 * per-task routing card and the usage card. Each mirrors the loaded component's frame,
 * paddings and grid (see `SetupSummary`, `ProviderCard`, `RoutingCard`, `UsageCard`).
 */
import type * as React from 'react'

import { SkeletonLine, SkeletonRegion } from '@/components/common/skeletons'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

/** Card header: an icon + title line over a one-line description; optional right-side control. */
function HeaderSkeleton({ title, description, right }: { title: string; description: string; right?: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-3 p-6 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex h-5 items-center gap-2">
          <Skeleton className="size-4 rounded" />
          <Skeleton className={`h-4 ${title}`} />
        </div>
        <SkeletonLine size="sm" className={`${description} max-w-full`} />
      </div>
      {right}
    </div>
  )
}

/** One `ProviderCard`: name + kind + status pill, description, privacy note, key field, footer. */
export function ProviderCardSkeleton() {
  return (
    <Card className="flex h-full flex-col" aria-hidden>
      <div className="flex flex-col space-y-2 p-6 pb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <SkeletonLine size="title" className="w-28" />
            <SkeletonLine size="xs" className="w-20" boxClassName="mt-0.5" />
          </div>
          <Skeleton className="h-[22px] w-24 shrink-0 rounded-full" />
        </div>
        <div>
          <SkeletonLine size="sm" className="w-full" />
          <SkeletonLine size="sm" className="w-3/5" />
        </div>
      </div>
      <CardContent className="flex-1 space-y-4">
        <div className="rounded-md bg-muted/50 p-2.5">
          <SkeletonLine size="xs" className="w-full" />
          <SkeletonLine size="xs" className="w-4/5" />
        </div>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <SkeletonLine size="sm" className="w-16" />
            <Skeleton className="h-9 w-full rounded-lg" />
            <SkeletonLine size="xs" className="w-3/4" />
          </div>
          <Skeleton className="h-8 w-20 rounded-md" />
        </div>
      </CardContent>
      <div className="flex flex-wrap items-center gap-2 border-t p-6 pt-4">
        <Skeleton className="h-8 w-36 rounded-md" />
        <Skeleton className="h-8 w-32 rounded-md" />
        <div className="ml-auto flex gap-3">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-3 w-10" />
        </div>
      </div>
    </Card>
  )
}

/** The provider/model picker pair (`TargetPicker`). */
function PickerSkeleton() {
  return (
    <div className="grid gap-2 sm:grid-cols-[minmax(12rem,max-content)_minmax(0,1fr)]">
      <Skeleton className="h-9 w-48 rounded-lg" />
      <Skeleton className="h-9 w-full rounded-lg" />
    </div>
  )
}

/** `RoutingCard`: default model, the per-task list, the fallback box, the save footer. */
export function RoutingCardSkeleton({ tasks = 5 }: { tasks?: number }) {
  return (
    <Card aria-hidden>
      <HeaderSkeleton title="w-40" description="w-[30rem]" />
      <CardContent className="space-y-6">
        <section className="space-y-2">
          <SkeletonLine size="sm" className="w-28" />
          <PickerSkeleton />
        </section>
        <section className="space-y-3">
          <SkeletonLine size="sm" className="w-16" />
          <ul className="divide-y rounded-lg border">
            {Array.from({ length: tasks }, (_, index) => (
              <li key={index} className="grid gap-2 p-3 lg:grid-cols-[minmax(0,14rem)_minmax(0,1fr)] lg:items-center">
                <div className="min-w-0">
                  <SkeletonLine size="sm" className={index % 2 ? 'w-28' : 'w-36'} />
                  <SkeletonLine size="xs" className="w-48 max-w-full" />
                  <SkeletonLine size="xs" className="w-32" boxClassName="mt-1" />
                </div>
                <PickerSkeleton />
              </li>
            ))}
          </ul>
        </section>
        <section className="space-y-3 rounded-lg border p-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <SkeletonLine size="sm" className="w-16" />
              <SkeletonLine size="xs" className="w-full max-w-lg" />
              <SkeletonLine size="xs" className="w-2/3" />
            </div>
            <Skeleton className="h-5 w-9 shrink-0 rounded-full" />
          </div>
        </section>
      </CardContent>
      <div className="flex flex-wrap items-center justify-end gap-2 border-t p-6 pt-4">
        <Skeleton className="h-9 w-16 rounded-lg" />
        <Skeleton className="h-9 w-32 rounded-lg" />
      </div>
    </Card>
  )
}

/** The body of `UsageCard`: four stat tiles and the 180 px calls-per-day chart. */
export function UsageBodySkeleton({ bare }: { bare?: boolean }) {
  const body = (
    <>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-hidden>
        {Array.from({ length: 4 }, (_, index) => (
          <div key={index} className="rounded-lg border p-3">
            <SkeletonLine size="xs" className="w-20" />
            <SkeletonLine size="lg" className="w-16" boxClassName="mt-1" />
            <SkeletonLine size="xs" className="w-28 max-w-full" boxClassName="mt-0.5" />
          </div>
        ))}
      </div>
      <div className="flex h-[180px] items-end gap-2 pb-6 pl-10" aria-hidden>
        {[30, 55, 20, 70, 45, 60, 35, 80, 50, 25, 65, 40].map((value, index) => (
          <Skeleton key={index} className="flex-1 rounded-b-none rounded-t-sm" style={{ height: `${value}%` }} />
        ))}
      </div>
    </>
  )
  return bare ? (
    <div className="space-y-4" aria-hidden>
      {body}
    </div>
  ) : (
    <SkeletonRegion label="Loading usage" className="space-y-4">
      {body}
    </SkeletonRegion>
  )
}

/** The whole AI Model Settings page body while the catalog and settings load. */
export function AiModelSettingsSkeleton() {
  return (
    <SkeletonRegion label="Loading AI model settings" className="space-y-8">
      <div aria-hidden>
        <Card>
          <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <Skeleton className="size-10 shrink-0 rounded-full" />
              <div className="min-w-0">
                <SkeletonLine size="xs" className="w-24" />
                <SkeletonLine size="base" className="w-64 max-w-full" />
                <SkeletonLine size="xs" className="w-80 max-w-full" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
      <section className="space-y-3" aria-hidden>
        <div>
          <SkeletonLine size="lg" className="w-24" />
          <SkeletonLine size="sm" className="w-[34rem] max-w-full" />
        </div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }, (_, index) => (
            <ProviderCardSkeleton key={index} />
          ))}
        </div>
      </section>
      <RoutingCardSkeleton />
      <Card aria-hidden>
        <HeaderSkeleton title="w-44" description="w-[28rem]" right={<Skeleton className="h-9 w-56 shrink-0 rounded-full" />} />
        <CardContent className="space-y-4">
          <UsageBodySkeleton bare />
        </CardContent>
      </Card>
    </SkeletonRegion>
  )
}
