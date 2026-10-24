import { Check, ChevronsUpDown, LayoutGrid, Lock, Pin } from 'lucide-react'
import * as React from 'react'
import { useNavigate } from 'react-router-dom'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { RAIL_TOOLTIP } from '@/components/layout/navigation'
import { SimpleTooltip } from '@/components/ui/tooltip'
import { unavailableCopy } from '@/features/workspace/copy'
import type { WorkspaceModule } from '@/features/workspace/types'
import { MODULE_SWITCHER_SHORTCUT_LABEL } from '@/lib/shortcuts'
import { cn } from '@/lib/utils'
import { accentClasses, getModuleDefinition, moduleIcon, type ModuleDefinition } from '@/modules/registry'
import { useUiStore } from '@/stores/ui'

export interface ModuleSwitcherProps {
  definition: ModuleDefinition | undefined
  module: WorkspaceModule | undefined
  modules: WorkspaceModule[]
  /** Collapsed rail: only the module icon shows. */
  collapsed?: boolean
  /** Inside the mobile drawer: close it after choosing. */
  onNavigate?: () => void
  /**
   * The desktop rail's switcher follows the UI store, so Ctrl+Shift+M can open it. The
   * drawer's copy keeps its own state: the rail stays mounted (just hidden) on small
   * screens, and two menus must never open at once.
   */
  shortcutControlled?: boolean
}

function reasonLabel(module: WorkspaceModule): string {
  return unavailableCopy(module.unavailable_reason).badge
}

/**
 * The sidebar header: the current module's icon and name, and a menu of the user's other
 * modules (with their taglines) plus "All modules" (the launcher). Ctrl+Shift+M opens it
 * from anywhere (AppShell); the open state lives in the UI store for that reason.
 */
export function ModuleSwitcher({
  definition,
  module,
  modules,
  collapsed = false,
  onNavigate,
  shortcutControlled = false,
}: ModuleSwitcherProps) {
  const navigate = useNavigate()
  const storeOpen = useUiStore((state) => state.moduleSwitcherOpen)
  const setStoreOpen = useUiStore((state) => state.setModuleSwitcherOpen)
  const [localOpen, setLocalOpen] = React.useState(false)
  const open = shortcutControlled ? storeOpen : localOpen
  const setOpen = shortcutControlled ? setStoreOpen : setLocalOpen

  const name = module?.name ?? definition?.name ?? 'Modules'
  const Icon = definition ? moduleIcon(definition.code, module?.icon) : LayoutGrid
  const accent = accentClasses(module?.accent ?? definition?.accent)

  function go(path: string) {
    setOpen(false)
    onNavigate?.()
    navigate(path)
  }

  const trigger = (
    <DropdownMenuTrigger
      className={cn(
        // Lives on the dark rail: sidebar tokens only. Expanded, it sits on a raised surface.
        'group flex min-w-0 items-center gap-2.5 rounded-lg text-left transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring focus-visible:ring-offset-2 focus-visible:ring-offset-sidebar',
        'hover:bg-sidebar-accent/70 data-[state=open]:bg-sidebar-accent',
        collapsed
          ? 'size-10 justify-center'
          : 'h-10 min-w-0 flex-1 bg-sidebar-raised px-2 shadow-sm ring-1 ring-inset ring-sidebar-border',
      )}
      aria-label={`Current module: ${name}. Switch module`}
      aria-keyshortcuts="Control+Shift+M Meta+Shift+M"
    >
      {collapsed ? (
        // The rail shows the module's icon on top, in its solid accent tile.
        <span className={cn('flex size-8 shrink-0 items-center justify-center rounded-lg shadow-sm', accent.solid)}>
          <Icon className="size-4" aria-hidden />
        </span>
      ) : (
        <>
          <span className={cn('flex size-6 shrink-0 items-center justify-center rounded-md', accent.solid)}>
            <Icon className="size-3.5" aria-hidden />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[11px] leading-tight text-sidebar-muted">Module</span>
            <span className="block truncate text-sm font-semibold leading-tight tracking-tight text-sidebar-accent-foreground">
              {name}
            </span>
          </span>
          <ChevronsUpDown
            className="size-4 shrink-0 text-sidebar-muted transition-colors group-hover:text-sidebar-accent-foreground"
            aria-hidden
          />
        </>
      )}
    </DropdownMenuTrigger>
  )

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      {collapsed ? (
        <SimpleTooltip label={`${name} · switch module (${MODULE_SWITCHER_SHORTCUT_LABEL})`} side="right" className={RAIL_TOOLTIP}>
          {trigger}
        </SimpleTooltip>
      ) : (
        trigger
      )}
      <DropdownMenuContent
        align="start"
        side={collapsed ? 'right' : 'bottom'}
        sideOffset={collapsed ? 10 : 6}
        className="w-72 p-1.5"
      >
        <DropdownMenuLabel className="flex items-center justify-between px-2 pb-1.5 pt-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
          Switch module
          <kbd className="rounded border border-border bg-muted px-1.5 font-mono text-[10px] normal-case tracking-normal">
            {MODULE_SWITCHER_SHORTCUT_LABEL}
          </kbd>
        </DropdownMenuLabel>
        {modules.map((item) => {
          const ItemIcon = moduleIcon(item.code, item.icon)
          const itemAccent = accentClasses(item.accent)
          const current = item.code === definition?.code
          const target = getModuleDefinition(item.code)
          const disabled = !item.available || !target
          return (
            <DropdownMenuItem
              key={item.code}
              disabled={disabled}
              onSelect={() => target && go(target.homePath)}
              aria-current={current ? 'true' : undefined}
              className={cn('items-start gap-3 rounded-md py-2', current && 'bg-accent/70')}
            >
              <span className={cn('mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md', itemAccent.soft)}>
                <ItemIcon aria-hidden />
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5 text-sm font-medium">
                  <span className="truncate">{item.name}</span>
                  {item.is_pinned ? <Pin className="!size-3 text-muted-foreground" aria-label="Pinned" /> : null}
                </span>
                <span className="block text-xs leading-snug text-muted-foreground">
                  {disabled ? reasonLabel(item) : item.tagline}
                </span>
              </span>
              {current ? <Check className="mt-1 text-primary" aria-hidden /> : null}
              {disabled ? <Lock className="mt-1 text-muted-foreground" aria-hidden /> : null}
            </DropdownMenuItem>
          )
        })}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => go('/home')}>
          <LayoutGrid aria-hidden />
          All modules
          <DropdownMenuShortcut>Launcher</DropdownMenuShortcut>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
