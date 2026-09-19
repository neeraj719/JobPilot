import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

export type Theme = 'light' | 'dark' | 'system'

interface UiState {
  theme: Theme
  /** Resolved value actually applied to `<html>` (never 'system'). */
  resolvedTheme: 'light' | 'dark'
  sidebarCollapsed: boolean

  setTheme: (theme: Theme) => void
  toggleTheme: () => void
  setSidebarCollapsed: (collapsed: boolean) => void
  toggleSidebar: () => void
  /** Applies the persisted theme to `<html>` and starts watching the OS preference. */
  initTheme: () => () => void
}

const STORAGE_KEY = 'jobpilot.ui'

function prefersDark(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches
}

function resolveTheme(theme: Theme): 'light' | 'dark' {
  if (theme === 'system') return prefersDark() ? 'dark' : 'light'
  return theme
}

function applyTheme(theme: Theme): 'light' | 'dark' {
  const resolved = resolveTheme(theme)
  if (typeof document !== 'undefined') {
    const root = document.documentElement
    root.classList.toggle('dark', resolved === 'dark')
    root.style.colorScheme = resolved
  }
  return resolved
}

export const useUiStore = create<UiState>()(
  persist(
    (set, get) => ({
      theme: 'system',
      resolvedTheme: 'light',
      sidebarCollapsed: false,

      setTheme: (theme) => set({ theme, resolvedTheme: applyTheme(theme) }),

      toggleTheme: () => {
        const next: Theme = get().resolvedTheme === 'dark' ? 'light' : 'dark'
        set({ theme: next, resolvedTheme: applyTheme(next) })
      },

      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

      initTheme: () => {
        set({ resolvedTheme: applyTheme(get().theme) })
        if (typeof window === 'undefined') return () => undefined
        const media = window.matchMedia('(prefers-color-scheme: dark)')
        const onChange = () => {
          if (get().theme === 'system') set({ resolvedTheme: applyTheme('system') })
        }
        media.addEventListener('change', onChange)
        return () => media.removeEventListener('change', onChange)
      },
    }),
    {
      name: STORAGE_KEY,
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({ theme: state.theme, sidebarCollapsed: state.sidebarCollapsed }),
      onRehydrateStorage: () => (state) => {
        // Re-apply as soon as the persisted value lands, to avoid a light-mode flash.
        if (state) state.resolvedTheme = applyTheme(state.theme)
      },
    },
  ),
)
