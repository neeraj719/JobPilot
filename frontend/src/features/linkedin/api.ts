/**
 * LinkedIn connection hooks (`/integrations/linkedin`, `/resumes/from-linkedin`).
 *
 * Nothing here ever sees a token: the backend keeps them encrypted and the status endpoint
 * returns only identity, scopes, timestamps and counts.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import { invalidateResumeCaches } from '@/features/resume-studio/api'
import type { StudioResumeRead } from '@/features/resume-studio/types'
import type { AuthorizationUrlResponse } from '@/types/api'

import type {
  LinkedInApplyResult,
  LinkedInResumeRequest,
  LinkedInStatus,
  LinkedInSyncResult,
} from './types'

const BASE = '/integrations/linkedin'

export function useLinkedIn() {
  return useQuery({
    queryKey: qk.linkedin.status,
    queryFn: () => api.get<LinkedInStatus>(BASE),
  })
}

/** The stored snapshot diffed against the profile right now (no LinkedIn call). */
export function useLinkedInDiff(enabled: boolean) {
  return useQuery({
    queryKey: qk.linkedin.diff,
    queryFn: () => api.get<LinkedInSyncResult>(`${BASE}/diff`),
    enabled,
  })
}

function useStoreResult() {
  const queryClient = useQueryClient()
  return (result: LinkedInSyncResult) => {
    queryClient.setQueryData(qk.linkedin.status, result.status)
    queryClient.setQueryData(qk.linkedin.diff, result)
  }
}

export function useConnectLinkedIn() {
  return useMutation({
    mutationFn: () => api.post<AuthorizationUrlResponse>(`${BASE}/connect`),
  })
}

export function useSyncLinkedIn() {
  const store = useStoreResult()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<LinkedInSyncResult>(`${BASE}/sync`),
    onSuccess: store,
    // A failed sync can still change the status (expired / revoked): show it.
    onError: () => void queryClient.invalidateQueries({ queryKey: qk.linkedin.status }),
  })
}

export function useAddLinkedInExport() {
  const store = useStoreResult()
  return useMutation({
    mutationFn: (files: File[]) => {
      const form = new FormData()
      for (const file of files) form.append('files', file)
      return api.upload<LinkedInSyncResult>(`${BASE}/export`, form)
    },
    onSuccess: store,
  })
}

export function useApplyLinkedIn() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (changeIds: string[]) => api.post<LinkedInApplyResult>(`${BASE}/apply`, { change_ids: changeIds }),
    onSuccess: (result) => {
      queryClient.setQueryData(qk.linkedin.status, result.status)
      void queryClient.invalidateQueries({ queryKey: qk.linkedin.diff })
      void queryClient.invalidateQueries({ queryKey: qk.profile.detail })
      void queryClient.invalidateQueries({ queryKey: qk.resumeStudio.prefill })
    },
  })
}

export function useUpdateLinkedIn() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { auto_sync: boolean }) => api.patch<LinkedInStatus>(BASE, body),
    onSuccess: (status) => queryClient.setQueryData(qk.linkedin.status, status),
  })
}

export function useDisconnectLinkedIn() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.delete<LinkedInStatus>(BASE),
    onSuccess: (status) => {
      queryClient.setQueryData(qk.linkedin.status, status)
      queryClient.removeQueries({ queryKey: qk.linkedin.diff })
    },
  })
}

export function useCreateResumeFromLinkedIn() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: LinkedInResumeRequest = {}) => api.post<StudioResumeRead>('/resumes/from-linkedin', body),
    onSuccess: (resume) => invalidateResumeCaches(queryClient, resume.id),
  })
}
