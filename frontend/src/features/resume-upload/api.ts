/**
 * "Upload my original resume" — hooks for the uploaded-resume endpoints
 * (`backend/app/modules/resumes/router_upload.py`) and an upload that reports real progress.
 *
 * `api.upload` is `fetch`, which has no upload progress, so the two file uploads here use
 * `XMLHttpRequest` with the same bearer token, error shape (`ApiError`) and one
 * refresh-and-retry on an expired token.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'

import { api, ApiError, buildUrl, saveBlob } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import { getAccessToken } from '@/stores/auth'
import { invalidateResumeCaches } from '@/features/resume-studio/api'
import type { ResumeRead } from '@/types/api'

import type { ResumeFileInfo, UploadProgress } from './types'

export const fileInfoKey = (id: string) => [...qk.resumes.detail(id), 'file-info'] as const

function toApiError(xhr: XMLHttpRequest): ApiError {
  let body: unknown = null
  try {
    body = xhr.responseText ? JSON.parse(xhr.responseText) : null
  } catch {
    body = null
  }
  if (body && typeof body === 'object' && 'error' in body) {
    const error = (body as { error: { code?: string; message?: string; details?: unknown } }).error
    return new ApiError(xhr.status, error.code || 'error', error.message || 'Upload failed', error.details)
  }
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    return new ApiError(xhr.status, 'validation_error', typeof detail === 'string' ? detail : 'The upload could not be validated.', detail)
  }
  if (xhr.status === 413) return new ApiError(413, 'file_too_large', 'That file is too large.')
  return new ApiError(xhr.status, `http_${xhr.status}`, xhr.statusText || 'Upload failed')
}

function sendOnce<T>(
  path: string,
  form: FormData,
  onProgress: (progress: UploadProgress) => void,
  signal?: AbortSignal,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', buildUrl(path))
    xhr.withCredentials = true
    xhr.setRequestHeader('Accept', 'application/json')
    const token = getAccessToken()
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return
      const percent = Math.min(100, Math.round((event.loaded / event.total) * 100))
      onProgress({ percent, phase: percent >= 100 ? 'reading' : 'uploading' })
    }
    // All bytes are on the server: it now extracts and parses the file.
    xhr.upload.onload = () => onProgress({ percent: 100, phase: 'reading' })
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as T)
        } catch {
          reject(new ApiError(xhr.status, 'bad_response', 'The server sent an unreadable answer.'))
        }
      } else {
        reject(toApiError(xhr))
      }
    }
    xhr.onerror = () => reject(new ApiError(0, 'network_error', 'Cannot reach the JobPilot API. Check your connection.'))
    xhr.onabort = () => reject(new ApiError(0, 'aborted', 'Upload cancelled.'))
    if (signal) {
      if (signal.aborted) return xhr.abort()
      signal.addEventListener('abort', () => xhr.abort(), { once: true })
    }
    onProgress({ percent: 0, phase: 'uploading' })
    xhr.send(form)
  })
}

/** POST a multipart form with upload progress; an expired token is refreshed once (through `api`) and retried. */
export async function postWithProgress<T>(
  path: string,
  form: FormData,
  onProgress: (progress: UploadProgress) => void,
  signal?: AbortSignal,
): Promise<T> {
  try {
    return await sendOnce<T>(path, form, onProgress, signal)
  } catch (error) {
    const expired = error instanceof ApiError && error.status === 401 && error.code !== 'reauth_required'
    if (!expired) throw error
    // `api` owns the single-flight refresh; any authenticated call triggers it.
    await api.get('/auth/me')
    return sendOnce<T>(path, form, onProgress, signal)
  }
}

export interface UploadInput {
  file: File
  name?: string
  targetRole?: string | null
  setDefault?: boolean
  /** The model picked for the parse (`useAiChoice('parse_resume').runWithModel`), sent as `ai_provider` / `ai_model`. */
  ai?: { provider: string; model: string } | null
}

const IDLE: UploadProgress = { percent: null, phase: 'idle' }

function useProgressState() {
  const [progress, setProgress] = React.useState<UploadProgress>(IDLE)
  const controller = React.useRef<AbortController | null>(null)
  const start = () => {
    controller.current?.abort()
    controller.current = new AbortController()
    return controller.current.signal
  }
  const cancel = () => controller.current?.abort()
  React.useEffect(() => () => controller.current?.abort(), [])
  return { progress, setProgress, start, cancel, reset: () => setProgress(IDLE) }
}

