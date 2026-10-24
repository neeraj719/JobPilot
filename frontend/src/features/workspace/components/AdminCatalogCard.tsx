import { AlertTriangle } from 'lucide-react'
import * as React from 'react'

import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { ErrorState } from '@/components/common/ErrorState'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { toast } from '@/components/ui/toaster'
import { useAdminCatalog, useAdminUpdateCatalog } from '@/features/workspace/api'
import type { AdminCatalogModule, AdminCatalogUpdate, ModuleStatus } from '@/features/workspace/types'
import { errorMessage } from '@/lib/api'
import { moduleIcon } from '@/modules/registry'
import { ModuleRowsSkeleton } from '@/features/workspace/components/WorkspaceSkeletons'

const STATUS_LABELS: Record<ModuleStatus, string> = {
  AVAILABLE: 'Available',
  COMING_SOON: 'Coming soon',
}

/**
 * Settings › Admin › Platform modules: the platform-wide switch and status of every module.
 * Switching off asks for confirmation (it affects every account at once). The server
 * refuses to switch off the last usable module and to make a module without a home page
 * available; its message is shown as is.
 */
export function AdminCatalogCard() {
  const catalog = useAdminCatalog()
  const update = useAdminUpdateCatalog()
  const [pendingCode, setPendingCode] = React.useState<string | null>(null)
  const [confirmOff, setConfirmOff] = React.useState<AdminCatalogModule | null>(null)

  async function save(module: AdminCatalogModule, change: AdminCatalogUpdate, success: string) {
    setPendingCode(module.code)
    try {
      await update.mutateAsync({ code: module.code, ...change })
      toast.success(success)
    } catch (error) {
      toast.error(`Could not change ${module.name}`, { description: errorMessage(error) })
    } finally {
      setPendingCode(null)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Platform modules</CardTitle>
        <CardDescription>Which modules exist for everyone on this JobPilot installation.</CardDescription>
        <p className="flex items-start gap-2 rounded-xl border border-warning/30 bg-warning-soft px-3 py-2 text-sm text-warning-soft-foreground">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
          Switching a module off hides it for everyone and returns 403 from its API.
        </p>
      </CardHeader>
      <CardContent>
        {catalog.isPending ? (
          <ModuleRowsSkeleton rows={4} trailing="select-switch" label="Loading platform modules" />
        ) : catalog.isError ? (
          <ErrorState error={catalog.error} size="sm" onRetry={() => void catalog.refetch()} />
        ) : (
          <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border" aria-label="Platform modules">
            {catalog.data.map((module) => {
              const Icon = moduleIcon(module.code, module.icon)
              const id = `catalog-module-${module.code}`
              const busy = pendingCode !== null
              return (
                <li key={module.code} className="flex flex-wrap items-center gap-3 p-3 sm:flex-nowrap">
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-gradient-brand-soft text-primary ring-1 ring-inset ring-primary/15">
                    <Icon className="size-4" aria-hidden />
                  </span>
                  <div className="min-w-0 flex-1">
                    <label htmlFor={id} className="flex flex-wrap items-center gap-2 text-sm font-medium">
                      {module.name}
                      {module.is_enabled ? (
                        <Badge variant="success">On</Badge>
                      ) : (
                        <Badge variant="muted">Off for everyone</Badge>
                      )}
                      {module.min_role === 'ADMIN' ? <Badge variant="outline">Admins only</Badge> : null}
                    </label>
                    <p className="truncate text-xs text-muted-foreground">{module.tagline}</p>
                  </div>
                  <Select
                    value={module.status}
                    disabled={busy}
                    onValueChange={(value) =>
                      void save(module, { status: value as ModuleStatus }, `${module.name} is now ${STATUS_LABELS[value as ModuleStatus].toLowerCase()}`)
                    }
                  >
                    <SelectTrigger className="h-8 w-36" aria-label={`${module.name} status`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {(Object.keys(STATUS_LABELS) as ModuleStatus[]).map((status) => (
                        <SelectItem key={status} value={status}>
                          {STATUS_LABELS[status]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Switch
                    id={id}
                    checked={module.is_enabled}
                    disabled={busy}
                    aria-label={`${module.name} for everyone`}
                    onCheckedChange={(value) => {
                      if (value) void save(module, { is_enabled: true }, `${module.name} is on for everyone`)
                      else setConfirmOff(module)
                    }}
                  />
                </li>
              )
            })}
          </ul>
        )}
      </CardContent>
      <ConfirmDialog
        open={confirmOff !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmOff(null)
        }}
        title={confirmOff ? `Switch ${confirmOff.name} off for everyone?` : 'Switch off?'}
        description="Every account loses its pages at once and its API answers 403 until you switch it back on. No data is deleted, and scheduled automation for it stops."
        confirmLabel="Switch off"
        variant="destructive"
        loading={pendingCode !== null}
        onConfirm={async () => {
          if (confirmOff) await save(confirmOff, { is_enabled: false }, `${confirmOff.name} is off for everyone`)
          setConfirmOff(null)
        }}
      />
    </Card>
  )
}
