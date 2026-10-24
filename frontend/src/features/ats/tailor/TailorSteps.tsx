import { Check } from 'lucide-react'

import { cn } from '@/lib/utils'

export interface StepItem {
  label: string
  done: boolean
  active: boolean
}

/** The optimizer's numbered step strip (same language as `AtsOptimizer`); stacks on phones. */
export function TailorSteps({ steps }: { steps: StepItem[] }) {
  return (
    <ol className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-6" aria-label="Steps">
      {steps.map((step, index) => (
        <li key={step.label} className="flex items-center gap-2" aria-current={step.active ? 'step' : undefined}>
          <span
            className={cn(
              'flex size-7 shrink-0 items-center justify-center rounded-full border text-xs font-semibold tabular-nums',
              step.done
                ? 'border-success bg-success text-success-foreground'
                : step.active
                  ? 'border-primary text-primary'
                  : 'border-border text-muted-foreground',
            )}
            aria-hidden
          >
            {step.done ? <Check className="size-3.5" /> : index + 1}
          </span>
          <span className={cn('text-sm', step.active ? 'font-medium' : 'text-muted-foreground')}>
            {step.label}
            {step.done ? <span className="sr-only"> (done)</span> : null}
          </span>
        </li>
      ))}
    </ol>
  )
}
