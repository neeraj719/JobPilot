import { ArrowRight, BriefcaseBusiness, Check, ShieldCheck, UserRound } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import * as React from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import { AuthLayout } from '@/components/layout/AuthLayout'
import { ACCOUNT_STRIP, CHOOSE_ROLE_COPY, ROLE_LIST, ROLE_ROW } from '@/components/layout/authShell'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { errorMessage, isApiError } from '@/lib/api'
import { getPreferredRole, roleDescription, roleLabel } from '@/lib/roles'
import { cn, initials } from '@/lib/utils'
import { isLauncherPath } from '@/modules/registry'
import { useAuthStore } from '@/stores/auth'

const ROLE_ICONS: Record<string, LucideIcon> = {
  ADMIN: ShieldCheck,
  USER: UserRound,
}

/**
 * Shown after the password step when the account holds more than one role (reachable only
 * while a selection is pending — `RoleSelectionRoute`). v2: the shared split `AuthLayout`, a
 * glass card, role options as a keyboard radio group (arrows move, Enter continues), one
 * gradient "Continue" and a quiet "Sign out". `AuthSkeleton variant="roles"` mirrors it.
 */
export default function ChooseRolePage() {
  useDocumentTitle('Choose a role')
  const navigate = useNavigate()
  const location = useLocation()
  const pending = useAuthStore((state) => state.pendingRoleSelection)
  const selectRole = useAuthStore((state) => state.selectRole)
  const logout = useAuthStore((state) => state.logout)
  const roles = pending?.roles ?? []
  const [selected, setSelected] = React.useState<string | null>(() => {
    const preferred = getPreferredRole(pending?.user.id)
    return preferred && roles.includes(preferred) ? preferred : (roles[0] ?? null)
  })
  const [remember, setRemember] = React.useState(false)
  const [submitting, setSubmitting] = React.useState(false)
  const optionRefs = React.useRef<(HTMLButtonElement | null)[]>([])

  const from = (location.state as { from?: string } | null)?.from
  const redirectTo = from && !isLauncherPath(from) ? from : '/home'
  const redirectState = redirectTo === '/home' ? { entry: true } : undefined

  if (!pending) return null
  const { user } = pending

  async function choose() {
    if (!selected || submitting) return
    setSubmitting(true)
    try {
      await selectRole(selected, remember)
      toast.success(`Signed in as ${roleLabel(selected)}`, { description: `Welcome back, ${user.full_name || user.email}` })
      navigate(redirectTo, { replace: true, state: redirectState })
    } catch (error) {
      if (isApiError(error) && error.status === 401) {
        toast.error('Please sign in again', { description: errorMessage(error) })
        navigate('/?auth=login', { replace: true, state: { from } })
        return
      }
      toast.error('Could not sign in with that role', { description: errorMessage(error) })
    } finally {
      setSubmitting(false)
    }
  }

  function notYou() {
    // The one sign-out (clears the pending selection with everything else), then the landing page.
    void logout('user').then(() => navigate('/', { replace: true }))
  }

  /** Radio-group keyboard model: arrows / Home / End move the selection (and focus), Enter continues. */
  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const index = Math.max(0, roles.indexOf(selected ?? ''))
    let next: number | null = null
    if (event.key === 'ArrowDown' || event.key === 'ArrowRight') next = (index + 1) % roles.length
    else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') next = (index - 1 + roles.length) % roles.length
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = roles.length - 1
    else if (event.key === 'Enter') {
      event.preventDefault()
      void choose()
      return
    }
    if (next === null) return
    event.preventDefault()
    setSelected(roles[next])
    optionRefs.current[next]?.focus()
  }

  return (
    <AuthLayout
      title={CHOOSE_ROLE_COPY.title}
      description={CHOOSE_ROLE_COPY.description}
      heroTitle={CHOOSE_ROLE_COPY.heroTitle}
      footer={
        <>
          Not you?{' '}
          <button
            type="button"
            onClick={notYou}
            disabled={submitting}
            className="rounded-sm font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Sign out
          </button>
        </>
      }
    >
      <div className="space-y-4">
        <div className={ACCOUNT_STRIP}>
          <Avatar className="size-8">
            <AvatarFallback className="bg-primary/10 text-xs text-primary">{initials(user.full_name || user.email)}</AvatarFallback>
          </Avatar>
          <span className="min-w-0 flex-1 text-left">
            <span className="block truncate text-sm font-semibold">{user.full_name || user.email}</span>
            <span className="block truncate text-xs text-muted-foreground">{user.email}</span>
          </span>
        </div>

        <div role="radiogroup" aria-label="Role" className={ROLE_LIST} onKeyDown={onKeyDown}>
          {roles.map((role, index) => {
            const Icon = ROLE_ICONS[role] ?? BriefcaseBusiness
            const isSelected = role === selected
            return (
              <button
                key={role}
                ref={(node) => {
                  optionRefs.current[index] = node
                }}
                type="button"
                role="radio"
                aria-checked={isSelected}
                tabIndex={isSelected ? 0 : -1}
                disabled={submitting}
                onClick={() => setSelected(role)}
                className={cn(
                  ROLE_ROW,
                  'flex w-full items-center gap-3 rounded-2xl p-4 text-left transition-[box-shadow,transform] duration-150',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
                  'disabled:cursor-not-allowed disabled:opacity-60',
                  isSelected ? 'border-gradient shadow-sm dark:shadow-highlight' : 'border border-border bg-card hover:border-primary/50',
                )}
              >
                <span
                  className={cn(
                    'flex size-10 shrink-0 items-center justify-center rounded-xl',
                    isSelected ? 'bg-gradient-brand text-gradient-foreground shadow-glow' : 'bg-primary/10 text-primary',
                  )}
                >
                  <Icon className="size-5" aria-hidden />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold">{roleLabel(role)}</span>
                  <span className="block truncate text-sm text-muted-foreground">{roleDescription(role)}</span>
                </span>
                <span
                  aria-hidden
                  className={cn(
                    'flex size-5 shrink-0 items-center justify-center rounded-full',
                    isSelected ? 'bg-gradient-brand text-gradient-foreground' : 'ring-1 ring-inset ring-input',
                  )}
                >
                  {isSelected ? <Check className="size-3.5" strokeWidth={3} /> : null}
                </span>
              </button>
            )
          })}
        </div>

        <div className="flex h-5 items-center gap-2">
          <Checkbox id="remember-role" checked={remember} onCheckedChange={(value) => setRemember(value === true)} disabled={submitting} />
          <Label htmlFor="remember-role" className="text-sm font-normal">
            Remember my choice on this device
          </Label>
        </div>

        <Button
          type="button"
          size="lg"
          className="h-12 w-full text-base hover:-translate-y-0.5 motion-reduce:hover:translate-y-0 dark:shadow-glow"
          loading={submitting}
          disabled={!selected}
          onClick={() => void choose()}
        >
          Continue{selected ? ` as ${roleLabel(selected)}` : ''}
          {!submitting ? <ArrowRight /> : null}
        </Button>
      </div>
    </AuthLayout>
  )
}
