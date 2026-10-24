import { Cpu } from 'lucide-react'

import { cn } from '@/lib/utils'
import { modelChipLabel } from '@/features/ai-providers/useAiChoice'

/** "qwen2.5:3b-instruct · local" — which model produced a result (nothing for rules-only). */
export function AiModelChip({ provider, model, className, prefix = 'AI model' }: { provider?: string | null; model?: string | null; className?: string; prefix?: string }) {
  const label = modelChipLabel(provider, model)
  if (!label) return null
  return (
    <span
      className={cn(
        'inline-flex max-w-full items-center gap-1 rounded-full border border-ai/25 bg-ai-soft px-2 py-0.5 text-2xs font-medium text-ai-soft-foreground',
        className,
      )}
      data-testid="ai-model-chip"
      title={`${prefix}: ${provider} · ${model}`}
    >
      <Cpu className="size-3 shrink-0" aria-hidden />
      <span className="sr-only">{prefix}: </span>
      <span className="truncate">{label}</span>
    </span>
  )
}
