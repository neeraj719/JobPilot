import * as React from 'react'

import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { useProviderModels } from '@/features/ai-providers/api'
import { formatPrice } from '@/features/ai-providers/schema'
import type { ModelRow, ProviderId } from '@/features/ai-providers/types'

const GROUP_LABELS: Record<ModelRow['group'], string> = {
  recommended: 'Recommended',
  other: 'Other models',
  unknown_pricing: 'Not in registry — pricing unknown',
}

export function modelPriceLabel(model: ModelRow): string {
  if (!model.pricing_known) return 'pricing unknown'
  if (model.input_per_m_usd === 0 && model.output_per_m_usd === 0) return 'free'
  return `${formatPrice(model.input_per_m_usd)} / ${formatPrice(model.output_per_m_usd)} per 1M tokens`
}

interface ModelSelectProps {
  provider: ProviderId
  value: string | null
  onChange: (model: string) => void
  id?: string
  disabled?: boolean
  'aria-label'?: string
  className?: string
}

/**
 * Models of one provider, grouped as recommended / other / unknown pricing. A model the live
 * list says this key cannot use is shown disabled. OpenAI-compatible servers have no
 * registry, so their model is typed.
 */
export function ModelSelect({ provider, value, onChange, id, disabled, className, ...rest }: ModelSelectProps) {
  const models = useProviderModels(provider, { enabled: provider !== 'openai_compatible' })

  if (provider === 'openai_compatible') {
    return (
      <Input
        id={id}
        className={className}
        value={value ?? ''}
        placeholder="Model name on your server"
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        aria-label={rest['aria-label']}
        maxLength={200}
      />
    )
  }

  const rows = models.data?.models ?? []
  const groups = (['recommended', 'other', 'unknown_pricing'] as const)
    .map((group) => ({ group, items: rows.filter((m) => m.group === group) }))
    .filter((g) => g.items.length > 0)
  const known = rows.some((m) => m.id === value)

  return (
    <Select value={value ?? undefined} onValueChange={onChange} disabled={disabled || models.isLoading}>
      <SelectTrigger id={id} className={className} aria-label={rest['aria-label']}>
        <SelectValue
          placeholder={
            models.isLoading ? (
              <span role="status" className="flex items-center">
                <Skeleton className="h-3.5 w-28" />
                <span className="sr-only">Loading models</span>
              </span>
            ) : (
              'Choose a model'
            )
          }
        />
      </SelectTrigger>
      <SelectContent>
        {value && !known ? (
          <SelectItem value={value}>{value}</SelectItem>
        ) : null}
        {groups.map(({ group, items }, index) => (
          <React.Fragment key={group}>
            {index > 0 ? <SelectSeparator /> : null}
            <SelectGroup>
              <SelectLabel className="text-xs text-muted-foreground">{GROUP_LABELS[group]}</SelectLabel>
              {items.map((model) => (
                <SelectItem key={model.id} value={model.id} disabled={model.available === false}>
                  <span className="flex flex-col">
                    <span>
                      {model.display_name}
                      {model.display_name !== model.id ? <span className="ml-1 text-xs text-muted-foreground">({model.id})</span> : null}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {model.available === false ? 'not available to this key · ' : ''}
                      {modelPriceLabel(model)}
                    </span>
                  </span>
                </SelectItem>
              ))}
            </SelectGroup>
          </React.Fragment>
        ))}
        {rows.length === 0 && !models.isLoading ? (
          <div className="px-2 py-1.5 text-xs text-muted-foreground">No models found — test the connection first.</div>
        ) : null}
      </SelectContent>
    </Select>
  )
}
