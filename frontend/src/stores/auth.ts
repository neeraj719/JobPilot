import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

import { api, configureApiAuth, isApiError } from '@/lib/api'
import { getPreferredRole, setPreferredRole } from '@/lib/roles'
import type {
  LoginRequest,
  LoginResponse,
  RegisterRequest,
  RoleSelectionRequired,
  SelectRoleRequest,
  SwitchRoleRequest,
  TokenResponse,
  UserRead,
} from '@/types/api'

/** Password accepted, but the account holds several roles and must pick one. */
export interface PendingRoleSelection {
  selectionToken: string
  roles: string[]
  user: UserRead
  /** The login form's "Stay signed in" choice, forwarded to `/auth/select-role`. */
  rememberMe: boolean
}

/**
 * Result of `login` / `register`:
 *  - `signed_in`: a session exists. `autoSelected` is set when the role was picked
 *    silently from this device's remembered preference (show a "Switch" hint).
 *  - `role_selection`: no session yet; send the user to `/choose-role`.
 */
export type LoginOutcome =
  | { status: 'signed_in'; user: UserRead; activeRole: string; autoSelected?: string }
  | { status: 'role_selection'; user: UserRead; roles: string[] }

interface AuthState {
  accessToken: string | null
  user: UserRead | null
  /** The role the current session acts as (the access token's `role` claim). */
  activeRole: string | null
  /** Every role the user may switch to. */
  availableRoles: string[]
  /**
   * Whether this browser's session was started with "Stay signed in" (persistent refresh
   * cookie). `null` when unknown. Drives the one-time "skip the login next time" nudge.
   */
  sessionRemembered: boolean | null
  /** Set between a multi-role password check and the role choice. */
  pendingRoleSelection: PendingRoleSelection | null
  /** True while a login/register/bootstrap request is in flight. */
  isLoading: boolean
  /** Flipped once the stored session has been validated (or found absent) on boot. */
  isBootstrapped: boolean

  /** `rememberMe` = "Stay signed in on this device". The password is sent, never kept. */
  login: (email: string, password: string, rememberMe?: boolean) => Promise<LoginOutcome>
  register: (fullName: string, email: string, password: string, rememberMe?: boolean) => Promise<LoginOutcome>
  /** Finish a pending selection. `remember` stores the role as this device's default. */
  selectRole: (role: string, remember?: boolean) => Promise<UserRead>
  /** Change the active role of the current session without signing out. */
  switchRole: (role: string) => Promise<UserRead>
  /** Abandon a pending selection (the "Not you?" link). */
  cancelRoleSelection: () => void
  logout: () => Promise<void>
  setToken: (token: string | null, user?: UserRead | null) => void
  setUser: (user: UserRead) => void
  /** Record that this device's session was switched to / from "Stay signed in". */
  setSessionRemembered: (remembered: boolean) => void
  fetchMe: () => Promise<UserRead | null>
  /**
   * Called once on app start: validates a persisted token, or - with none in this tab -
   * tries the refresh cookie, which is how a remembered device skips the login.
   */
  bootstrap: () => Promise<void>
  isAuthenticated: () => boolean
}

const STORAGE_KEY = 'jobpilot.auth'

const SIGNED_OUT = {
  accessToken: null,
  user: null,
  activeRole: null,
  availableRoles: [] as string[],
  pendingRoleSelection: null,
  sessionRemembered: null,
}

export function isRoleSelectionRequired(response: LoginResponse): response is RoleSelectionRequired {
  return response.requires_role_selection === true
}

