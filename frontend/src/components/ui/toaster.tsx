import { Toaster as SonnerToaster, toast } from 'sonner'

import { useUiStore } from '@/stores/ui'

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
      toastOptions={{
        classNames: {
          toast: 'group rounded-lg border border-border bg-card text-card-foreground shadow-lg',
          description: 'text-muted-foreground',
          actionButton: 'bg-primary text-primary-foreground',
          cancelButton: 'bg-muted text-muted-foreground',
        },
      }}
    />
  )
}

export { toast }
