import { zodResolver } from '@hookform/resolvers/zod'
import * as React from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
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
import { Textarea } from '@/components/ui/textarea'
import { INTERVIEW_TYPE_LABELS } from '@/lib/utils'
import { fromDateTimeLocalValue, toDateTimeLocalValue } from '@/features/automation/datetime'
import { ApplicationPicker } from '@/features/emails/components/ApplicationPicker'
import { INTERVIEW_STATUS_LABELS } from '@/features/interviews/helpers'
import {
  INTERVIEW_STATUSES,
  INTERVIEW_TYPES,
  type ApplicationStatus,
  type InterviewRead,
  type InterviewType,
  type UUID,
} from '@/types/api'

/** Statuses an interview can realistically belong to (spec §19). */
export const INTERVIEW_APPLICATION_STATUSES: ApplicationStatus[] = [
  'INTERVIEW',
  'ASSESSMENT',
  'RECRUITER_CONTACTED',
  'APPLIED',
]

const schema = z.object({
  interview_type: z.enum(INTERVIEW_TYPES),
  status: z.enum(INTERVIEW_STATUSES),
  round_number: z.coerce.number().int().min(1, 'Round 1 or later').max(20, 'At most round 20'),
  scheduled_at: z.string().optional(),
  duration_minutes: z
    .union([z.literal(''), z.coerce.number().int().min(1, 'At least a minute').max(1440, 'At most 24 hours')])
    .optional(),
  location_or_link: z.string().max(1000).optional(),
  interviewer: z.string().max(255).optional(),
  notes: z.string().optional(),
})

type FormValues = z.infer<typeof schema>

export interface InterviewFormSubmit {
  application_id?: UUID
  interview_type: InterviewType
  status: FormValues['status']
  round_number: number
  scheduled_at: string | null
  duration_minutes: number | null
  location_or_link: string | null
  interviewer: string | null
  notes: string | null
}

export interface InterviewFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Editing an existing round, or `null` to create a new one. */
  interview?: InterviewRead | null
  saving?: boolean
  onSubmit: (values: InterviewFormSubmit) => Promise<void> | void
}

/** Create or edit one interview round. */
export function InterviewFormDialog({
  open,
  onOpenChange,
  interview = null,
  saving = false,
  onSubmit,
}: InterviewFormDialogProps) {
  const isEdit = Boolean(interview)
  const [applicationId, setApplicationId] = React.useState<UUID | null>(interview?.application_id ?? null)
  const [applicationError, setApplicationError] = React.useState(false)

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      interview_type: 'TECHNICAL',
      status: 'SCHEDULED',
      round_number: 1,
      scheduled_at: '',
      duration_minutes: 60,
      location_or_link: '',
      interviewer: '',
      notes: '',
    },
  })

  const { reset } = form
  React.useEffect(() => {
    if (!open) return
    setApplicationError(false)
    setApplicationId(interview?.application_id ?? null)
    reset({
      interview_type: interview?.interview_type ?? 'TECHNICAL',
      status: interview?.status ?? 'SCHEDULED',
      round_number: interview?.round_number ?? 1,
      scheduled_at: toDateTimeLocalValue(interview?.scheduled_at),
      duration_minutes: interview?.duration_minutes ?? 60,
      location_or_link: interview?.location_or_link ?? '',
      interviewer: interview?.interviewer ?? '',
      notes: interview?.notes ?? '',
    })
  }, [open, interview, reset])

  async function handleSubmit(parsed: FormValues) {
    if (!isEdit && !applicationId) {
      setApplicationError(true)
      return
    }
    await onSubmit({
      application_id: applicationId ?? undefined,
      interview_type: parsed.interview_type,
      status: parsed.status,
      round_number: parsed.round_number,
      scheduled_at: fromDateTimeLocalValue(parsed.scheduled_at),
      duration_minutes: typeof parsed.duration_minutes === 'number' ? parsed.duration_minutes : null,
      location_or_link: parsed.location_or_link?.trim() || null,
      interviewer: parsed.interviewer?.trim() || null,
      notes: parsed.notes?.trim() || null,
    })
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (saving ? undefined : onOpenChange(next))}>
      <DialogContent className="max-h-[90vh] max-w-xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit interview' : 'Add interview'}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? 'Update the round — rescheduling, adding the joining link or recording how it went.'
              : 'Interviews appear here automatically when an email moves an application to Interview. Add one by hand when you heard some other way.'}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
            {isEdit ? (
              <div className="rounded-lg border border-border bg-muted/30 p-3 text-sm">
                <p className="font-medium">{interview?.company_name ?? 'Application'}</p>
                <p className="text-muted-foreground">{interview?.job_title ?? ''}</p>
              </div>
            ) : (
              <div className="space-y-1">
                <ApplicationPicker
                  value={applicationId}
                  onChange={(id) => {
                    setApplicationId(id)
                    setApplicationError(false)
                  }}
                  statuses={INTERVIEW_APPLICATION_STATUSES}
                  label="Which application?"
                  emptyHint="No applications are at interview stage yet."
                />
                {applicationError ? (
                  <p className="text-xs font-medium text-destructive">Pick the application this round is for.</p>
                ) : null}
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="interview_type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Type</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {INTERVIEW_TYPES.map((type) => (
                          <SelectItem key={type} value={type}>
                            {INTERVIEW_TYPE_LABELS[type]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="round_number"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Round</FormLabel>
                    <FormControl>
                      <Input type="number" min={1} max={20} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="scheduled_at"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>When</FormLabel>
                    <FormControl>
                      <Input type="datetime-local" {...field} />
                    </FormControl>
                    <FormDescription>Leave empty if the time is not fixed yet.</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="duration_minutes"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Duration (minutes)</FormLabel>
                    <FormControl>
                      <Input type="number" min={1} max={1440} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="location_or_link"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Location or joining link</FormLabel>
                  <FormControl>
                    <Input placeholder="https://meet.google.com/… or an office address" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="interviewer"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Interviewer</FormLabel>
                    <FormControl>
                      <Input placeholder="Name or panel" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="status"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Status</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {INTERVIEW_STATUSES.map((status) => (
                          <SelectItem key={status} value={status}>
                            {INTERVIEW_STATUS_LABELS[status]}
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
              name="notes"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Notes</FormLabel>
                  <FormControl>
                    <Textarea rows={3} placeholder="What to focus on, who is on the panel, anything else." {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
                Cancel
              </Button>
              <Button type="submit" loading={saving}>
                {isEdit ? 'Save changes' : 'Add interview'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
