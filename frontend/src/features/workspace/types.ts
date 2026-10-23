/** Workspace API shapes (`/api/v1/workspace`, `backend/app/modules/workspace/schemas.py`). */

export type ModuleStatus = 'AVAILABLE' | 'COMING_SOON'
export type ModuleMinRole = 'USER' | 'ADMIN'
/**
 * Why a visible module cannot be opened, in the order the server checks them: switched off
 * platform-wide, not finished, switched off for this account. A module above the session's
 * role is not returned at all.
 */
export type ModuleUnavailableReason = 'platform_disabled' | 'coming_soon' | 'disabled_for_user'
export type WorkspaceLanding = 'LAUNCHER' | 'LAST_MODULE'

/** One live number on a launcher card; `value: null` renders as a dash. */
export interface ModuleStat {
  key: string
  label: string
  value: number | null
  unit?: string | null
  hint?: string | null
}

export interface WorkspaceModule {
  code: string
  name: string
  tagline: string
  description?: string | null
  /** A lucide icon name; the client registry's icon wins for known modules. */
  icon: string
  /** `null` for a module with no pages yet. */
  home_path: string | null
  /** A design-token name (`primary`, `info`, `warning`…). */
  accent: string
  status: ModuleStatus
  min_role: ModuleMinRole
  available: boolean
  unavailable_reason: ModuleUnavailableReason | null
  is_pinned: boolean
  sort_order: number
  last_opened_at: string | null
  open_count: number
  summary: ModuleStat[]
}

export interface ModuleUpdate {
  is_pinned?: boolean
  sort_order?: number
}

export interface WorkspacePreferences {
  landing: WorkspaceLanding
  show_tips: boolean
  last_module_code: string | null
  last_module_home_path: string | null
}

export interface WorkspacePreferencesUpdate {
  landing?: WorkspaceLanding
  show_tips?: boolean
}

export interface AdminUserRef {
  id: string
  email: string
  full_name: string
}

export interface AdminModuleState {
  code: string
  name: string
  status: ModuleStatus
  min_role: ModuleMinRole
  platform_enabled: boolean
  enabled_for_user: boolean
}

export interface AdminUserModules {
  user: AdminUserRef
  modules: AdminModuleState[]
}

/** `details` of a `403 module_disabled` error. */
export interface ModuleDisabledDetails {
  module: string
  module_name: string
  reason: ModuleUnavailableReason | 'role_required'
}

/** One catalog row for the platform admin (`GET /workspace/admin/modules`). */
export interface AdminCatalogModule {
  code: string
  name: string
  tagline: string
  icon: string
  home_path: string | null
  status: ModuleStatus
  min_role: ModuleMinRole
  /** Off hides the module for everyone and its API answers 403. */
  is_enabled: boolean
  sort_order: number
}

export interface AdminCatalogUpdate {
  is_enabled?: boolean
  status?: ModuleStatus
  sort_order?: number
}
