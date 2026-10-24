import * as RadioGroupPrimitive from '@radix-ui/react-radio-group'
import { Cpu, Globe2, Lock, Sparkles } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import * as React from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { toast } from '@/components/ui/toaster'
import { errorMessage } from '@/lib/api'
import { cn, formatRelative } from '@/lib/utils'
import type { AiChoice } from '@/features/ai-providers/types'
import { choiceTarget, patchAiSettings, type PickerRequest, type PickerResult } from '@/features/ai-providers/useAiChoice'

/** Provider chip + model name + badges; used by the dialog and the split button's popover. */
export function ChoiceBadges({ choice, workflowLabel, compact = false }: { choice: AiChoice; workflowLabel: string; compact?: boolean }) {
  const local = choice.provider === 'ollama' || (!choice.hosted && choice.cost_hint === 'free, local')
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      {choice.is_default ? (
        <Badge variant="primary" className="text-2xs">
          Default for {workflowLabel}
        </Badge>
      ) : null}
      {choice.provider === 'mock' ? (
        <Badge variant="muted" className="text-2xs">Rules · no AI</Badge>
      ) : local ? (
        <Badge variant="success" className="text-2xs">
          <Lock className="mr-1 size-3" aria-hidden />
          Local · private
        </Badge>
      ) : choice.hosted ? (
        <Badge variant="info" className="text-2xs">
          <Globe2 className="mr-1 size-3" aria-hidden />
          Hosted
        </Badge>
      ) : (
        <Badge variant="outline" className="text-2xs">Self-hosted</Badge>
      )}
      {!compact && choice.cost_hint !== 'free, local' ? (
        <Badge variant="outline" className="text-2xs">{choice.cost_hint === 'unknown' ? 'Cost unknown' : choice.cost_hint}</Badge>
      ) : null}
      {!compact && choice.last_used_at ? (
        <span className="text-2xs text-muted-foreground">Last used {formatRelative(choice.last_used_at)}</span>
      ) : null}
    </span>
  )
}

function ProviderChip({ choice }: { choice: AiChoice }) {
  return (
    <span className="inline-flex shrink-0 items-center gap-1 rounded-md border border-border bg-surface-2 px-1.5 py-0.5 text-2xs font-medium text-muted-foreground">
      {choice.provider === 'mock' ? <Sparkles className="size-3" aria-hidden /> : <Cpu className="size-3" aria-hidden />}
      {choice.provider_name}
    </span>
  )
}

function CandidateCard({ choice, workflowLabel }: { choice: AiChoice; workflowLabel: string }) {
  const descriptionId = `ai-choice-${choice.id.replace(/[^a-z0-9]/gi, '-')}-desc`
  return (
    <RadioGroupPrimitive.Item
      value={choice.id}
      disabled={!choice.available}
      aria-describedby={descriptionId}
      className={cn(
        'group flex w-full min-w-0 items-start gap-3 rounded-xl border border-border bg-card p-3 text-left transition-[border-color,background-color,box-shadow] duration-150',
        'hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-popover',
        'data-[state=checked]:border-primary data-[state=checked]:bg-primary/5 data-[state=checked]:shadow-xs',
        'disabled:cursor-not-allowed disabled:border-dashed disabled:bg-surface-2 disabled:hover:border-border',
      )}
    >
      <span
        aria-hidden
        className="mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full border border-input bg-card group-data-[state=checked]:border-primary"
      >
        <span className="size-2 rounded-full bg-primary opacity-0 group-data-[state=checked]:opacity-100" />
      </span>
      <span className="min-w-0 flex-1 space-y-1.5">
        <span className="flex flex-wrap items-center gap-2">
          <ProviderChip choice={choice} />
          <span className="min-w-0 truncate text-sm font-semibold text-foreground">{choice.label}</span>
        </span>
        {choice.label !== choice.model && choice.provider !== 'mock' ? (
          <span className="block truncate font-mono text-xs text-muted-foreground">{choice.model}</span>
        ) : null}
        <ChoiceBadges choice={choice} workflowLabel={workflowLabel} />
        <span id={descriptionId} className="block text-xs text-muted-foreground">
          {choice.available ? choice.privacy_note : `Unavailable: ${choice.unavailable_reason ?? 'not configured'}`}
        </span>
      </span>
    </RadioGroupPrimitive.Item>
  )
}

/**
 * "Which model should process this?" — one radio card per candidate. Enter runs with the
 * selected model, Esc cancels (the action does not run). "Remember" writes the workflow's
 * model; "Don't ask again" switches the prompt off (with Undo) and runs with the default.
 */
