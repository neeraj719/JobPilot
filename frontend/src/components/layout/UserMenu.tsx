import { Check, LogOut, Repeat, Settings, UserRound } from 'lucide-react'
import * as React from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { errorMessage } from '@/lib/api'
import { queryClient } from '@/lib/queryClient'
import { roleLabel } from '@/lib/roles'
import { initials } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth'

export function UserMenu() {
  const user = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)
  const activeRole = useAuthStore((state) => state.activeRole)
  const availableRoles = useAuthStore((state) => state.availableRoles)
  const switchRole = useAuthStore((state) => state.switchRole)
  const navigate = useNavigate()
  const [pending, setPending] = React.useState(false)

  async function handleSwitchRole(role: string) {
    if (role === activeRole) return
    setPending(true)
    try {
      await switchRole(role)
      // Everything on screen was fetched as the previous role: refetch it as the new one.
      await queryClient.invalidateQueries()
      toast.success(`Now acting as ${roleLabel(role)}`)
    } catch (error) {
      toast.error('Could not switch role', { description: errorMessage(error) })
    } finally {
      setPending(false)
    }
  }

  async function handleLogout() {
    setPending(true)
    try {
      await logout()
      queryClient.clear()
      toast.success('Signed out')
      navigate('/login', { replace: true })
    } finally {
      setPending(false)
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="h-9 gap-2 px-1.5 sm:px-2" aria-label="Account menu">
          <Avatar className="size-7">
            <AvatarFallback className="bg-primary/10 text-primary">{initials(user?.full_name ?? user?.email)}</AvatarFallback>
          </Avatar>
          <span className="hidden max-w-32 truncate text-sm font-medium sm:inline">
            {user?.full_name ?? user?.email ?? 'Account'}
          </span>
          {activeRole && availableRoles.length > 1 ? (
            <Badge variant={activeRole === 'ADMIN' ? 'default' : 'secondary'} className="hidden sm:inline-flex">
              {roleLabel(activeRole)}
            </Badge>
          ) : null}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <div className="px-2 py-1.5">
          <div className="flex items-center gap-2">
            <p className="min-w-0 flex-1 truncate text-sm font-medium">{user?.full_name ?? 'Signed in'}</p>
            {activeRole ? (
              <Badge variant={activeRole === 'ADMIN' ? 'default' : 'secondary'} aria-label={`Active role: ${roleLabel(activeRole)}`}>
                {roleLabel(activeRole)}
              </Badge>
            ) : null}
          </div>
          <p className="truncate text-xs text-muted-foreground">{user?.email ?? ''}</p>
        </div>
        <DropdownMenuSeparator />
        {availableRoles.length > 1 ? (
          <>
            <DropdownMenuSub>
              <DropdownMenuSubTrigger disabled={pending}>
                <Repeat />
                Switch role
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent>
                {availableRoles.map((role) => (
                  <DropdownMenuItem
                    key={role}
                    disabled={pending}
                    onSelect={() => void handleSwitchRole(role)}
                    aria-current={role === activeRole ? 'true' : undefined}
                  >
                    {role === activeRole ? <Check /> : <span className="size-4" aria-hidden />}
                    {roleLabel(role)}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuSubContent>
            </DropdownMenuSub>
            <DropdownMenuSeparator />
          </>
        ) : null}
        <DropdownMenuItem onSelect={() => navigate('/profile')}>
          <UserRound />
          Profile
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => navigate('/settings')}>
          <Settings />
          Settings
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          destructive
          disabled={pending}
          onSelect={(event) => {
            event.preventDefault()
            void handleLogout()
          }}
        >
          <LogOut />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
