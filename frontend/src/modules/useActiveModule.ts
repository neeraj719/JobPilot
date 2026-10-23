import { useLocation } from 'react-router-dom'

import { useWorkspaceModules } from '@/features/workspace/api'
import type { WorkspaceModule } from '@/features/workspace/types'
import {
  findAccountItem,
  findModuleForPath,
  findNavItemIn,
  getModuleDefinition,
  isLauncherPath,
  moduleNavItems,
  type ModuleDefinition,
} from '@/modules/registry'
import type { NavItem } from '@/components/layout/navigation'
import { useUiStore } from '@/stores/ui'

export interface ActiveModule {
  /** The module whose sidebar is shown: the one owning the path, else the last one used. */
  definition: ModuleDefinition | undefined
  /** The server's view of that module (name, availability…), once loaded. */
  module: WorkspaceModule | undefined
  /** The module owning the current path (none on the launcher and the account pages). */
  pathModule: ModuleDefinition | undefined
  /** The page's nav entry, for the title and breadcrumb. */
  navItem: NavItem | undefined
  isLauncher: boolean
  isAccountPage: boolean
  /** Modules the user can see and the client can render, in the user's order. */
  modules: WorkspaceModule[]
  isLoading: boolean
  isError: boolean
}

/** Visible modules the client knows how to render (a coming-soon card needs no routes). */
export function renderableModules(modules: WorkspaceModule[] | undefined): WorkspaceModule[] {
  return (modules ?? []).filter((module) => getModuleDefinition(module.code) || module.status === 'COMING_SOON')
}

export function useActiveModule(): ActiveModule {
  const { pathname } = useLocation()
  const query = useWorkspaceModules()
  const lastModuleCode = useUiStore((state) => state.lastModuleCode)

  const modules = renderableModules(query.data)
  const isLauncher = isLauncherPath(pathname)
  const pathModule = findModuleForPath(pathname)
  const accountItem = pathModule ? undefined : findAccountItem(pathname)

  const usable = (code: string | null | undefined) =>
    code && modules.some((module) => module.code === code && module.available) ? getModuleDefinition(code) : undefined
  const firstUsable = modules.find((module) => module.available && getModuleDefinition(module.code))

  const definition = isLauncher
    ? undefined
    : pathModule ?? usable(lastModuleCode) ?? getModuleDefinition(firstUsable?.code)

  const navItem = pathModule ? findNavItemIn(moduleNavItems(pathModule), pathname) : accountItem

  return {
    definition,
    module: definition ? modules.find((module) => module.code === definition.code) : undefined,
    pathModule,
    navItem,
    isLauncher,
    isAccountPage: Boolean(accountItem),
    modules,
    isLoading: query.isPending,
    isError: query.isError,
  }
}
