/**
 * Standing answers (`GET/PUT/DELETE /profiles/standing-answers`): answers the user gave once
 * that the answer engine reuses on every application asking the same question.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import type { StandingAnswerRead, StandingAnswerUpsert, UUID } from '@/types/api'

/** Lives under the profile key, so anything that refreshes the profile refreshes these too. */
export const standingAnswersKey = [...qk.profile.detail, 'standing-answers'] as const

const PATH = '/profiles/standing-answers'

/** `{company}` in a stored wording stands for whichever employer asks it. */
export const COMPANY_PLACEHOLDER = '{company}'

export function useStandingAnswers() {
  return useQuery({
    queryKey: standingAnswersKey,
    queryFn: () => api.get<StandingAnswerRead[]>(PATH),
  })
}

export function useSaveStandingAnswer() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: StandingAnswerUpsert) => api.put<StandingAnswerRead>(PATH, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: standingAnswersKey })
    },
  })
}

export function useDeleteStandingAnswer() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: UUID) => api.delete(`${PATH}/${id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: standingAnswersKey })
    },
  })
}

/** Demographic questions are always answered per application — never offered for reuse. */
export function canRememberAnswer(questionKey: string, fieldType: string): boolean {
  if (fieldType === 'FILE') return false
  return !/demographic|gender|ethnic|race|disabilit|veteran|orientation|religion|caste|marital|pronoun/i.test(questionKey)
}