/** `POST /resumes` (the existing upload) with real progress. */
export function useUploadOriginal() {
  const queryClient = useQueryClient()
  const state = useProgressState()
  const mutation = useMutation({
    mutationFn: ({ file, name, targetRole, setDefault, ai }: UploadInput) => {
      const form = new FormData()
      form.append('file', file)
      if (name) form.append('name', name)
      if (targetRole) form.append('target_role', targetRole)
      form.append('set_default', String(Boolean(setDefault)))
      if (ai?.provider) form.append('ai_provider', ai.provider)
      if (ai?.model) form.append('ai_model', ai.model)
      return postWithProgress<ResumeRead>('/resumes', form, state.setProgress, state.start())
    },
    onSuccess: (resume) => {
      invalidateResumeCaches(queryClient, resume.id)
      void queryClient.invalidateQueries({ queryKey: qk.profile.detail })
    },
    onSettled: () => state.reset(),
  })
  return { ...mutation, progress: state.progress, cancel: state.cancel }
}

/** `POST /resumes/{id}/file` — replace the original file; the server saves a new version. */
export function useReplaceFile(id: string) {
  const queryClient = useQueryClient()
  const state = useProgressState()
  const mutation = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return postWithProgress<ResumeRead>(`/resumes/${id}/file`, form, state.setProgress, state.start())
    },
    onSuccess: (resume) => {
      queryClient.setQueryData(qk.resumes.detail(resume.id), resume)
      invalidateResumeCaches(queryClient, resume.id)
      void queryClient.invalidateQueries({ queryKey: qk.resumes.detail(resume.id) })
    },
    onSettled: () => state.reset(),
  })
  return { ...mutation, progress: state.progress, cancel: state.cancel }
}

/** `GET /resumes/{id}/file-info`. Lives under `['resumes', id]`, so every resume invalidation refreshes it. */
export function useFileInfo(id: string | undefined, enabled = true) {
  return useQuery({
    queryKey: fileInfoKey(id ?? 'none'),
    queryFn: () => api.get<ResumeFileInfo>(`/resumes/${id}/file-info`),
    enabled: Boolean(id) && enabled,
  })
}

/** `POST /resumes/{id}/edit-copy` — a CREATED copy for the editor; the uploaded original is never changed. */
export function useEditCopy() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name?: string }) => api.post<ResumeRead>(`/resumes/${id}/edit-copy`, name ? { name } : {}),
    onSuccess: (resume) => invalidateResumeCaches(queryClient, resume.id),
  })
}

/** Download the original file exactly as uploaded. */
export async function downloadOriginal(resume: Pick<ResumeRead, 'id' | 'original_filename'>): Promise<void> {
  const blob = await api.download(`/resumes/${resume.id}/file`, { params: { disposition: 'attachment' } })
  saveBlob(blob, resume.original_filename || 'resume')
}

/**
 * A `blob:` URL of the original file for the inline preview. The file is fetched with the
 * bearer token (an `<iframe src>` cannot send it) and the URL is revoked on unmount or when
 * the resume's version changes (a replaced file). Not cached by react-query on purpose.
 */
export function useOriginalFileUrl(id: string, version: number, enabled: boolean) {
  const [state, setState] = React.useState<{ url: string | null; error: unknown; loading: boolean }>({
    url: null,
    error: null,
    loading: enabled,
  })
  const [attempt, setAttempt] = React.useState(0)
  React.useEffect(() => {
    if (!enabled) {
      setState({ url: null, error: null, loading: false })
      return
    }
    let url: string | null = null
    let alive = true
    setState({ url: null, error: null, loading: true })
    api
      .download(`/resumes/${id}/file`, { params: { disposition: 'inline' } })
      .then((blob) => {
        if (!alive) return
        url = URL.createObjectURL(blob.type ? blob : new Blob([blob], { type: 'application/pdf' }))
        setState({ url, error: null, loading: false })
      })
      .catch((error: unknown) => alive && setState({ url: null, error, loading: false }))
    return () => {
      alive = false
      if (url) URL.revokeObjectURL(url)
    }
  }, [id, version, enabled, attempt])
  return { ...state, retry: () => setAttempt((n) => n + 1) }
}
