import * as React from 'react'

import { useAiPickerStore } from '@/features/ai-providers/useAiChoice'

const AiModelPickerDialog = React.lazy(() => import('@/features/ai-providers/components/AiModelPickerDialog'))

/**
 * Mounted once (`App.tsx`). Renders the "Which model should process this?" dialog while an
 * AI action waits for a pick (`useAiChoice().runWithModel`). The dialog's code is loaded only
 * the first time it is needed, so the main chunk stays small.
 */
export function AiModelPickerHost() {
  const request = useAiPickerStore((state) => state.request)
  const settle = useAiPickerStore((state) => state.settle)
  if (!request) return null
  return (
    <React.Suspense fallback={null}>
      <AiModelPickerDialog key={request.id} request={request} onSettle={(result) => settle(request.id, result)} />
    </React.Suspense>
  )
}
