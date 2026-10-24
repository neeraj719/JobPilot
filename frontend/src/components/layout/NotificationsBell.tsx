import { Bell, CheckCheck } from 'lucide-react'
import * as React from 'react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
  useUnreadCount,
} from '@/features/notifications/api'
import { cn, formatRelative, notificationColor } from '@/lib/utils'
import type { NotificationRead } from '@/types/api'

export function NotificationsBell() {
  const [open, setOpen] = React.useState(false)
  const navigate = useNavigate()

  const unread = useUnreadCount()
  const list = useNotifications({ page: 1, page_size: 10 })
  const markRead = useMarkNotificationRead()
  const markAllRead = useMarkAllNotificationsRead()

  const count = unread.data?.count ?? 0
  const items = list.data?.items ?? []

  function handleOpen(notification: NotificationRead) {
    if (!notification.is_read) markRead.mutate(notification.id)
    setOpen(false)
    if (notification.link) navigate(notification.link)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label={`Notifications${count ? `, ${count} unread` : ''}`}>
          <Bell />
          {count > 0 ? (
            <span className="absolute -right-0.5 -top-0.5 flex min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold leading-4 text-destructive-foreground">
              {count > 99 ? '99+' : count}
            </span>
          ) : null}
        </Button>
      </PopoverTrigger>

      <PopoverContent align="end" className="w-[22rem] p-0">
        <div className="flex items-center justify-between px-4 py-3">
          <div>
            <p className="text-sm font-semibold">Notifications</p>
            <p className="text-xs text-muted-foreground">
              {count > 0 ? `${count} unread` : 'You are all caught up'}
            </p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            disabled={count === 0 || markAllRead.isPending}
            onClick={() => markAllRead.mutate()}
          >
            <CheckCheck />
            Mark all
          </Button>
        </div>
        <Separator />

        <ScrollArea className="max-h-96">
          {list.isLoading ? (
            <div role="status" aria-busy="true">
              <span className="sr-only">Loading notifications</span>
              {/* Same rows as the list below: unread dot, title, body, time. */}
              <ul className="divide-y divide-border" aria-hidden>
                {Array.from({ length: 3 }, (_, index) => (
                  <li key={index} className="flex items-start gap-3 px-4 py-3">
                    <Skeleton className="mt-1.5 size-2 shrink-0 rounded-full" />
                    <div className="min-w-0 flex-1 space-y-0.5">
                      <div className="flex h-5 items-center">
                        <Skeleton className={index % 2 ? 'h-3.5 w-1/2' : 'h-3.5 w-3/4'} />
                      </div>
                      <div className="flex h-4 items-center">
                        <Skeleton className="h-3 w-full" />
                      </div>
                      <div className="flex h-4 items-center">
                        <Skeleton className="h-2.5 w-16" />
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ) : items.length === 0 ? (
            <p className="px-4 py-10 text-center text-sm text-muted-foreground">No notifications yet.</p>
          ) : (
            <ul className="divide-y divide-border">
              {items.map((notification) => (
                <li key={notification.id}>
                  <button
                    type="button"
                    onClick={() => handleOpen(notification)}
                    className={cn(
                      'flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-accent focus-visible:outline-none focus-visible:bg-accent',
                      !notification.is_read && 'bg-primary/[0.04]',
                    )}
                  >
                    <span
                      className={cn(
                        'mt-1.5 size-2 shrink-0 rounded-full',
                        notification.is_read ? 'bg-transparent' : 'bg-primary',
                      )}
                      aria-hidden
                    />
                    <span className="min-w-0 flex-1 space-y-0.5">
                      <span className={cn('block truncate text-sm font-medium', notificationColor(notification.type))}>
                        {notification.title}
                      </span>
                      {notification.body ? (
                        <span className="line-clamp-2 block text-xs text-muted-foreground">{notification.body}</span>
                      ) : null}
                      <span className="block text-[11px] text-muted-foreground/80">
                        {formatRelative(notification.created_at)}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </ScrollArea>

        <Separator />
        <div className="p-2">
          <Button
            variant="ghost"
            size="sm"
            className="w-full"
            onClick={() => {
              setOpen(false)
              navigate('/settings')
            }}
          >
            Notification settings
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}
