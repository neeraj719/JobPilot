import type * as React from 'react'
import { Toaster as SonnerToaster, toast } from 'sonner'

import { useUiStore } from '@/stores/ui'

/**
 * Sonner reads its colours from CSS variables; point them at our tokens so a success
 * toast is the same soft green as a success badge, in both themes (AA-checked pairs).
 */
const TOKEN_VARS = {
  '--normal-bg': 'hsl(var(--popover))',
  '--normal-border': 'hsl(var(--border))',
  '--normal-text': 'hsl(var(--popover-foreground))',
  '--success-bg': 'hsl(var(--success-soft))',
  '--success-border': 'hsl(var(--success) / 0.25)',
  '--success-text': 'hsl(var(--success-soft-foreground))',
  '--info-bg': 'hsl(var(--info-soft))',
  '--info-border': 'hsl(var(--info) / 0.25)',
  '--info-text': 'hsl(var(--info-soft-foreground))',
  '--warning-bg': 'hsl(var(--warning-soft))',
  '--warning-border': 'hsl(var(--warning) / 0.3)',
  '--warning-text': 'hsl(var(--warning-soft-foreground))',
  '--error-bg': 'hsl(var(--destructive-soft))',
  '--error-border': 'hsl(var(--destructive) / 0.25)',
  '--error-text': 'hsl(var(--destructive-soft-foreground))',
  '--border-radius': 'calc(var(--radius) + 2px)',
  fontFamily: 'inherit',
} as React.CSSProperties

/**
 * App-wide toast host. Mounted once in `App.tsx`; call `toast.success(...)` anywhere.
 * Styling is driven by the theme tokens so toasts match light and dark mode.
 */
export function Toaster() {
  const resolvedTheme = useUiStore((state) => state.resolvedTheme)

  return (
    <SonnerToaster
      theme={resolvedTheme}
      position="bottom-right"
      closeButton
      richColors
      duration={5000}
      style={TOKEN_VARS}
      toastOptions={{
        classNames: {
          toast: 'group rounded-xl border shadow-lg font-sans',
          description: 'opacity-90',
          actionButton: 'bg-primary text-primary-foreground',
          cancelButton: 'bg-muted text-muted-foreground',
        },
      }}
    />
  )
}

export { toast }
