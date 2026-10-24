/** Types of the AI Model Settings API (`/api/v1/ai/...`, `backend/app/modules/ai/settings_schemas.py`). */

export type ProviderId = 'mock' | 'ollama' | 'openai' | 'gemini' | 'anthropic' | 'openai_compatible'
export type WorkflowId = 'generation' | 'analysis' | 'rewriting' | 'jd_analysis' | 'review' | 'general'
export type UsageRange = '7d' | '30d' | 'month'
export type CredentialStatus = 'UNTESTED' | 'OK' | 'ERROR'
/** `ask`: ask which model to use before each AI run (when 2+ are usable); `default`: never ask. */
export type ModelPromptMode = 'ask' | 'default'

/** Error codes the runtime and the connection test report. */
export type AiErrorCode =
  | 'provider_not_configured'
  | 'invalid_credentials'
  | 'quota_exceeded'
  | 'model_unavailable'
  | 'provider_timeout'
  | 'budget_exceeded'
  | 'provider_error'

export interface CredentialRead {
  provider: ProviderId
  has_key: boolean
  /** `••••1234` — a stored key is never returned. */
  masked_key: string | null
  base_url: string | null
  credential_version: number
  status: CredentialStatus
  last_tested_at: string | null
  last_latency_ms: number | null
  last_error: string | null
  last_error_code: string | null
  rotated_at: string | null
  updated_at: string | null
}

export interface CredentialWrite {
  api_key?: string | null
  base_url?: string | null
}

export interface ProviderRead {
  id: ProviderId
  name: string
  kind: 'builtin' | 'local' | 'hosted' | 'self_hosted'
  hosted: boolean
  requires_key: boolean
  supports_base_url: boolean
  default_model: string | null
  docs_url: string | null
  key_url: string | null
  prices_as_of: string | null
  privacy_note: string
  billing_note: string | null
  supports_live_models: boolean
  description: string
  capabilities: Record<string, unknown>
  allowed: boolean
  is_server_default: boolean
  server_key_configured: boolean
  credential: CredentialRead | null
}

export interface WorkflowTarget {
  provider: ProviderId
  model: string
}

export interface ProvidersResponse {
  providers: ProviderRead[]
  workflows: { id: WorkflowId; label: string }[]
  server_default: WorkflowTarget
  billing_note: string
  hosted_allowed: boolean
}

export interface EffectiveTarget {
  provider: ProviderId
  model: string
  source: 'task_override' | 'user_default' | 'server_default' | 'fallback'
  usable: boolean
  problem: string | null
}

export interface AiSettingsRead {
  default_provider: ProviderId | null
  default_model: string | null
  workflow_models: Partial<Record<WorkflowId, WorkflowTarget>>
  fallback_enabled: boolean
  fallback_provider: ProviderId | null
  fallback_model: string | null
  daily_call_limit: number | null
  monthly_budget_usd: number | null
  data_residency_ack: boolean
  model_prompt_mode: ModelPromptMode
  effective: Record<WorkflowId, EffectiveTarget>
  fallback: EffectiveTarget | null
  server_default: WorkflowTarget
  hosted_allowed: boolean
  credentials: CredentialRead[]
  summary: string
  status: { provider: ProviderId; model: string; source: string; configured: boolean; problem: string | null; hosted: boolean }
  updated_at: string | null
}

export interface AiSettingsUpdate {
  default_provider: ProviderId | null
  default_model: string | null
  workflow_models: Partial<Record<WorkflowId, WorkflowTarget>>
  fallback_enabled: boolean
  fallback_provider: ProviderId | null
  fallback_model: string | null
  daily_call_limit: number | null
  monthly_budget_usd: number | null
  data_residency_ack: boolean
  /** Omitted = keep the stored mode. */
  model_prompt_mode?: ModelPromptMode
}

/** `PATCH /ai/settings` — what the model picker changes; everything else is kept. */
export interface AiSettingsPatch {
  model_prompt_mode?: ModelPromptMode
  remember?: { workflow: WorkflowId; provider: ProviderId; model: string }
}

/** One model the user can pick for a run (`GET /ai/choices`). */
export interface AiChoice {
  /** `"<provider>:<model>"` */
  id: string
  provider: ProviderId
  provider_name: string
  model: string
  label: string
  source: 'workflow_default' | 'user_default' | 'server_default' | 'credential' | 'local'
  is_default: boolean
  hosted: boolean
  privacy_note: string
  /** `free, local` | `≈ $x per 1k tokens` | `unknown` */
  cost_hint: string
  available: boolean
  unavailable_reason: string | null
  last_used_at: string | null
}

export interface AiChoicesResponse {
  task: string
  workflow: WorkflowId
  workflow_label: string
  mode: ModelPromptMode
  default: string
  candidates: AiChoice[]
  usable_count: number
  should_ask: boolean
}

export interface ModelRow {
  id: string
  display_name: string
  in_registry: boolean
  pricing_known: boolean
  input_per_m_usd: number | null
  output_per_m_usd: number | null
  context_window: number | null
  json_mode: boolean
  vision: boolean
  recommended_for: string[]
  group: 'recommended' | 'other' | 'unknown_pricing'
  available: boolean | null
  notes: string | null
}

export interface ModelsResponse {
  provider: ProviderId
  models: ModelRow[]
  live: boolean
  fetched_at: string | null
  error_code: string | null
  error: string | null
  prices_as_of: string | null
}

export interface ConnectionTestResult {
  provider: ProviderId
  ok: boolean
  model: string | null
  model_available: boolean | null
  latency_ms: number | null
  error_code: string | null
  error: string | null
  tested_at: string
  credential: CredentialRead | null
}

export interface UsageTotals {
  calls: number
  ok: number
  errors: number
  fallbacks: number
  input_tokens: number
  output_tokens: number
  estimated_cost_usd: number
  cost_unknown_calls: number
  tokens_estimated_calls: number
  avg_duration_ms: number | null
}

export interface UsageGroup extends UsageTotals {
  key: string
  label: string | null
  provider: string | null
  model: string | null
}

export interface UsageDay {
  date: string
  calls: number
  errors: number
  estimated_cost_usd: number
  tokens: number
}

export interface UsageResponse {
  range: UsageRange
  since: string
  totals: UsageTotals
  by_workflow: UsageGroup[]
  by_provider: UsageGroup[]
  daily: UsageDay[]
  estimated: boolean
  prices_as_of: Record<string, string>
  limits: {
    daily_call_limit?: number | null
    monthly_budget_usd?: number | null
    server_daily_limit_hosted?: number | null
    calls_today?: number
    spent_this_month_usd?: number
  }
  note: string
}
