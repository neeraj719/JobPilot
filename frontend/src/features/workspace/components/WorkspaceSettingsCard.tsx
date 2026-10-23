import { zodResolver } from '@hookform/resolvers/zod'
import { ArrowDown, ArrowUp, Lock, Pin, PinOff } from 'lucide-react'
import * as React from 'react'
import { useForm } from 'react-hook-form'

import { ErrorState } from '@/components/common/ErrorState'
import { LoadingState } from '@/components/common/LoadingState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel } from '@/components/ui/form'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Switch } from '@/components/ui/switch'
import { toast } from '@/components/ui/toaster'
import { SimpleTooltip } from '@/components/ui/tooltip'
import {
  useUpdateModule,
  useUpdateWorkspacePreferences,
  useWorkspaceModules,
  useWorkspacePreferences,
} from '@/features/workspace/api'
import { unavailableCopy } from '@/features/workspace/copy'
import { workspacePreferencesSchema, type WorkspacePreferencesValues } from '@/features/workspace/schema'
import type { WorkspaceModule } from '@/features/workspace/types'
import { errorMessage } from '@/lib/api'
import { cn } from '@/lib/utils'
import { accentClasses, moduleIcon } from '@/modules/registry'
import { renderableModules } from '@/modules/useActiveModule'

const LANDING_OPTIONS: { value: WorkspacePreferencesValues['landing']; label: string; description: string }[] = [
  { value: 'LAUNCHER', label: 'The module launcher', description: 'See all your modules after signing in.' },
  {
    value: 'LAST_MODULE',
    label: 'The module I used last',
    description: 'Go straight back in. "All modules" in the module menu still opens the launcher.',
  },
]

