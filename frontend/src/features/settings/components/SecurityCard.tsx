import { zodResolver } from '@hookform/resolvers/zod'
import { KeyRound, LogOut, MonitorSmartphone } from 'lucide-react'
import * as React from 'react'
import { useForm } from 'react-hook-form'

import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { LoadingState } from '@/components/common/LoadingState'
import { SourceBadge } from '@/components/common/SourceBadge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { toast } from '@/components/ui/toaster'
import { useAuth } from '@/hooks/useAuth'
import { errorMessage } from '@/lib/api'
import { formatDateTime, formatRelative, humanizeEnum } from '@/lib/utils'
import { Field } from '@/features/profile/components/SectionCard'
import { useBrowserSessions, useChangePassword, useRevokeBrowserSession } from '@/features/settings/api'
import { DeviceSessionsCard } from '@/features/settings/components/DeviceSessionsCard'
import { passwordSchema, type PasswordValues } from '@/features/settings/schema'
import type { BrowserSessionRead } from '@/types/api'

const FORM_ID = 'change-password-form'

function ChangePasswordCard() {
  const changePassword = useChangePassword()
  const form = useForm<PasswordValues>({
    resolver: zodResolver(passwordSchema),
    defaultValues: { current_password: '', new_password: '', confirm_password: '' },
  })
  const { register, handleSubmit, reset, formState } = form
  const errors = formState.errors

  const onSubmit = handleSubmit(async (values) => {
    try {
      await changePassword.mutateAsync({
        current_password: values.current_password,
        new_password: values.new_password,
      })
      reset({ current_password: '', new_password: '', confirm_password: '' })
      toast.success('Password changed', { description: 'Your other devices have been signed out.' })
    } catch (error) {
      toast.error('Could not change your password', { description: errorMessage(error) })
    }
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <KeyRound className="size-4" aria-hidden />
          Change password
        </CardTitle>
        <CardDescription>
          At least 8 characters with a letter and a digit. Other devices are signed out afterwards.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form id={FORM_ID} onSubmit={onSubmit} className="space-y-4" noValidate>
          <Field label="Current password" htmlFor="current_password" error={errors.current_password?.message}>
            <Input
              id="current_password"
              type="password"
              autoComplete="current-password"
              {...register('current_password')}
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="New password" htmlFor="new_password" error={errors.new_password?.message}>
              <Input id="new_password" type="password" autoComplete="new-password" {...register('new_password')} />
            </Field>
            <Field label="Repeat new password" htmlFor="confirm_password" error={errors.confirm_password?.message}>
              <Input
                id="confirm_password"
                type="password"
                autoComplete="new-password"
                {...register('confirm_password')}
              />
            </Field>
          </div>
        </form>
      </CardContent>
      <CardFooter className="justify-end border-t bg-muted/30 py-3">
        <Button type="submit" form={FORM_ID} size="sm" loading={changePassword.isPending}>
          Change password
        </Button>
      </CardFooter>
    </Card>
  )
}

function BrowserSessionsCard() {
  const sessions = useBrowserSessions()
  const revoke = useRevokeBrowserSession()
  const [pending, setPending] = React.useState<BrowserSessionRead | null>(null)

  const confirmRevoke = async () => {
    if (!pending) return
    try {
      await revoke.mutateAsync(pending.id)
      toast.success('Browser session forgotten', { description: 'Stored cookies for that site were deleted.' })
      setPending(null)
    } catch (error) {
      toast.error('Could not revoke the session', { description: errorMessage(error) })
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <MonitorSmartphone className="size-4" aria-hidden />
          Stored browser sessions
        </CardTitle>
        <CardDescription>
          Cookies the automation keeps so it does not have to sign in again. The stored state itself is encrypted and
          never shown.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {sessions.isLoading ? (
          <LoadingState variant="list" rows={2} />
        ) : sessions.error ? (
          <ErrorState error={sessions.error} size="sm" onRetry={() => void sessions.refetch()} />
        ) : (sessions.data?.length ?? 0) === 0 ? (
          <EmptyState
            size="sm"
            icon={MonitorSmartphone}
            title="No stored sessions"
            description="Nothing is being kept. A session appears here the first time the automation signs in to a platform for you."
          />
        ) : (
          <ul className="divide-y divide-border rounded-lg border border-border">
            {sessions.data?.map((session) => (
              <li key={session.id} className="flex flex-wrap items-center justify-between gap-3 p-3">
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <SourceBadge source={session.source} />
                    <Badge variant={session.status === 'ACTIVE' ? 'success' : 'muted'}>
                      {humanizeEnum(session.status)}
                    </Badge>
                  </div>
                  <p className="truncate text-xs text-muted-foreground">
                    {session.last_used_at ? `Last used ${formatRelative(session.last_used_at)}` : 'Never used'}
                    {session.expires_at ? ` · expires ${formatDateTime(session.expires_at)}` : ''}
                  </p>
                </div>
                <Button type="button" variant="outline" size="sm" onClick={() => setPending(session)}>
                  Revoke
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>

      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(open) => {
          if (!open) setPending(null)
        }}
        title="Forget this browser session?"
        description="The stored cookies are deleted. The automation will have to sign in again — and will pause and ask you if it cannot."
        confirmLabel="Revoke session"
        variant="destructive"
        loading={revoke.isPending}
        onConfirm={confirmRevoke}
      />
    </Card>
  )
}

function SignOutCard() {
  const { logout, user } = useAuth()
  const [open, setOpen] = React.useState(false)
  const [busy, setBusy] = React.useState(false)

  const confirm = async () => {
    setBusy(true)
    try {
      await logout()
      toast.success('Signed out')
    } catch (error) {
      toast.error('Could not sign out', { description: errorMessage(error) })
    } finally {
      setBusy(false)
      setOpen(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <LogOut className="size-4" aria-hidden />
          Sign out
        </CardTitle>
        <CardDescription>
          Revokes this browser&apos;s session for {user?.email ?? 'this account'}. To sign out other devices, use
          Sessions and devices above.
        </CardDescription>
      </CardHeader>
      <CardFooter className="justify-end border-t bg-muted/30 py-3">
        <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)}>
          Sign out of this device
        </Button>
      </CardFooter>

      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Sign out of this device?"
        description="This browser's session is revoked and it will need your password again. Other devices stay signed in."
        confirmLabel="Sign out"
        loading={busy}
        onConfirm={confirm}
      />
    </Card>
  )
}

export function SecurityCard() {
  return (
    <div className="space-y-6">
      <ChangePasswordCard />
      <DeviceSessionsCard />
      <BrowserSessionsCard />
      <SignOutCard />
    </div>
  )
}
