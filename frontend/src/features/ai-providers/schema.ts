import { z } from 'zod'

import type { AiErrorCode, CredentialRead, ProviderId, ProviderRead } from '@/features/ai-providers/types'

/** Client-side checks mirror the server's (`CredentialWrite`); the server stays the authority. */
export const apiKeySchema = z
  .string()
  .trim()
  .min(8, 'That key looks too short.')
  .max(512, 'That key is too long.')
  .regex(/^[\x21-\x7e]+$/, 'A key cannot contain spaces or non-ASCII characters.')

export const baseUrlSchema = z
  .string()
  .trim()
  .min(1, 'Enter the server address.')
  .max(500)
  .regex(/^https?:\/\//i, 'Start with http:// or https://.')

export const limitsSchema = z.object({
  daily_call_limit: z
    .union([z.literal(''), z.coerce.number().int('Use a whole number.').min(1, 'At least 1.').max(100_000)])
    .transform((v) => (v === '' ? null : v)),
  monthly_budget_usd: z
    .union([z.literal(''), z.coerce.number().min(0, 'Cannot be negative.').max(100_000)])
    .transform((v) => (v === '' ? null : Math.round(v * 100) / 100)),
})

export const ERROR_LABELS: Record<AiErrorCode | string, string> = {
  provider_not_configured: 'not set up',
  invalid_credentials: 'invalid key',
  quota_exceeded: 'quota or billing limit',
  model_unavailable: 'model unavailable',
  provider_timeout: 'timed out',
  budget_exceeded: 'usage limit reached',
  provider_error: 'provider error',
  invalid_base_url: 'invalid address',
}

export const PROVIDER_SHORT: Record<ProviderId, string> = {
  mock: 'Built-in rules',
  ollama: 'Ollama',
  openai: 'OpenAI',
  gemini: 'Gemini',
  anthropic: 'Anthropic',
  openai_compatible: 'OpenAI-compatible',
}

export type PillTone = 'success' | 'warning' | 'destructive' | 'muted' | 'secondary'

export interface StatusPill {
  label: string
  tone: PillTone
}

/** The status pill of a provider card. */
export function credentialPill(provider: ProviderRead, credential: CredentialRead | null): StatusPill {
  if (provider.id === 'mock') return { label: 'Always available', tone: 'secondary' }
  if (!provider.allowed) return { label: 'Disabled on this server', tone: 'muted' }
  if (!credential) {
    if (provider.is_server_default && (provider.server_key_configured || !provider.requires_key)) {
      return { label: 'Server default', tone: 'secondary' }
    }
    return { label: 'Not configured', tone: 'muted' }
  }
  if (credential.status === 'OK') {
    return { label: credential.last_latency_ms != null ? `Connected · ${credential.last_latency_ms} ms` : 'Connected', tone: 'success' }
  }
  if (credential.status === 'ERROR') {
    return { label: `Error: ${ERROR_LABELS[credential.last_error_code ?? ''] ?? 'failed'}`, tone: 'destructive' }
  }
  return { label: 'Untested', tone: 'warning' }
}

/** Whether the user can route work to this provider right now (mirrors `target_problem`). */
export function providerUsable(provider: ProviderRead): boolean {
  if (!provider.allowed) return false
  if (provider.id === 'mock' || provider.id === 'ollama') return true
  const credential = provider.credential
  if (provider.id === 'openai_compatible') return Boolean(credential?.base_url)
  if (credential?.has_key) return true
  return provider.is_server_default && provider.server_key_configured
}

export function formatUsd(value: number | null | undefined, digits = 4): string {
  if (value == null) return '—'
  if (value === 0) return '$0'
  if (value < 0.0001) return '< $0.0001'
  return `$${value.toFixed(value >= 1 ? 2 : digits)}`
}

export function formatPrice(value: number | null | undefined): string {
  if (value == null) return '?'
  if (value === 0) return 'free'
  return `$${value < 1 ? value.toFixed(2) : value.toFixed(2)}`
}
