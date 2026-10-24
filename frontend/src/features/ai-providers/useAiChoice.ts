/**
 * "Which model should process this?" — per-run model choice (`GET /ai/choices`).
 *
 * `useAiChoice(task)` loads the models the user can pick for one AI task and exposes
 * `runWithModel(fn)`: when the user asked to be asked (`mode === 'ask'`) and two or more
 * models are usable, the picker dialog opens (mounted once by `AiModelPickerHost`) and `fn`
 * runs with the chosen `{provider, model}`; otherwise `fn` runs at once with `undefined`
 * (the server routing applies). Cancelling the dialog does not run the action.
 *
 * When `/ai/choices` fails the action still runs with the default model, with a toast.
 */
import { type QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import { create } from 'zustand'

import { toast } from '@/components/ui/toaster'
import { api } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import type { AiChoice, AiChoicesResponse, AiSettingsPatch, AiSettingsRead, WorkflowTarget } from '@/features/ai-providers/types'

export const CHOICES_STALE_MS = 60_000

/** Task names the backend's AI calls use (`app/modules/ai/routing.py::TASK_WORKFLOWS`). */
export type AiTask =
  | 'polish_suggestions'
  | 'tailor_resume'
  | 'analyze_job_description'
  | 'parse_resume'
  | 'rewrite_bullet'
  | 'improve_grammar'
  | 'draft_summary'
  | 'general'

/** What the dialog says the run is and what it sends to the model. */
export const TASK_COPY: Record<AiTask, { label: string; sends: string }> = {
  polish_suggestions: { label: 'ATS suggestions', sends: 'Your resume and the job description' },
  tailor_resume: { label: 'Tailored resume', sends: 'Your resume and the job description' },
  analyze_job_description: { label: 'Job-description analysis', sends: 'The job description' },
  parse_resume: { label: 'Resume parsing', sends: 'Your resume text' },
  rewrite_bullet: { label: 'Bullet rewrite', sends: 'The bullet and its role' },
  improve_grammar: { label: 'Grammar and clarity', sends: 'The text you are editing' },
  draft_summary: { label: 'Summary draft', sends: 'The facts on your resume' },
  general: { label: 'AI task', sends: 'The text of this task' },
}

export function choiceTarget(choice: Pick<AiChoice, 'provider' | 'model'>): WorkflowTarget {
  return { provider: choice.provider, model: choice.model }
}

/** `qwen2.5:3b-instruct · local`, `gpt-4o-mini · hosted`, `Built-in rules`. */
export function choiceShortLabel(choice: Pick<AiChoice, 'provider' | 'model' | 'hosted'>): string {
  if (choice.provider === 'mock') return 'Built-in rules'
  const where = choice.provider === 'ollama' ? 'local' : choice.hosted ? 'hosted' : 'self-hosted'
  return `${choice.model} · ${where}`
}

/** Same wording for a `provider` / `model` pair stored on a result (analysis, rewrite). */
export function modelChipLabel(provider: string | null | undefined, model: string | null | undefined): string | null {
  if (!provider || !model || provider === 'mock') return null
  const hosted = provider === 'openai' || provider === 'gemini' || provider === 'anthropic'
  return choiceShortLabel({ provider: provider as AiChoice['provider'], model, hosted })
}

function choicesQuery(task: string) {
  return {
    queryKey: qk.aiProviders.choices(task),
    queryFn: () => api.get<AiChoicesResponse>('/ai/choices', { params: { task } }),
    staleTime: CHOICES_STALE_MS,
  }
}

export function useAiChoices(task: string, { enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({ ...choicesQuery(task), enabled, retry: 1 })
}

/**
 * `PATCH /ai/settings` outside a component's lifetime (the picker unmounts the moment the user
 * decides, and an Undo toast outlives it): updates the caches itself.
 */
export async function patchAiSettings(queryClient: QueryClient, payload: AiSettingsPatch): Promise<AiSettingsRead> {
  const settings = await api.patch<AiSettingsRead>('/ai/settings', payload)
  queryClient.setQueryData(qk.aiProviders.settings, settings)
  void queryClient.invalidateQueries({ queryKey: [...qk.aiProviders.all, 'choices'] })
  void queryClient.invalidateQueries({ queryKey: ['ai', 'status'] })
  return settings
}

/** `PATCH /ai/settings` — prompt mode and "remember for this workflow". */
export function usePatchAiSettings() {
  const queryClient = useQueryClient()
  return useMutation({ mutationFn: (payload: AiSettingsPatch) => patchAiSettings(queryClient, payload) })
}

/* ------------------------------------------------------------------ picker store */

/** `null` = cancelled (the action does not run); `{ai: undefined}` = run with the routing. */
export type PickerResult = { ai: WorkflowTarget | undefined } | null

export interface PickerRequest {
  id: number
  task: string
  data: AiChoicesResponse
  /** One line: what is sent, e.g. "Your resume and the job description". */
  context: string
  label: string
  resolve: (result: PickerResult) => void
}

interface PickerState {
  request: PickerRequest | null
  open: (request: Omit<PickerRequest, 'id' | 'resolve'>) => Promise<PickerResult>
  settle: (id: number, result: PickerResult) => void
}

let nextId = 1

export const useAiPickerStore = create<PickerState>((set, get) => ({
  request: null,
  open: (request) =>
    new Promise<PickerResult>((resolve) => {
      const previous = get().request
      if (previous) previous.resolve(null) // a second action cancels the first prompt
      set({ request: { ...request, id: nextId++, resolve } })
    }),
  settle: (id, result) => {
    const current = get().request
    if (!current || current.id !== id) return
    set({ request: null })
    current.resolve(result)
  },
}))

/* ------------------------------------------------------------------ the hook */

export interface UseAiChoiceOptions {
  /** Overrides the "what is sent" line of the dialog. */
  context?: string
  enabled?: boolean
}

export function useAiChoice(task: AiTask, { context, enabled = true }: UseAiChoiceOptions = {}) {
  const queryClient = useQueryClient()
  const query = useAiChoices(task, { enabled })
  const data = query.data
  const copy = TASK_COPY[task] ?? TASK_COPY.general

  const defaultChoice = React.useMemo(
    () => data?.candidates.find((c) => c.id === data.default) ?? data?.candidates[0] ?? null,
    [data],
  )
  const usable = React.useMemo(() => data?.candidates.filter((c) => c.available) ?? [], [data])

  const runWithModel = React.useCallback(
    async <T,>(fn: (ai?: WorkflowTarget) => Promise<T>): Promise<T | undefined> => {
      let choices: AiChoicesResponse
      try {
        choices = await queryClient.fetchQuery(choicesQuery(task))
      } catch {
        toast.message('Could not load your AI models', { description: 'Running with your default model.' })
        return fn(undefined)
      }
      if (!choices.should_ask) return fn(undefined)
      const result = await useAiPickerStore.getState().open({
        task,
        data: choices,
        context: context ?? copy.sends,
        label: copy.label,
      })
      if (result === null) return undefined
      return fn(result.ai)
    },
    [queryClient, task, context, copy.sends, copy.label],
  )

  return {
    query,
    data,
    defaultChoice,
    usable,
    /** Two or more usable models: the split button shows its chevron. */
    canChoose: usable.length >= 2,
    runWithModel,
  }
}
