/**
 * Profile + job-preference react-query hooks (`GET/PUT /profile`, `GET/PUT /preferences/job`).
 *
 * Both endpoints are singletons for the signed-in user, so the cache holds exactly one
 * entry each and every mutation writes the server response straight back into it.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import type { JobPreferenceRead, JobPreferenceUpdate, ProfileRead, ProfileUpdate } from '@/types/api'

export function useProfile() {
  return useQuery({
    queryKey: qk.profile.detail,
    queryFn: () => api.get<ProfileRead>('/profile'),
  })
}

export function useUpdateProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: ProfileUpdate) => api.put<ProfileRead>('/profile', payload),
    onSuccess: (profile) => {
      queryClient.setQueryData(qk.profile.detail, profile)
    },
  })
}

export function useJobPreferences() {
  return useQuery({
    queryKey: qk.profile.jobPreferences,
    queryFn: () => api.get<JobPreferenceRead>('/preferences/job'),
  })
}

export function useUpdateJobPreferences() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: JobPreferenceUpdate) => api.put<JobPreferenceRead>('/preferences/job', payload),
    onSuccess: (preferences) => {
      queryClient.setQueryData(qk.profile.jobPreferences, preferences)
      // Matching and the job feed read these thresholds — let them refetch.
      void queryClient.invalidateQueries({ queryKey: qk.jobs.all })
      void queryClient.invalidateQueries({ queryKey: qk.matching.summary })
    },
  })
}
