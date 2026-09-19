import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

import { api, configureApiAuth } from '@/lib/api'
import type { LoginRequest, RegisterRequest, TokenResponse, UserRead } from '@/types/api'

interface AuthState {
  accessToken: string | null
  user: UserRead | null
  /** True while a login/register/bootstrap request is in flight. */
  isLoading: boolean
  /** Flipped once the stored session has been validated (or found absent) on boot. */
  isBootstrapped: boolean

  login: (email: string, password: string) => Promise<UserRead>
  register: (fullName: string, email: string, password: string) => Promise<UserRead>
  logout: () => Promise<void>
  setToken: (token: string | null, user?: UserRead | null) => void
  setUser: (user: UserRead) => void
  fetchMe: () => Promise<UserRead | null>
  /** Called once on app start: validates a persisted token. */
  bootstrap: () => Promise<void>
  isAuthenticated: () => boolean
}

const STORAGE_KEY = 'jobpilot.auth'

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      user: null,
      isLoading: false,
      isBootstrapped: false,

      setToken: (token, user) =>
        set((state) => ({
          accessToken: token,
          user: user === undefined ? state.user : user,
        })),

      setUser: (user) => set({ user }),

      isAuthenticated: () => Boolean(get().accessToken),

      login: async (email, password) => {
        set({ isLoading: true })
        try {
          const token = await api.post<TokenResponse>(
            '/auth/login',
            { email, password } satisfies LoginRequest,
            { skipAuth: true },
          )
          set({ accessToken: token.access_token, user: token.user, isBootstrapped: true })
          return token.user
        } finally {
          set({ isLoading: false })
        }
      },

      register: async (fullName, email, password) => {
        set({ isLoading: true })
        try {
          const token = await api.post<TokenResponse>(
            '/auth/register',
            { full_name: fullName, email, password } satisfies RegisterRequest,
            { skipAuth: true },
          )
          set({ accessToken: token.access_token, user: token.user, isBootstrapped: true })
          return token.user
        } finally {
          set({ isLoading: false })
        }
      },

      logout: async () => {
        try {
          // Revokes the refresh token and clears the HttpOnly cookie server-side.
          await api.post('/auth/logout')
        } catch {
          // A failed logout must never trap the user in the app.
        } finally {
          set({ accessToken: null, user: null, isBootstrapped: true })
        }
      },

      fetchMe: async () => {
        if (!get().accessToken) return null
        try {
          const user = await api.get<UserRead>('/auth/me')
          set({ user })
          return user
        } catch {
          set({ accessToken: null, user: null })
          return null
        }
      },

      bootstrap: async () => {
        if (get().isBootstrapped) return
        if (!get().accessToken) {
          set({ isBootstrapped: true })
          return
        }
        set({ isLoading: true })
        try {
          await get().fetchMe()
        } finally {
          set({ isLoading: false, isBootstrapped: true })
        }
      },
    }),
    {
      name: STORAGE_KEY,
      // sessionStorage: the token dies with the tab; the refresh cookie restores the session.
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({ accessToken: state.accessToken, user: state.user }),
    },
  ),
)

// Teach the fetch client how to read/refresh the token without importing the store.
configureApiAuth({
  getToken: () => useAuthStore.getState().accessToken,
  onTokenRefreshed: (token, response) => {
    useAuthStore.setState({ accessToken: token, user: response.user ?? useAuthStore.getState().user })
  },
  onAuthFailure: () => {
    useAuthStore.setState({ accessToken: null, user: null, isBootstrapped: true })
  },
})

/** Non-reactive read, for use outside React (e.g. route loaders). */
export const getAccessToken = (): string | null => useAuthStore.getState().accessToken
