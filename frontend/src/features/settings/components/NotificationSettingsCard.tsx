import { Laptop } from 'lucide-react'
import * as React from 'react'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { toast } from '@/components/ui/toaster'
import { NOTIFICATION_TYPE_LABELS } from '@/lib/utils'
import {
  NOTIFICATION_PREFERENCE_TYPES,
  defaultNotificationPreferences,
  readNotificationPreferences,
  writeNotificationPreferences,
  type NotificationPreferenceType,
  type NotificationPreferences,
} from '@/features/settings/schema'

/**
 * Per-type notification toggles. The API has no preference endpoint, so these are stored
 * in `localStorage` and clearly labelled as a device setting.
 */
export function NotificationSettingsCard() {
  const [preferences, setPreferences] = React.useState<NotificationPreferences>(() => readNotificationPreferences())

  const update = (type: NotificationPreferenceType, enabled: boolean) => {
    const next = { ...preferences, [type]: enabled }
    setPreferences(next)
    writeNotificationPreferences(next)
  }

  const resetAll = () => {
    const next = defaultNotificationPreferences()
    setPreferences(next)
    writeNotificationPreferences(next)
    toast.success('Notification settings reset', { description: 'Every type is shown again on this device.' })
  }

  const hiddenCount = NOTIFICATION_PREFERENCE_TYPES.filter((type) => !preferences[type]).length

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Notifications</CardTitle>
        <CardDescription>Which notification types appear in the bell menu.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Alert>
          <Laptop aria-hidden />
          <AlertDescription>
            <strong>Device setting.</strong> The API stores every notification regardless; this only filters what this
            browser shows you, and it does not sync to your other devices.
          </AlertDescription>
        </Alert>

        <ul className="divide-y divide-border rounded-lg border border-border">
          {NOTIFICATION_PREFERENCE_TYPES.map((type) => (
            <li key={type} className="flex items-center justify-between gap-4 p-3">
              <Label htmlFor={`notify-${type}`} className="font-normal">
                {NOTIFICATION_TYPE_LABELS[type]}
              </Label>
              <Switch
                id={`notify-${type}`}
                checked={preferences[type]}
                onCheckedChange={(checked) => update(type, checked)}
              />
            </li>
          ))}
        </ul>

        <div className="flex items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">
            {hiddenCount === 0 ? 'All types are shown.' : `${hiddenCount} type${hiddenCount === 1 ? '' : 's'} hidden.`}
          </p>
          <Button type="button" variant="ghost" size="sm" onClick={resetAll} disabled={hiddenCount === 0}>
            Show all again
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
