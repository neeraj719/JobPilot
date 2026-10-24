import { MessageSquareMore } from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { toast } from '@/components/ui/toaster'
import { errorMessage } from '@/lib/api'
import type { AiSettingsRead, ModelPromptMode } from '@/features/ai-providers/types'
import { useAiChoices, usePatchAiSettings } from '@/features/ai-providers/useAiChoice'

const OPTIONS: { value: ModelPromptMode; label: string; hint: string }[] = [
  {
    value: 'ask',
    label: 'Ask me which model to use (when I have more than one)',
    hint: 'Every AI action opens a quick picker first. With only one usable model nothing is asked.',
  },
  {
    value: 'default',
    label: 'Always use my routing below',
    hint: 'AI actions run at once on the model each task is routed to. A button’s arrow still lets you pick another model once.',
  },
]

/** AI Model Settings › "Before each AI run": the `model_prompt_mode` switch. */
export function ModelPromptCard({ settings }: { settings: AiSettingsRead }) {
  const patch = usePatchAiSettings()
  const choices = useAiChoices('polish_suggestions')
  const usable = choices.data?.usable_count ?? null

  const change = (value: string) => {
    const mode = value as ModelPromptMode
    if (mode === settings.model_prompt_mode) return
    patch.mutate(
      { model_prompt_mode: mode },
      {
        onSuccess: () => toast.success(mode === 'ask' ? 'JobPilot will ask which model to use' : 'JobPilot will use your routing without asking'),
        onError: (error) => toast.error('Could not save that preference', { description: errorMessage(error) }),
      },
    )
  }

  return (
    <Card aria-labelledby="ai-prompt-mode-heading" data-testid="model-prompt-card">
      <CardHeader className="pb-3">
        <CardTitle id="ai-prompt-mode-heading" className="flex items-center gap-2">
          <MessageSquareMore className="size-4 text-primary" aria-hidden />
          Before each AI run
        </CardTitle>
        <CardDescription>
          Choose whether JobPilot asks which model should process each AI action.
          {usable !== null ? ` You have ${usable} usable ${usable === 1 ? 'model' : 'models'} right now.` : ''}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <RadioGroup value={settings.model_prompt_mode} onValueChange={change} aria-label="Before each AI run" className="gap-3" disabled={patch.isPending}>
          {OPTIONS.map((option) => (
            <div key={option.value} className="flex items-start gap-3 rounded-lg border border-border p-3 has-[button[data-state=checked]]:border-primary has-[button[data-state=checked]]:bg-primary/5">
              <RadioGroupItem value={option.value} id={`ai-prompt-${option.value}`} className="mt-0.5" aria-describedby={`ai-prompt-${option.value}-hint`} />
              <div className="space-y-0.5">
                <Label htmlFor={`ai-prompt-${option.value}`} className="text-sm font-medium">
                  {option.label}
                </Label>
                <p id={`ai-prompt-${option.value}-hint`} className="text-xs text-muted-foreground">
                  {option.hint}
                </p>
              </div>
            </div>
          ))}
        </RadioGroup>
      </CardContent>
    </Card>
  )
}

/** One line for the Resume Dashboard's AI model card. */
export function AiPromptModeNote({ mode }: { mode: ModelPromptMode | undefined }) {
  if (!mode) return null
  return (
    <p className="text-xs text-muted-foreground" data-testid="ai-prompt-mode-note">
      {mode === 'ask' ? 'Asks which model to use before each AI run (when you have more than one).' : 'Runs on your routing without asking.'}
    </p>
  )
}
