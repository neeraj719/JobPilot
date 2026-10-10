import { type LoginOutcome, useAuthStore } from '@/stores/auth'
import type { UserRead } from '@/types/api'

export interface UseAuthResult {
  user: UserRead | null
  accessToken: string | null
  isAuthenticated: boolean
  /** True when the session currently *acts as* ADMIN, not merely when ADMIN is held. */
  isAdmin: boolean
  activeRole: string | null
  availableRoles: string[]
  isLoading: boolean
  isBootstrapped: boolean
  login: (email: string, password: string, rememberMe?: boolean) => Promise<LoginOutcome>
  register: (fullName: string, email: string, password: string, rememberMe?: boolean) => Promise<LoginOutcome>
  switchRole: (role: string) => Promise<UserRead>
  logout: () => Promise<void>
  refreshUser: () => Promise<UserRead | null>
}

/** Ergonomic view over the auth store for components. */
export function useAuth(): UseAuthResult {
  const user = useAuthStore((state) => state.user)
  const accessToken = useAuthStore((state) => state.accessToken)
  const activeRole = useAuthStore((state) => state.activeRole)
  const availableRoles = useAuthStore((state) => state.availableRoles)
  const isLoading = useAuthStore((state) => state.isLoading)
  const isBootstrapped = useAuthStore((state) => state.isBootstrapped)
  const login = useAuthStore((state) => state.login)
  const register = useAuthStore((state) => state.register)
  const switchRole = useAuthStore((state) => state.switchRole)
  const logout = useAuthStore((state) => state.logout)
  const fetchMe = useAuthStore((state) => state.fetchMe)

  return {
    user,
    accessToken,
    isAuthenticated: Boolean(accessToken),
    isAdmin: (activeRole ?? user?.active_role) === 'ADMIN',
    activeRole,
    availableRoles,
    isLoading,
    isBootstrapped,
    login,
    register,
    switchRole,
    logout,
    refreshUser: fetchMe,
  }
}
