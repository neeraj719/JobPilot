import * as React from 'react'
import { Navigate, Outlet } from 'react-router-dom'

import { LoadingState } from '@/components/common/LoadingState'
import { PageContainer } from '@/components/layout/PageContainer'
import { toast } from '@/components/ui/toaster'
import { useWorkspaceModules } from '@/features/workspace/api'
import { unavailableToast } from '@/features/workspace/copy'
import type { WorkspaceModule } from '@/features/workspace/types'
import { getModuleDefinition } from '@/modules/registry'

/** What a page shows while its module's bundle downloads. */
export function PageLoading() {
  return (
    <PageContainer aria-busy="true">
      <LoadingState variant="cards" rows={3} />
    </PageContainer>
  )
}

function unavailableMessage(code: string, module: WorkspaceModule | undefined): { title: string; description: string } {
  const name = module?.name ?? getModuleDefinition(code)?.name ?? 'That module'
  return unavailableToast(name, module?.unavailable_reason)
}

function RedirectToLauncher({ code, module }: { code: string; module: WorkspaceModule | undefined }) {
  React.useEffect(() => {
    const { title, description } = unavailableMessage(code, module)
    // A fixed id: StrictMode's double effect (and repeated redirects) show one toast.
    toast.warning(title, { id: `module-unavailable-${code}`, description })
  }, [code, module])
  return <Navigate to="/home" replace />
}

/**
 * Layout route for one module's pages. Waits for the module list, sends the user to the
 * launcher (with a toast) when the server does not offer the module or it cannot be opened,
 * and gives the module's lazily loaded bundle its own Suspense boundary.
 *
 * If the module list itself cannot be fetched the pages still render: the API guards every
 * module endpoint (`403 module_disabled`), so failing open here hides nothing.
 */
export function ModuleRoute({ code }: { code: string }) {
  const modules = useWorkspaceModules()
  if (modules.isPending) return <PageLoading />
  if (modules.isSuccess) {
    const module = modules.data.find((candidate) => candidate.code === code)
    if (!module || !module.available) return <RedirectToLauncher code={code} module={module} />
  }
  return (
    <React.Suspense fallback={<PageLoading />}>
      <Outlet />
    </React.Suspense>
  )
}
