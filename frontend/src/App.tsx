import { QueryClientProvider } from '@tanstack/react-query'
import * as React from 'react'
import { BrowserRouter } from 'react-router-dom'

import { Toaster } from '@/components/ui/toaster'
import { TooltipProvider } from '@/components/ui/tooltip'
import { queryClient } from '@/lib/queryClient'
import { AppRoutes } from '@/router'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

export default function App() {
  const bootstrap = useAuthStore((state) => state.bootstrap)
  const initTheme = useUiStore((state) => state.initTheme)

  // Apply the persisted theme and keep following the OS preference.
  React.useEffect(() => initTheme(), [initTheme])

  // Validate any token restored from sessionStorage before the router decides on redirects.
  React.useEffect(() => {
    void bootstrap()
  }, [bootstrap])

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={200}>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  )
}
