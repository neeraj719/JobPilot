import { FlaskConical } from 'lucide-react'
import * as React from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { EMAIL_CLASSIFICATION_LABELS } from '@/lib/utils'
import { ApplicationPicker } from '@/features/emails/components/ApplicationPicker'
import {
  EMAIL_CLASSIFICATIONS,
  type EmailClassification,
  type EmailSimulateRequest,
  type UUID,
} from '@/types/api'

export interface SimulateEmailDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  saving?: boolean
  onSubmit: (payload: EmailSimulateRequest) => Promise<void> | void
}

/**
 * Demo tool. `POST /emails/simulate` injects a realistic recruiter message so the whole
 * inbox → classify → link → status flow can be shown without connecting a real mailbox.
 */
export function SimulateEmailDialog({ open, onOpenChange, saving = false, onSubmit }: SimulateEmailDialogProps) {
  const [kind, setKind] = React.useState<EmailClassification>('APPLICATION_RECEIVED')
  const [applicationId, setApplicationId] = React.useState<UUID | null>(null)
  const [subject, setSubject] = React.useState('')
  const [body, setBody] = React.useState('')

  React.useEffect(() => {
    if (!open) return
    setKind('APPLICATION_RECEIVED')
    setApplicationId(null)
    setSubject('')
    setBody('')
  }, [open])

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    void onSubmit({
      kind,
      application_id: applicationId,
      subject: subject.trim() || null,
      body: body.trim() || null,
    })
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (saving ? undefined : onOpenChange(next))}>
      <DialogContent className="max-h-[90vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FlaskConical className="size-4 text-info" aria-hidden />
            Simulate an email
            <span className="rounded-full border border-info/25 bg-info/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-info">
              Demo tool
            </span>
          </DialogTitle>
          <DialogDescription>
            Injects a realistic message as if it had arrived in your inbox, then classifies and links it exactly
            like a real one. Nothing is sent anywhere.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="simulate-kind">Kind of email</Label>
            <Select value={kind} onValueChange={(value) => setKind(value as EmailClassification)}>
              <SelectTrigger id="simulate-kind">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {EMAIL_CLASSIFICATIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {EMAIL_CLASSIFICATION_LABELS[option]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <ApplicationPicker
            value={applicationId}
            onChange={(id) => setApplicationId((current) => (current === id ? null : id))}
            label="Application (optional)"
            emptyHint="No applications yet — the email will arrive unlinked."
          />

          <div className="space-y-2">
            <Label htmlFor="simulate-subject">Subject (optional)</Label>
            <Input
              id="simulate-subject"
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
              placeholder="Leave empty for a realistic generated subject"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="simulate-body">Body (optional)</Label>
            <Textarea
              id="simulate-body"
              value={body}
              onChange={(event) => setBody(event.target.value)}
              placeholder="Leave empty for a realistic generated body"
              rows={4}
            />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" loading={saving}>
              Simulate email
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
