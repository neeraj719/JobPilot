/**
 * Typed fetch client for the JobPilot API.
 *
 * Responsibilities:
 *  - prefix every path with `VITE_API_BASE_URL` (default `/api/v1`, proxied by Vite in dev)
 *  - attach the access token from the auth store as a `Bearer` header
 *  - on a 401 for a request that carried a token, call `POST /auth/refresh` **once**
 *    (the refresh token lives in an HttpOnly cookie, hence `credentials: 'include'`),
 *    update the store and retry the original request
 *  - normalise error bodies (`{"error": {code, message, details}}`) into `ApiError`
 *  - leave a `401 reauth_required` alone: it asks for the password again (sensitive
 *    actions), and answering it with a refreshed token would defeat the check
 *
 * The auth wiring is injected by `src/stores/auth.ts` via `configureApiAuth` so that this
 * module stays free of store imports (no circular dependency).
 */
import type { ApiErrorBody, TokenResponse } from '@/types/api'

export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

export type QueryValue = string | number | boolean | Date | null | undefined | (string | number | boolean)[]
export type QueryParams = Record<string, QueryValue>

export interface RequestOptions extends Omit<RequestInit, 'body' | 'method'> {
  /** Serialised onto the query string; `undefined`, `null` and `''` are dropped. */
  params?: QueryParams
  /** Skip the Authorization header (used by login/register/refresh). */
  skipAuth?: boolean
  /** Skip the transparent refresh-and-retry dance (used by the refresh call itself). */
  skipRefresh?: boolean
}

/** Every non-2xx response is thrown as one of these. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details?: unknown

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }

  /** 4xx errors are the user's problem to fix; retrying them is pointless. */
  get isClientError(): boolean {
    return this.status >= 400 && this.status < 500
  }

  get isAuthError(): boolean {
    return this.status === 401 || this.status === 403
  }

  get isNotFound(): boolean {
    return this.status === 404
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}

/**
 * 401 codes that mean "this request needs something more", not "the session is over":
 * no refresh-and-retry, and the user is not signed out.
 *  - `reauth_required`: a sensitive action wants the password again (or a fresh sign-in).
 *  - `invalid_credentials`: e.g. a wrong *current* password in the change-password form.
 */
const NON_SESSION_401_CODES = new Set(['reauth_required', 'invalid_credentials'])

/** True when the API asks the user to confirm their password before a sensitive action. */
export function isReauthRequired(error: unknown): boolean {
  return isApiError(error) && error.status === 401 && error.code === 'reauth_required'
}

/** Header carrying the current password for a sensitive action (see `require_recent_auth`). */
export const REAUTH_HEADER = 'X-Reauth-Password'

/**
 * Headers for re-authentication. Header values must be Latin-1 and lose surrounding
 * whitespace, so anything beyond printable ASCII is sent percent-encoded (UTF-8); the
 * server accepts both. The password goes straight into this one request and is not kept.
 */
export function reauthHeaders(password: string): Record<string, string> {
  const plain = /^[\x21-\x7e]*$/.test(password)
  return { [REAUTH_HEADER]: plain ? password : encodeURIComponent(password) }
}

/** Best-effort human-readable message for any thrown value. */
export function errorMessage(error: unknown, fallback = 'Something went wrong. Please try again.'): string {
  if (isApiError(error)) return error.message || fallback
  if (error instanceof Error) return error.message || fallback
  if (typeof error === 'string' && error) return error
  return fallback
}

/* ------------------------------------------------------------------ */
/* Auth wiring (installed by the auth store)                           */
/* ------------------------------------------------------------------ */

interface ApiAuthBridge {
  getToken: () => string | null
  onTokenRefreshed: (token: string, response: TokenResponse) => void
  onAuthFailure: () => void
}

let authBridge: ApiAuthBridge = {
  getToken: () => null,
  onTokenRefreshed: () => undefined,
  onAuthFailure: () => undefined,
}

export function configureApiAuth(bridge: Partial<ApiAuthBridge>): void {
  authBridge = { ...authBridge, ...bridge }
}

/* ------------------------------------------------------------------ */
/* URL building                                                        */
/* ------------------------------------------------------------------ */

export function buildQueryString(params?: QueryParams): string {
  if (!params) return ''
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    if (Array.isArray(value)) {
      for (const item of value) {
        if (item === undefined || item === null || item === '') continue
        search.append(key, String(item))
      }
      continue
    }
    search.append(key, value instanceof Date ? value.toISOString() : String(value))
  }
  const qs = search.toString()
  return qs ? `?${qs}` : ''
}

export function buildUrl(path: string, params?: QueryParams): string {
  const base = API_BASE_URL.replace(/\/+$/, '')
  const suffix = path.startsWith('/') ? path : `/${path}`
  return `${base}${suffix}${buildQueryString(params)}`
}

/* ------------------------------------------------------------------ */
/* Response handling                                                   */
/* ------------------------------------------------------------------ */

function looksLikeErrorBody(body: unknown): body is ApiErrorBody {
  return (
    typeof body === 'object' &&
    body !== null &&
    'error' in body &&
    typeof (body as ApiErrorBody).error === 'object' &&
    (body as ApiErrorBody).error !== null
  )
}

async function toApiError(response: Response): Promise<ApiError> {
  let body: unknown = null
  try {
    const text = await response.text()
    body = text ? JSON.parse(text) : null
  } catch {
    body = null
  }

  if (looksLikeErrorBody(body)) {
    const { code, message, details } = body.error
    return new ApiError(response.status, code || 'error', message || response.statusText, details)
  }

  // FastAPI request-validation errors: {"detail": [...]}
  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    const message = typeof detail === 'string' ? detail : 'The request could not be validated.'
    return new ApiError(response.status, 'validation_error', message, detail)
  }

  return new ApiError(response.status, `http_${response.status}`, response.statusText || 'Request failed', body)
}

