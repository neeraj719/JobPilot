import { ChevronDown } from 'lucide-react'
import * as React from 'react'

import { Button, type ButtonProps } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { AiChoice, WorkflowTarget } from '@/features/ai-providers/types'
import { type AiTask, choiceShortLabel, choiceTarget, useAiChoice } from '@/features/ai-providers/useAiChoice'

/** Compact candidate list (the chevron's popover): a one-off pick, no dialog. */
function CandidateMenu({
  candidates,
  loading,
  workflowLabel,
  onPick,
}: {
  candidates: AiChoice[]
  loading: boolean
  workflowLabel: string
  onPick: (choice: AiChoice) => void
}) {
  if (loading) {
    return (
      <div className="space-y-2 p-1" aria-hidden data-testid="ai-choice-skeleton">
        {[0, 1, 2].map((i) => (
          <div key={i} className="space-y-1.5 rounded-lg p-2">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-3 w-1/3" />
          </div>
        ))}
      </div>
    )
  }
  return (
    <div role="menu" aria-label="Run once with" className="space-y-0.5">
      {candidates.map((choice) => (
        <button
          key={choice.id}
          type="button"
          role="menuitem"
          disabled={!choice.available}
          onClick={() => onPick(choice)}
          className={cn(
            'flex w-full flex-col items-start gap-0.5 rounded-lg px-2.5 py-2 text-left transition-colors duration-150',
            'hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            'disabled:cursor-not-allowed disabled:hover:bg-transparent',
          )}
        >
          <span className="flex w-full items-center justify-between gap-2">
            <span className={cn('truncate text-sm font-medium', choice.available ? 'text-foreground' : 'text-muted-foreground')}>
              {choice.label}
            </span>
            {choice.is_default ? <span className="shrink-0 text-2xs font-medium text-primary">Default</span> : null}
          </span>
          <span className="text-2xs text-muted-foreground">
            {choice.available
              ? `${choiceShortLabel(choice)} · ${choice.cost_hint === 'unknown' ? 'cost unknown' : choice.cost_hint}`
              : choice.unavailable_reason ?? 'Unavailable'}
          </span>
          {choice.is_default ? <span className="sr-only">Default for {workflowLabel}</span> : null}
        </button>
      ))}
    </div>
  )
}

export interface AiRunButtonProps extends Omit<ButtonProps, 'onClick' | 'children'> {
  /** The backend task the action runs (decides the default model and the dialog copy). */
  task: AiTask
  /** Runs the action; `ai` is the picked model, `undefined` = the routing. */
  onRun: (ai?: WorkflowTarget) => unknown
  children: React.ReactNode
  /** One line for the dialog: what is sent to the model. */
  context?: string
  /** "Model: qwen2.5:3b-instruct · local" under the button. */
  showModel?: boolean
  /** `false` = this run makes no model call (e.g. AI refinement switched off): a plain button. */
  aiEnabled?: boolean
  /** Extra classes for the wrapper. */
  wrapperClassName?: string
}

/**
 * Split button for every AI action: the main part runs (asking "which model?" first when the
 * user has 2+ usable models and asked to be asked), the chevron opens a compact list for a
 * one-off pick without the dialog. With one usable model it is a plain button.
 */
export function AiRunButton({
  task,
  onRun,
  children,
  context,
  showModel = true,
  aiEnabled = true,
  wrapperClassName,
  className,
  variant,
  size,
  disabled,
  loading,
  ...rest
}: AiRunButtonProps) {
  const choice = useAiChoice(task, { context, enabled: aiEnabled })
  const [open, setOpen] = React.useState(false)
  const data = choice.data
  const split = aiEnabled && choice.canChoose

  const runMain = () => {
    if (!aiEnabled) {
      void onRun(undefined)
      return
    }
    void choice.runWithModel(async (ai) => onRun(ai))
  }

  const helper = (() => {
    if (!aiEnabled || !showModel) return null
    if (choice.query.isLoading) return <Skeleton className="h-3 w-36" data-testid="ai-model-helper-skeleton" />
    if (!choice.defaultChoice) return null
    const asks = data?.should_ask
    return (
      <span className="text-2xs text-muted-foreground" data-testid="ai-model-helper">
        Model: <span className="font-medium text-foreground">{choiceShortLabel(choice.defaultChoice)}</span>
        {asks ? ' · asks before running' : ''}
      </span>
    )
  })()

  return (
    <span className={cn('inline-flex flex-col items-start gap-1', wrapperClassName)}>
      <span className="inline-flex" role={split ? 'group' : undefined} aria-label={split ? 'AI action' : undefined}>
        <Button
          {...rest}
          variant={variant}
          size={size}
          className={cn(split && 'rounded-r-none', className)}
          disabled={disabled}
          loading={loading}
          onClick={runMain}
        >
          {children}
        </Button>
        {split ? (
          <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
              <Button
                variant={variant}
                size={size}
                disabled={disabled || loading}
                className={cn(
                  'rounded-l-none border-l px-2',
                  variant === 'outline' || variant === 'secondary' || variant === 'ghost' || variant === 'soft'
                    ? 'border-l-border'
                    : 'border-l-gradient-foreground/30',
                )}
                aria-label="Choose the model for this run"
                data-testid="ai-run-chevron"
              >
                <ChevronDown aria-hidden />
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-80 p-2">
              <p className="px-2.5 pb-1 pt-1.5 text-2xs font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                Run once with
              </p>
              <CandidateMenu
                candidates={data?.candidates ?? []}
                loading={choice.query.isLoading}
                workflowLabel={data?.workflow_label ?? ''}
                onPick={(picked) => {
                  setOpen(false)
                  void onRun(choiceTarget(picked))
                }}
              />
            </PopoverContent>
          </Popover>
        ) : null}
      </span>
      {helper}
    </span>
  )
}
