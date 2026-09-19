import { useAuthStore } from '@/stores/auth'
import type { UserRead } from '@/types/api'

export interface UseAuthResult {
  user: UserRead | null
  accessToken: string | null
  isAuthenticated: boolean
  isAdmin: boolean
  isLoading: boolean
  isBootstrapped: boolean
  login: (email: string, password: string) => Promise<UserRead>
  register: (fullName: string, email: string, password: string) => Promise<UserRead>
  logout: () => Promise<void>
  refreshUser: () => Promise<UserRead | null>
}

/** Ergonomic view over the auth store for components. */
export function useAuth(): UseAuthResult {
  const user = useAuthStore((state) => state.user)
  const accessToken = useAuthStore((state) => state.accessToken)
  const isLoading = useAuthStore((state) => state.isLoading)
  const isBootstrapped = useAuthStore((state) => state.isBootstrapped)
  const login = useAuthStore((state) => state.login)
  const register = useAuthStore((state) => state.register)
  const logout = useAuthStore((state) => state.logout)
  const fetchMe = useAuthStore((state) => state.fetchMe)

  return {
    user,
    accessToken,
    isAuthenticated: Boolean(accessToken),
    isAdmin: user?.role === 'ADMIN',
    isLoading,
    isBootstrapped,
    login,
    register,
    logout,
    refreshUser: fetchMe,
  }
}