/** State patch for a token response (login, select, switch, refresh). */
function sessionFrom(token: TokenResponse) {
  return {
    accessToken: token.access_token,
    user: { ...token.user, active_role: token.active_role },
    activeRole: token.active_role ?? token.user.active_role ?? token.user.role,
    availableRoles: token.available_roles ?? token.user.roles ?? [],
    pendingRoleSelection: null,
    // A no-op role switch sets no cookie and says `null`: keep what we knew.
    ...(typeof token.remembered === 'boolean' ? { sessionRemembered: token.remembered } : {}),
  }
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => {
      /** Shared by login and register: both can answer with either shape. */
      async function handleLoginResponse(response: LoginResponse, rememberMe: boolean): Promise<LoginOutcome> {
        if (!isRoleSelectionRequired(response)) {
          set({ ...sessionFrom(response), isBootstrapped: true })
          return { status: 'signed_in', user: response.user, activeRole: response.active_role }
        }

        const pending: PendingRoleSelection = {
          selectionToken: response.selection_token,
          roles: response.available_roles,
          user: response.user,
          rememberMe,
        }
        set({ ...SIGNED_OUT, pendingRoleSelection: pending, isBootstrapped: true })

        // A role remembered on this device and still held is picked silently.
        const preferred = getPreferredRole(response.user.id)
        if (preferred && response.available_roles.includes(preferred)) {
          try {
            const user = await get().selectRole(preferred, false)
            return { status: 'signed_in', user, activeRole: preferred, autoSelected: preferred }
          } catch {
            // Fall through to the explicit choice (e.g. the token just expired).
            set({ pendingRoleSelection: pending })
          }
        }
        return { status: 'role_selection', user: response.user, roles: response.available_roles }
      }

      return {
        ...SIGNED_OUT,
        isLoading: false,
        isBootstrapped: false,

        setToken: (token, user) =>
          set((state) => ({
            accessToken: token,
            user: user === undefined ? state.user : user,
          })),

        setUser: (user) => set({ user }),

        setSessionRemembered: (remembered) => set({ sessionRemembered: remembered }),

        isAuthenticated: () => Boolean(get().accessToken),

        login: async (email, password, rememberMe = false) => {
          set({ isLoading: true })
          try {
            const response = await api.post<LoginResponse>(
              '/auth/login',
              { email, password, remember_me: rememberMe } satisfies LoginRequest,
              { skipAuth: true },
            )
            return await handleLoginResponse(response, rememberMe)
          } finally {
            set({ isLoading: false })
          }
        },

        register: async (fullName, email, password, rememberMe = false) => {
          set({ isLoading: true })
          try {
            const response = await api.post<LoginResponse>(
              '/auth/register',
              { full_name: fullName, email, password, remember_me: rememberMe } satisfies RegisterRequest,
              { skipAuth: true },
            )
            return await handleLoginResponse(response, rememberMe)
          } finally {
            set({ isLoading: false })
          }
        },

        selectRole: async (role, remember = false) => {
          const pending = get().pendingRoleSelection
          if (!pending) throw new Error('There is no role selection in progress. Sign in again.')
          try {
            const token = await api.post<TokenResponse>(
              '/auth/select-role',
              {
                selection_token: pending.selectionToken,
                role,
                remember,
                remember_me: pending.rememberMe ?? false,
              } satisfies SelectRoleRequest,
              { skipAuth: true },
            )
            set({ ...sessionFrom(token), isBootstrapped: true })
            if (remember) setPreferredRole(token.user.id, role)
            return token.user
          } catch (error) {
            // An expired or already-used selection cannot be retried: start over.
            if (isApiError(error) && error.status === 401) set({ pendingRoleSelection: null })
            throw error
          }
        },

        switchRole: async (role) => {
          const token = await api.post<TokenResponse>('/auth/switch-role', { role } satisfies SwitchRoleRequest)
          set(sessionFrom(token))
          return token.user
        },

        cancelRoleSelection: () => set({ pendingRoleSelection: null }),

        logout: async () => {
          try {
            // Revokes the refresh token and clears the HttpOnly cookie server-side.
            await api.post('/auth/logout')
          } catch {
            // A failed logout must never trap the user in the app.
          } finally {
            set({ ...SIGNED_OUT, isBootstrapped: true })
          }
        },

        fetchMe: async () => {
          if (!get().accessToken) return null
          try {
            const user = await api.get<UserRead>('/auth/me')
            set((state) => ({
              user,
              activeRole: user.active_role ?? state.activeRole ?? user.role,
              availableRoles: user.roles?.length ? user.roles : state.availableRoles,
            }))
            return user
          } catch (error) {
            // Only a genuine authentication failure ends the session. A rate limit,
            // a server error or a dropped connection must not silently sign the
            // user out and bounce them to the login screen.
            if (isApiError(error) && (error.status === 401 || error.status === 403)) {
              set({ accessToken: null, user: null, activeRole: null, availableRoles: [] })
            }
            return null
          }
        },

        bootstrap: async () => {
          if (get().isBootstrapped) return
          if (!get().accessToken) {
            if (!get().pendingRoleSelection) {
              set({ isLoading: true })
              try {
                // A new tab or a reopened browser: the HttpOnly refresh cookie (if this
                // device was remembered, or the browser session is still open) restores
                // the session without asking for the password.
                const token = await api.post<TokenResponse>('/auth/refresh', undefined, {
                  skipAuth: true,
                  skipRefresh: true,
                })
                set(sessionFrom(token))
              } catch {
                // No cookie, or it expired / was signed out: the login page it is.
              } finally {
                set({ isLoading: false })
              }
            }
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
      }
    },
    {
      name: STORAGE_KEY,
      // sessionStorage: the token dies with the tab; the refresh cookie restores the session.
      // The pending selection (a 5-minute, single-use token) is kept so a reload of
      // /choose-role does not throw the user back to the password step.
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({
        accessToken: state.accessToken,
        user: state.user,
        activeRole: state.activeRole,
        availableRoles: state.availableRoles,
        pendingRoleSelection: state.pendingRoleSelection,
        sessionRemembered: state.sessionRemembered,
      }),
    },
  ),
)

// Teach the fetch client how to read/refresh the token without importing the store.
configureApiAuth({
  getToken: () => useAuthStore.getState().accessToken,
  onTokenRefreshed: (token, response) => {
    if (response.user) {
      useAuthStore.setState({ ...sessionFrom(response), accessToken: token })
    } else {
      useAuthStore.setState({ accessToken: token })
    }
  },
  onAuthFailure: () => {
    useAuthStore.setState({ ...SIGNED_OUT, isBootstrapped: true })
  },
})

/** Non-reactive read, for use outside React (e.g. route loaders). */
export const getAccessToken = (): string | null => useAuthStore.getState().accessToken
