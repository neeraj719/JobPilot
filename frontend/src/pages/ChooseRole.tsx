import { ShieldCheck, UserRound } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import * as React from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import { AuthLayout } from '@/components/layout/AuthLayout'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Spinner } from '@/components/ui/spinner'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { errorMessage, isApiError } from '@/lib/api'
import { roleDescription, roleLabel } from '@/lib/roles'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth'

const ROLE_ICONS: Record<string, LucideIcon> = {
  ADMIN: ShieldCheck,
  USER: UserRound,
}

/**
 * Shown after the password step when the account holds more than one role.
 * Reachable only while a selection is pending (see `RoleSelectionRoute` in the router).
 */
export default function ChooseRolePage() {
  useDocumentTitle('Choose a role')
  const navigate = useNavigate()
  const location = useLocation()
  const pending = useAuthStore((state) => state.pendingRoleSelection)
  const selectRole = useAuthStore((state) => state.selectRole)
  const cancelRoleSelection = useAuthStore((state) => state.cancelRoleSelection)
  const [remember, setRemember] = React.useState(false)
  const [submitting, setSubmitting] = React.useState<string | null>(null)

  const redirectTo = (location.state as { from?: string } | null)?.from ?? '/dashboard'

  if (!pending) return null
  const { user, roles } = pending

  async function choose(role: string) {
    setSubmitting(role)
    try {
      await selectRole(role, remember)
      toast.success(`Signed in as ${roleLabel(role)}`, { description: `Welcome back, ${user.full_name || user.email}` })
      navigate(redirectTo, { replace: true })
    } catch (error) {
      if (isApiError(error) && error.status === 401) {
        toast.error('Please sign in again', { description: errorMessage(error) })
        navigate('/login', { replace: true })
        return
      }
      toast.error('Could not sign in with that role', { description: errorMessage(error) })
    } finally {
      setSubmitting(null)
    }
  }

  function notYou() {
    cancelRoleSelection()
    navigate('/login', { replace: true })
  }

  return (
    <AuthLayout
      title="Choose how to sign in"
      description={`${user.full_name || user.email}, your account has more than one role. Pick the one to use now; you can switch any time from the account menu.`}
      footer={
        <>
          Not you?{' '}
          <button
            type="button"
            onClick={notYou}
            className="font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Sign out
          </button>
        </>
      }
    >
      <div className="space-y-3" role="list" aria-label="Available roles">
        {roles.map((role) => {
          const Icon = ROLE_ICONS[role] ?? UserRound
          const busy = submitting === role
          return (
            <button
              key={role}
              type="button"
              role="listitem"
              disabled={submitting !== null}
              onClick={() => void choose(role)}
              className={cn(
                'flex w-full items-center gap-3 rounded-lg border border-border bg-card p-4 text-left transition-colors',
                'hover:border-primary/60 hover:bg-accent/40',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                'disabled:cursor-not-allowed disabled:opacity-60',
              )}
            >
              <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                <Icon className="size-5" aria-hidden />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-semibold">{roleLabel(role)}</span>
                <span className="block text-sm text-muted-foreground">{roleDescription(role)}</span>
              </span>
              {busy ? <Spinner size="sm" label={`Signing in as ${roleLabel(role)}`} /> : null}
            </button>
          )
        })}
      </div>

      <div className="mt-4 flex items-center gap-2">
        <Checkbox
          id="remember-role"
          checked={remember}
          onCheckedChange={(value) => setRemember(value === true)}
          disabled={submitting !== null}
        />
        <Label htmlFor="remember-role" className="text-sm font-normal">
          Remember on this device
        </Label>
      </div>
    </AuthLayout>
  )
}