function LandingForm() {
  const preferences = useWorkspacePreferences()
  const update = useUpdateWorkspacePreferences()
  const form = useForm<WorkspacePreferencesValues>({
    resolver: zodResolver(workspacePreferencesSchema),
    defaultValues: { landing: 'LAUNCHER', show_tips: true },
  })

  React.useEffect(() => {
    if (preferences.data) form.reset({ landing: preferences.data.landing, show_tips: preferences.data.show_tips })
  }, [preferences.data, form])

  if (preferences.isPending) return <LoadingState rows={2} />
  if (preferences.isError) {
    return <ErrorState error={preferences.error} size="sm" onRetry={() => void preferences.refetch()} />
  }

  function onSubmit(values: WorkspacePreferencesValues) {
    update.mutate(values, {
      onSuccess: () => toast.success('Workspace preferences saved'),
      onError: (error) => toast.error('Could not save', { description: errorMessage(error) }),
    })
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-5" noValidate>
        <FormField
          control={form.control}
          name="landing"
          render={({ field }) => (
            <FormItem className="space-y-2">
              <FormLabel>After signing in, open</FormLabel>
              <FormControl>
                <RadioGroup value={field.value} onValueChange={field.onChange} className="gap-2">
                  {LANDING_OPTIONS.map((option) => (
                    <Label
                      key={option.value}
                      htmlFor={`landing-${option.value}`}
                      className={cn(
                        'flex cursor-pointer items-start gap-3 rounded-lg border border-border p-3 font-normal transition-colors',
                        'hover:bg-muted/40',
                        field.value === option.value && 'border-primary/60 bg-primary/5',
                      )}
                    >
                      <RadioGroupItem value={option.value} id={`landing-${option.value}`} className="mt-0.5" />
                      <span className="space-y-0.5">
                        <span className="block text-sm font-medium">{option.label}</span>
                        <span className="block text-xs text-muted-foreground">{option.description}</span>
                      </span>
                    </Label>
                  ))}
                </RadioGroup>
              </FormControl>
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="show_tips"
          render={({ field }) => (
            <FormItem className="flex items-center justify-between gap-4 space-y-0 rounded-lg border border-border p-3">
              <div className="space-y-0.5">
                <FormLabel className="text-sm">Show tips on the launcher</FormLabel>
                <FormDescription className="text-xs">Keyboard shortcuts and where things live.</FormDescription>
              </div>
              <FormControl>
                <Switch checked={field.value} onCheckedChange={field.onChange} />
              </FormControl>
            </FormItem>
          )}
        />
        <div className="flex justify-end">
          <Button type="submit" loading={update.isPending} disabled={!form.formState.isDirty}>
            Save preferences
          </Button>
        </div>
      </form>
    </Form>
  )
}

/**
 * Up/down buttons rather than drag and drop: keyboard and screen-reader friendly, and the
 * list is short. Pinned modules always come first, so a module only moves within its own
 * group (pinned or not).
 */
function ModuleOrderList() {
  const modulesQuery = useWorkspaceModules()
  const updateModule = useUpdateModule()
  const [busy, setBusy] = React.useState(false)
  const modules = renderableModules(modulesQuery.data)

  if (modulesQuery.isPending) return <LoadingState rows={3} />
  if (modulesQuery.isError) {
    return <ErrorState error={modulesQuery.error} size="sm" onRetry={() => void modulesQuery.refetch()} />
  }

  async function move(index: number, direction: -1 | 1) {
    const a = modules[index]
    const b = modules[index + direction]
    if (!a || !b || a.is_pinned !== b.is_pinned) return
    setBusy(true)
    try {
      // Swap the two effective positions. They are distinct, so this is a permutation.
      await updateModule.mutateAsync({ code: a.code, sort_order: b.sort_order })
      await updateModule.mutateAsync({ code: b.code, sort_order: a.sort_order })
    } catch (error) {
      toast.error('Could not reorder', { description: errorMessage(error) })
    } finally {
      setBusy(false)
    }
  }

  async function togglePin(module: WorkspaceModule) {
    setBusy(true)
    try {
      await updateModule.mutateAsync({ code: module.code, is_pinned: !module.is_pinned })
    } catch (error) {
      toast.error('Could not update the module', { description: errorMessage(error) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <ol className="divide-y divide-border rounded-lg border border-border" aria-label="Module order">
      {modules.map((module, index) => {
        const Icon = moduleIcon(module.code, module.icon)
        const accent = accentClasses(module.accent)
        const canUp = index > 0 && modules[index - 1].is_pinned === module.is_pinned
        const canDown = index < modules.length - 1 && modules[index + 1].is_pinned === module.is_pinned
        return (
          <li key={module.code} className="flex items-center gap-3 p-3">
            <span
              className={cn(
                'flex size-9 shrink-0 items-center justify-center rounded-md',
                module.available ? accent.soft : 'bg-muted text-muted-foreground',
              )}
            >
              <Icon className="size-4" aria-hidden />
            </span>
            <div className="min-w-0 flex-1">
              <p className="flex items-center gap-2 text-sm font-medium">
                <span className="truncate">{module.name}</span>
                {module.is_pinned ? (
                  <Badge variant="secondary">
                    <Pin aria-hidden />
                    Pinned
                  </Badge>
                ) : null}
                {!module.available ? (
                  <Badge variant="muted">
                    <Lock aria-hidden />
                    {unavailableCopy(module.unavailable_reason).badge}
                  </Badge>
                ) : null}
              </p>
              <p className="truncate text-xs text-muted-foreground">{module.tagline}</p>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              {module.available ? (
                <SimpleTooltip label={module.is_pinned ? 'Unpin' : 'Pin to the front'} side="top">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-8"
                    disabled={busy}
                    onClick={() => void togglePin(module)}
                    aria-pressed={module.is_pinned}
                    aria-label={module.is_pinned ? `Unpin ${module.name}` : `Pin ${module.name}`}
                  >
                    {module.is_pinned ? <PinOff /> : <Pin />}
                  </Button>
                </SimpleTooltip>
              ) : null}
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-8"
                disabled={busy || !canUp}
                onClick={() => void move(index, -1)}
                aria-label={`Move ${module.name} up`}
              >
                <ArrowUp />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-8"
                disabled={busy || !canDown}
                onClick={() => void move(index, 1)}
                aria-label={`Move ${module.name} down`}
              >
                <ArrowDown />
              </Button>
            </div>
          </li>
        )
      })}
    </ol>
  )
}

/** Settings › Workspace: where you land after sign-in, launcher tips, module order and pins. */
export function WorkspaceSettingsCard() {
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Landing page</CardTitle>
          <CardDescription>Where JobPilot takes you after you sign in.</CardDescription>
        </CardHeader>
        <CardContent>
          <LandingForm />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Your modules</CardTitle>
          <CardDescription>
            The order of the launcher and the module menu. Pinned modules come first.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ModuleOrderList />
        </CardContent>
      </Card>
    </div>
  )
}