/** The `error.code` of an error response, read from a clone so the body stays readable. */
async function peekErrorCode(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.clone().json()
    return looksLikeErrorBody(body) ? (body.error.code ?? null) : null
  } catch {
    return null
  }
}

async function parseBody<T>(response: Response): Promise<T> {
  if (response.status === 204 || response.status === 205) return undefined as T
  const contentType = response.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) {
    const text = await response.text()
    return (text ? JSON.parse(text) : undefined) as T
  }
  if (contentType.startsWith('text/')) {
    return (await response.text()) as unknown as T
  }
  return (await response.blob()) as unknown as T
}

/* ------------------------------------------------------------------ */
/* Refresh (single-flight)                                             */
/* ------------------------------------------------------------------ */

let refreshInFlight: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight

  refreshInFlight = (async () => {
    try {
      const response = await fetch(buildUrl('/auth/refresh'), {
        method: 'POST',
        credentials: 'include',
        headers: { Accept: 'application/json' },
      })
      if (!response.ok) return null
      const token = await parseBody<TokenResponse>(response)
      if (!token?.access_token) return null
      authBridge.onTokenRefreshed(token.access_token, token)
      return token.access_token
    } catch {
      return null
    } finally {
      // Release the lock on the next tick so concurrent callers all observe the result.
      setTimeout(() => {
        refreshInFlight = null
      }, 0)
    }
  })()

  return refreshInFlight
}

/* ------------------------------------------------------------------ */
/* Core request                                                        */
/* ------------------------------------------------------------------ */

type Body = unknown

function buildInit(method: string, body: Body, options: RequestOptions, token: string | null): RequestInit {
  const headers = new Headers(options.headers)
  headers.set('Accept', 'application/json')
  if (token && !options.skipAuth) headers.set('Authorization', `Bearer ${token}`)

  let payload: BodyInit | undefined
  if (body instanceof FormData || body instanceof Blob) {
    // Let the browser set the multipart boundary / blob content type.
    payload = body
  } else if (body !== undefined && body !== null) {
    headers.set('Content-Type', 'application/json')
    payload = JSON.stringify(body)
  }

  const { params: _params, skipAuth: _skipAuth, skipRefresh: _skipRefresh, ...rest } = options
  void _params
  void _skipAuth
  void _skipRefresh

  return {
    ...rest,
    method,
    headers,
    body: payload,
    credentials: rest.credentials ?? 'include',
  }
}

async function request<T>(method: string, path: string, body?: Body, options: RequestOptions = {}): Promise<T> {
  const url = buildUrl(path, options.params)
  const token = options.skipAuth ? null : authBridge.getToken()

  let response: Response
  try {
    response = await fetch(url, buildInit(method, body, options, token))
  } catch (cause) {
    throw new ApiError(0, 'network_error', 'Cannot reach the JobPilot API. Check your connection.', cause)
  }

  if (
    response.status === 401 &&
    !options.skipRefresh &&
    !options.skipAuth &&
    token &&
    !NON_SESSION_401_CODES.has((await peekErrorCode(response)) ?? '')
  ) {
    const fresh = await refreshAccessToken()
    if (fresh) {
      try {
        response = await fetch(url, buildInit(method, body, { ...options, skipRefresh: true }, fresh))
      } catch (cause) {
        throw new ApiError(0, 'network_error', 'Cannot reach the JobPilot API. Check your connection.', cause)
      }
    } else {
      authBridge.onAuthFailure()
    }
  }

  if (!response.ok) {
    const error = await toApiError(response)
    if (error.status === 401 && !options.skipAuth && !NON_SESSION_401_CODES.has(error.code)) {
      authBridge.onAuthFailure()
    }
    throw error
  }

  return parseBody<T>(response)
}

/* ------------------------------------------------------------------ */
/* Public surface                                                      */
/* ------------------------------------------------------------------ */

export const api = {
  baseUrl: API_BASE_URL,

  get: <T>(path: string, options?: RequestOptions): Promise<T> => request<T>('GET', path, undefined, options),

  post: <T>(path: string, body?: Body, options?: RequestOptions): Promise<T> =>
    request<T>('POST', path, body, options),

  put: <T>(path: string, body?: Body, options?: RequestOptions): Promise<T> => request<T>('PUT', path, body, options),

  patch: <T>(path: string, body?: Body, options?: RequestOptions): Promise<T> =>
    request<T>('PATCH', path, body, options),

  delete: <T = void>(path: string, options?: RequestOptions): Promise<T> =>
    request<T>('DELETE', path, undefined, options),

  /** Multipart upload — do not set Content-Type yourself. */
  upload: <T>(path: string, form: FormData, options?: RequestOptions): Promise<T> =>
    request<T>('POST', path, form, options),

  /** Fetch a file (resume, screenshot, export) as a Blob. */
  download: (path: string, options?: RequestOptions): Promise<Blob> =>
    request<Blob>('GET', path, undefined, options),

  /** Absolute URL for a path — handy for `<a download>` / `<img src>`. */
  url: (path: string, params?: QueryParams): string => buildUrl(path, params),
}

/** Trigger a browser download for a Blob returned by `api.download`. */
export function saveBlob(blob: Blob, filename: string): void {
  const href = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = href
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(href)
}

export default api
