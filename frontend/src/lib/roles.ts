/**
 * Role vocabulary for the UI and the per-device "remembered role" preference.
 *
 * The preference lives in `localStorage` under `jobpilot.preferredRole.<userId>`: it is a
 * convenience for this browser only (the server never stores the choice), so it is read
 * defensively — storage can be unavailable or cleared at any time.
 */

const PREFERRED_ROLE_PREFIX = 'jobpilot.preferredRole.'

const ROLE_LABELS: Record<string, string> = {
  ADMIN: 'Admin',
  USER: 'User',
}

const ROLE_DESCRIPTIONS: Record<string, string> = {
  ADMIN: 'Manage users and the system.',
  USER: 'Your own job search.',
}

export function roleLabel(role: string | null | undefined): string {
  if (!role) return 'Unknown'
  return ROLE_LABELS[role] ?? role.charAt(0) + role.slice(1).toLowerCase().replace(/_/g, ' ')
}

export function roleDescription(role: string): string {
  return ROLE_DESCRIPTIONS[role] ?? 'Act with the permissions of this role.'
}

function preferredRoleKey(userId: string): string {
  return `${PREFERRED_ROLE_PREFIX}${userId}`
}

export function getPreferredRole(userId: string | null | undefined): string | null {
  if (!userId) return null
  try {
    return window.localStorage.getItem(preferredRoleKey(userId))
  } catch {
    return null
  }
}

export function setPreferredRole(userId: string, role: string): void {
  try {
    window.localStorage.setItem(preferredRoleKey(userId), role)
  } catch {
    // Storage blocked (private mode, quota): the choice just is not remembered.
  }
}

export function clearPreferredRole(userId: string): void {
  try {
    window.localStorage.removeItem(preferredRoleKey(userId))
  } catch {
    // Nothing to forget if storage is unavailable.
  }
}
