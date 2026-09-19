import { zodResolver } from '@hookform/resolvers/zod'
import { TriangleAlert } from 'lucide-react'
import * as React from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import type { AutomationConfigRead, AutomationConfigUpdate } from '@/types/api'

/** Mirrors `automation.service.validate_config_update` so errors surface before the request. */
export const MAX_DAILY_APPLICATION_LIMIT = 100

const schema = z.object({
  schedule_time: z
    .string()
    .regex(/^([01]\d|2[0-3]):[0-5]\d$/, 'Use HH:MM in 24-hour format'),
  timezone: z.string().min(1, 'Pick a timezone'),
  daily_application_limit: z.coerce
    .number()
    .int('Whole applications only')
    .min(1, 'At least 1 application a day')
    .max(MAX_DAILY_APPLICATION_LIMIT, `The server caps this at ${MAX_DAILY_APPLICATION_LIMIT}`),
  min_match_score: z.coerce.number().int().min(0, 'Between 0 and 100').max(100, 'Between 0 and 100'),
  only_posted_within_hours: z.coerce
    .number()
    .int()
    .min(1, 'At least 1 hour')
    .max(24 * 30, 'At most 720 hours (30 days)'),
  prioritize_priority_companies: z.boolean(),
  auto_submit_enabled: z.boolean(),
})

export type AutomationConfigFormValues = z.infer<typeof schema>

/** A short, sensible list; the current value is always included so nothing is lost. */
const COMMON_TIMEZONES = [
  'Asia/Kolkata',
  'Asia/Dubai',
  'Asia/Singapore',
  'Asia/Tokyo',
  'Australia/Sydney',
  'Europe/London',
  'Europe/Berlin',
  'America/New_York',
  'America/Chicago',
  'America/Los_Angeles',
  'UTC',
]

export interface AutomationConfigSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  config: AutomationConfigRead | undefined
  saving?: boolean
  onSubmit: (values: AutomationConfigUpdate) => Promise<void> | void
}

/**
 * Quick-edit for the rails the pipeline respects. Writes through the same
 * `PUT /automation/config` the Settings page uses, with matching validation.
 */
export function AutomationConfigSheet({ open, onOpenChange, config, saving = false, onSubmit }: AutomationConfigSheetProps) {
  const form = useForm<AutomationConfigFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      schedule_time: '09:00',
      timezone: 'Asia/Kolkata',
      daily_application_limit: 20,
      min_match_score: 75,
      only_posted_within_hours: 24,
      prioritize_priority_companies: true,
      auto_submit_enabled: false,
    },
  })

  const { reset } = form
  React.useEffect(() => {
    if (!open || !config) return
    reset({
      schedule_time: config.schedule_time,
      timezone: config.timezone,
      daily_application_limit: config.daily_application_limit,
      min_match_score: config.min_match_score,
      only_posted_within_hours: config.only_posted_within_hours,
      prioritize_priority_companies: config.prioritize_priority_companies,
      auto_submit_enabled: config.auto_submit_enabled,
    })
  }, [open, config, reset])

  const timezones = React.useMemo(() => {
    const zones = new Set(COMMON_TIMEZONES)
    if (config?.timezone) zones.add(config.timezone)
    return [...zones].sort()
  }, [config?.timezone])

  const autoSubmit = form.watch('auto_submit_enabled')

  async function handleSubmit(values: AutomationConfigFormValues) {
    await onSubmit(values)
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="flex w-full flex-col gap-0 overflow-y-auto p-0 sm:max-w-md">
        <SheetHeader className="border-b border-border">
          <SheetTitle>Automation settings</SheetTitle>
          <SheetDescription>
            The rails every run respects. These are the same values the Settings page writes.
          </SheetDescription>
        </SheetHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(handleSubmit)} className="flex flex-1 flex-col">
            <div className="flex-1 space-y-5 p-6">
              <div className="grid gap-4 sm:grid-cols-2">
                <FormField
                  control={form.control}
                  name="schedule_time"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Run at</FormLabel>
                      <FormControl>
                        <Input type="time" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="timezone"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Timezone</FormLabel>
                      <Select value={field.value} onValueChange={field.onChange}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Pick a timezone" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {timezones.map((zone) => (
                            <SelectItem key={zone} value={zone}>
                              {zone}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <FormField
                control={form.control}
                name="daily_application_limit"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Daily application limit</FormLabel>
                    <FormControl>
                      <Input type="number" min={1} max={MAX_DAILY_APPLICATION_LIMIT} {...field} />
                    </FormControl>
                    <FormDescription>
                      The run stops once it has sent this many today. The server caps it at{' '}
                      {MAX_DAILY_APPLICATION_LIMIT}.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="min_match_score"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Minimum match score</FormLabel>
                    <FormControl>
                      <Input type="number" min={0} max={100} {...field} />
                    </FormControl>
                    <FormDescription>Jobs scoring below this are never queued.</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="only_posted_within_hours"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Only jobs posted within (hours)</FormLabel>
                    <FormControl>
                      <Input type="number" min={1} max={24 * 30} {...field} />
                    </FormControl>
                    <FormDescription>Older postings are usually already closed.</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="prioritize_priority_companies"
                render={({ field }) => (
                  <FormItem className="flex items-start justify-between gap-4 rounded-lg border border-border p-3">
                    <div className="space-y-0.5">
                      <FormLabel>Prioritise P1 companies</FormLabel>
                      <FormDescription>Dream companies use the day's budget first.</FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="auto_submit_enabled"
                render={({ field }) => (
                  <FormItem className="flex items-start justify-between gap-4 rounded-lg border border-border p-3">
                    <div className="space-y-0.5">
                      <FormLabel>Auto-submit applications</FormLabel>
                      <FormDescription>
                        Off means every prepared application waits in your review queue.
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              {autoSubmit ? (
                <p
                  role="alert"
                  className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/5 p-3 text-sm text-muted-foreground"
                >
                  <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
                  <span>
                    With auto-submit on, applications are sent <strong>without</strong> you seeing them first. The
                    automation still stops for CAPTCHAs, logins and questions it cannot answer.
                  </span>
                </p>
              ) : null}
            </div>

            <SheetFooter className="sticky bottom-0 border-t border-border bg-background">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
                Cancel
              </Button>
              <Button type="submit" loading={saving}>
                Save settings
              </Button>
            </SheetFooter>
          </form>
        </Form>
      </SheetContent>
    </Sheet>
  )
}
