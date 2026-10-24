import { zodResolver } from '@hookform/resolvers/zod'
import { Search, UserRound } from 'lucide-react'
import * as React from 'react'
import { useForm } from 'react-hook-form'

import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { toast } from '@/components/ui/toaster'
import { useAdminFindUser, useAdminToggleModule, useAdminUserModules } from '@/features/workspace/api'
import { adminUserLookupSchema, type AdminUserLookupValues } from '@/features/workspace/schema'
import type { AdminModuleState, AdminUserRef } from '@/features/workspace/types'
import { errorMessage, isApiError } from '@/lib/api'
import { moduleIcon } from '@/modules/registry'
import { AdminUserModulesSkeleton, ModuleRowsSkeleton } from '@/features/workspace/components/WorkspaceSkeletons'

function ModuleToggles({ user }: { user: AdminUserRef }) {
  const view = useAdminUserModules(user.id)
  const toggle = useAdminToggleModule(user.id)
  const [pendingCode, setPendingCode] = React.useState<string | null>(null)

  if (view.isPending) return <ModuleRowsSkeleton rows={3} trailing="switch" />
  if (view.isError) return <ErrorState error={view.error} size="sm" onRetry={() => void view.refetch()} />

  function onToggle(module: AdminModuleState, enabled: boolean) {
    setPendingCode(module.code)
    toggle.mutate(
      { code: module.code, is_enabled: enabled },
      {
        onSuccess: () =>
          toast.success(`${module.name} ${enabled ? 'turned on' : 'turned off'} for ${user.full_name || user.email}`, {
            description: enabled ? undefined : 'Its pages and API now refuse this account.',
          }),
        onError: (error) => toast.error('Could not change the module', { description: errorMessage(error) }),
        onSettled: () => setPendingCode(null),
      },
    )
  }

  return (
    <ul className="divide-y divide-border rounded-lg border border-border" aria-label={`Modules for ${user.email}`}>
      {view.data.modules.map((module) => {
        const Icon = moduleIcon(module.code)
        const id = `admin-module-${module.code}`
        return (
          <li key={module.code} className="flex items-center gap-3 p-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-muted">
              <Icon className="size-4" aria-hidden />
            </span>
            <div className="min-w-0 flex-1">
              <label htmlFor={id} className="flex flex-wrap items-center gap-2 text-sm font-medium">
                {module.name}
                {module.status === 'COMING_SOON' ? <Badge variant="muted">Coming soon</Badge> : null}
                {!module.platform_enabled ? <Badge variant="warning">Off platform-wide</Badge> : null}
                {module.min_role === 'ADMIN' ? <Badge variant="outline">Admins only</Badge> : null}
              </label>
              <p className="text-xs text-muted-foreground">
                {module.enabled_for_user ? 'On for this account' : 'Turned off for this account'}
              </p>
            </div>
            <Switch
              id={id}
              checked={module.enabled_for_user}
              disabled={pendingCode !== null}
              onCheckedChange={(value) => onToggle(module, value)}
              aria-label={`${module.name} for ${user.email}`}
            />
          </li>
        )
      })}
    </ul>
  )
}

/**
 * Settings › Admin: switch a module on or off for one account (e.g. a friend who only
 * needs Resume Studio). Find the account by its exact email; nothing lists every user.
 */
export function AdminModulesCard() {
  const [email, setEmail] = React.useState<string | null>(null)
  const found = useAdminFindUser(email)
  const form = useForm<AdminUserLookupValues>({
    resolver: zodResolver(adminUserLookupSchema),
    defaultValues: { email: '' },
  })

  function onSubmit(values: AdminUserLookupValues) {
    setEmail(values.email.toLowerCase())
  }

  const notFound = found.isError && isApiError(found.error) && found.error.status === 404

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Modules for user</CardTitle>
        <CardDescription>
          Turn a module off for one account. Its sidebar, launcher card and API endpoints are then refused for that
          account; their data is kept.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-2 sm:flex-row sm:items-start" noValidate>
            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem className="flex-1">
                  <FormLabel className="sr-only">Account email</FormLabel>
                  <FormControl>
                    <Input type="email" placeholder="friend@example.com" autoComplete="off" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button type="submit" variant="secondary" loading={found.isFetching}>
              {!found.isFetching ? <Search /> : null}
              Find account
            </Button>
          </form>
        </Form>

        {email === null ? null : found.isPending ? (
          <AdminUserModulesSkeleton />
        ) : notFound ? (
          <EmptyState size="sm" icon={UserRound} title="No account with that email" description={email} />
        ) : found.isError ? (
          <ErrorState error={found.error} size="sm" onRetry={() => void found.refetch()} />
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm">
              <UserRound className="size-4 text-muted-foreground" aria-hidden />
              <span className="font-medium">{found.data.full_name || found.data.email}</span>
              <span className="truncate text-muted-foreground">{found.data.email}</span>
            </div>
            <ModuleToggles user={found.data} />
          </div>
        )}
      </CardContent>
    </Card>
  )
}
