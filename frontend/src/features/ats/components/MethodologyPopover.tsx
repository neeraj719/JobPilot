import { Info } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useMethodology } from '@/features/ats/api'

/** "How is this estimated?" — the categories, their weights, the version and the disclaimer. */
export function MethodologyPopover({ weights }: { weights?: Record<string, number> }) {
  const { data } = useMethodology()
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className="h-7 gap-1 px-2 text-xs text-muted-foreground">
          <Info aria-hidden />
          How is this estimated?
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(92vw,26rem)] space-y-3 text-sm" align="end">
        <div className="space-y-1">
          <p className="font-semibold">Estimated ATS compatibility</p>
          <p className="text-xs text-muted-foreground">{data?.disclaimer}</p>
        </div>
        <ul className="space-y-2">
          {(data?.categories ?? []).map((category) => {
            const weight = weights?.[category.key] ?? category.weight
            return (
              <li key={category.key} className="space-y-0.5">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="font-medium">{category.label}</span>
                  <span className="tabular-nums text-xs text-muted-foreground">{Math.round(weight * 100)}%</span>
                </div>
                <p className="text-xs text-muted-foreground">{category.description}</p>
              </li>
            )
          })}
        </ul>
        {data?.notes.length ? (
          <ul className="list-disc space-y-1 pl-4 text-xs text-muted-foreground">
            {data.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        ) : null}
        <p className="text-[11px] text-muted-foreground">Methodology {data?.version}</p>
      </PopoverContent>
    </Popover>
  )
}
