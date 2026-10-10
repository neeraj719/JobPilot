import { Check, ShieldCheck, UserRound, Users } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import * as React from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { toast } from '@/components/ui/toaster'
import { errorMessage } from '@/lib/api'
import { queryClient } from '@/lib/queryClient'
import { clearPreferredRole, getPreferredRole, roleDescription, roleLabel, setPreferredRole } from '@/lib/roles'
import { useAuthStore } from '@/stores/auth'

const ROLE_ICONS: Record<string, LucideIcon> = {
  ADMIN: ShieldCheck,
  USER: UserRound,
}

/**
 * Settings → Account roles: every role the account holds, which one this session acts
 * as, a switch action, and this device's remembered sign-in role.
 */
export function AccountRolesCard() {
  const user = useAuthStore((state) => state.user)
  const activeRole = useAuthStore((state) => state.activeRole)
  const availableRoles = useAuthStore((state) => state.availableRoles)
  const switchRole = useAuthStore((state) => state.switchRole)
  const [switching, setSwitching] = React.useState<string | null>(null)
  const [preferred, setPreferred] = React.useState<string | null>(() => getPreferredRole(user?.id))

  React.useEffect(() => {
    setPreferred(getPreferredRole(user?.id))
  }, [user?.id])

  const roles = availableRoles.length ? availableRoles : (user?.roles ?? [])

  async function handleSwitch(role: string) {
    setSwitching(role)
    try {
      await switchRole(role)
      await queryClient.invalidateQueries()
      toast.success(`Now acting as ${roleLabel(role)}`)
    } catch (error) {
      toast.error('Could not switch role', { description: errorMessage(error) })
    } finally {
      setSwitching(null)
    }
  }

  function forget() {
    if (!user) return
    clearPreferredRole(user.id)
    setPreferred(null)
    toast.success('This device will ask which role to use next time you sign in.')
  }

  function rememberCurrent() {
    if (!user || !activeRole) return
    setPreferredRole(user.id, activeRole)
    setPreferred(activeRole)
    toast.success(`This device will sign you in as ${roleLabel(activeRole)}.`)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Users className="size-4" aria-hidden />
          Account roles
        </CardTitle>
        <CardDescription>
          The role you act as decides what you can do. Switching takes effect immediately and does not sign you out.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <ul className="divide-y divide-border rounded-md border border-border">
          {roles.map((role) => {
            const Icon = ROLE_ICONS[role] ?? UserRound
            const active = role === activeRole
            return (
              <li key={role} className="flex items-center gap-3 p-3">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                  <Icon className="size-4" aria-hidden />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-2 text-sm font-medium">
                    {roleLabel(role)}
                    {active ? (
                      <Badge variant="success">
                        <Check aria-hidden />
                        Active
                      </Badge>
                    ) : null}
                  </p>
                  <p className="text-sm text-muted-foreground">{roleDescription(role)}</p>
                </div>
                {!active ? (
                  <Button
                    variant="outline"
                    size="sm"
                    loading={switching === role}
                    disabled={switching !== null}
                    onClick={() => void handleSwitch(role)}
                  >
                    Switch to {roleLabel(role)}
                  </Button>
                ) : null}
              </li>
            )
          })}
        </ul>

        {roles.length > 1 ? (
          <div className="flex flex-col gap-3 rounded-md border border-dashed border-border p-3 sm:flex-row sm:items-center">
            <div className="min-w-0 flex-1 text-sm">
              <p className="font-medium">Remembered on this device</p>
              <p className="text-muted-foreground">
                {preferred
                  ? `Signing in here skips the role choice and uses ${roleLabel(preferred)}.`
                  : 'Nothing remembered: you will be asked which role to use each time you sign in here.'}
              </p>
            </div>
            {preferred ? (
              <Button variant="outline" size="sm" onClick={forget}>
                Forget
              </Button>
            ) : activeRole ? (
              <Button variant="outline" size="sm" onClick={rememberCurrent}>
                Remember {roleLabel(activeRole)}
              </Button>
            ) : null}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            Your account holds a single role, so there is nothing to choose at sign-in.
          </p>
        )}
      </CardContent>
    </Card>
  )
}