export function AiModelPickerDialog({ request, onSettle }: { request: PickerRequest; onSettle: (result: PickerResult) => void }) {
  const { data } = request
  const queryClient = useQueryClient()
  const firstAvailable = data.candidates.find((c) => c.id === data.default && c.available) ?? data.candidates.find((c) => c.available)
  const [selected, setSelected] = React.useState<string>(firstAvailable?.id ?? '')
  const [remember, setRemember] = React.useState(false)
  const choice = data.candidates.find((c) => c.id === selected && c.available) ?? null
  const rememberable = choice !== null && !choice.is_default && choice.provider !== 'mock'

  const confirm = () => {
    if (!choice) return
    if (remember && rememberable) {
      patchAiSettings(queryClient, { remember: { workflow: data.workflow, provider: choice.provider, model: choice.model } })
        .then(() => toast.success(`${choice.label} is now the default for ${data.workflow_label}`))
        .catch((error) => toast.error('Could not remember this model', { description: errorMessage(error) }))
    }
    onSettle({ ai: choiceTarget(choice) })
  }

  const dontAskAgain = () => {
    patchAiSettings(queryClient, { model_prompt_mode: 'default' })
      .then(() =>
        toast.success('JobPilot will use your default model without asking', {
          description: 'Change it any time in AI Model Settings.',
          action: {
            label: 'Undo',
            onClick: () => {
              void patchAiSettings(queryClient, { model_prompt_mode: 'ask' })
                .then(() => toast.success('JobPilot will ask again'))
                .catch((error) => toast.error('Could not undo', { description: errorMessage(error) }))
            },
          },
        }),
      )
      .catch((error) => toast.error('Could not save that preference', { description: errorMessage(error) }))
    onSettle({ ai: undefined })
  }

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key !== 'Enter') return
    const role = (event.target as HTMLElement).getAttribute('role')
    if (role === 'radio' || role === 'checkbox' || event.target === event.currentTarget) {
      event.preventDefault()
      confirm()
    }
  }

  return (
    <Dialog open onOpenChange={(open) => (!open ? onSettle(null) : undefined)}>
      <DialogContent
        onKeyDown={onKeyDown}
        className={cn(
          'glass max-h-[88dvh] gap-5 overflow-y-auto overflow-x-hidden sm:max-w-[520px] [&>*]:min-w-0',
          'max-sm:bottom-0 max-sm:top-auto max-sm:translate-y-0 max-sm:rounded-b-none max-sm:rounded-t-2xl max-sm:border-x-0 max-sm:border-b-0',
        )}
        aria-describedby="ai-picker-context"
      >
        <DialogHeader className="pr-6">
          <DialogTitle className="text-xl">Which model should process this?</DialogTitle>
          <DialogDescription id="ai-picker-context">
            <span className="font-medium text-foreground">{request.label}</span> · {request.context} will be sent to the model you pick.
          </DialogDescription>
        </DialogHeader>

        <RadioGroupPrimitive.Root
          value={selected}
          onValueChange={setSelected}
          aria-label="AI model for this run"
          className="grid min-w-0 grid-cols-1 gap-2"
          loop
        >
          {data.candidates.map((candidate) => (
            <CandidateCard key={candidate.id} choice={candidate} workflowLabel={data.workflow_label} />
          ))}
        </RadioGroupPrimitive.Root>

        <div className="flex min-w-0 items-start gap-2">
          <Checkbox
            id="ai-picker-remember"
            checked={remember && rememberable}
            disabled={!rememberable}
            onCheckedChange={(value) => setRemember(value === true)}
          />
          <div className="space-y-0.5">
            <Label htmlFor="ai-picker-remember" className={cn('text-sm', !rememberable && 'text-muted-foreground')}>
              Remember for {data.workflow_label}
            </Label>
            <p className="text-xs text-muted-foreground">
              {rememberable ? 'Makes this model the default for these tasks.' : 'This is already the default for these tasks.'}
            </p>
          </div>
        </div>

        <DialogFooter className="min-w-0 flex-col items-stretch gap-3 sm:flex-col sm:justify-start">
          <div className="flex min-w-0 flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={() => onSettle(null)}>
              Cancel
            </Button>
            <Button type="button" onClick={confirm} disabled={!choice} className="min-w-0">
              <Sparkles aria-hidden />
              <span className="truncate">{choice ? `Run with ${choice.label}` : 'Choose a model'}</span>
            </Button>
          </div>
          <Button
            type="button"
            variant="link"
            size="sm"
            className="h-auto self-start whitespace-normal px-0 text-left text-muted-foreground hover:text-foreground"
            onClick={dontAskAgain}
          >
            Don&apos;t ask again — always use my default
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default AiModelPickerDialog
