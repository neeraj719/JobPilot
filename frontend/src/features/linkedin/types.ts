/** LinkedIn connection — mirrors `backend/app/modules/integrations/linkedin_schemas.py`. */

export type LinkedInStatusValue = 'not_connected' | 'pending' | 'connected' | 'expired' | 'revoked' | 'error'
export type LinkedInDiffAction = 'add' | 'replace' | 'same'
export type LinkedInDiffGroup = 'basics' | 'experience' | 'education' | 'skills' | 'certifications' | 'languages'

export interface LinkedInHistoryCounts {
  positions: number
  education: number
  skills: number
  certifications: number
  languages: number
}

export interface LinkedInDiffSummary {
  synced_at: string | null
  source: string | null
  adds: number
  replaces: number
  same: number
  changes: number
  trigger: string | null
}

export interface LinkedInStatus {
  configured: boolean
  dma_enabled: boolean
  status: LinkedInStatusValue
  connected: boolean
  name: string | null
  email: string | null
  picture_url: string | null
  locale: string | null
  scopes: string[]
  dma_granted: boolean
  dma_error: string | null
  connected_at: string | null
  token_expires_at: string | null
  last_synced_at: string | null
  auto_sync: boolean
  auto_sync_hours: number
  snapshot_source: 'oidc' | 'dma' | 'export' | null
  history_source: 'dma' | 'export' | null
  history_counts: LinkedInHistoryCounts
  export_imported_at: string | null
  export_stale: boolean
  export_stale_days: number
  last_error: string | null
  pending_changes: number
  last_sync_diff: LinkedInDiffSummary | null
}

/** A profile entry as stored on `UserProfile` (strings for skills/languages, objects otherwise). */
export type LinkedInValue = string | Record<string, string | null | undefined> | null

export interface LinkedInDiffRow {
  id: string
  field: string
  label: string
  group: LinkedInDiffGroup
  key: string | null
  current: LinkedInValue
  incoming: LinkedInValue
  action: LinkedInDiffAction
  default_selected: boolean
}

export interface LinkedInDiff {
  source: string | null
  history_source: 'dma' | 'export' | null
  rows: LinkedInDiffRow[]
  adds: number
  replaces: number
  same: number
  changes: number
}

export interface LinkedInSyncResult {
  status: LinkedInStatus
  diff: LinkedInDiff
  notes: string[]
}

export interface LinkedInApplyResult {
  applied: number
  fields: string[]
  skipped: string[]
  status: LinkedInStatus
  diff: LinkedInDiff
}

export interface LinkedInResumeRequest {
  name?: string | null
  target_role?: string | null
  template?: string | null
  set_default?: boolean
}
