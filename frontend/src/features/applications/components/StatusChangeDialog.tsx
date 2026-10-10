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
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { APPLICATION_STATUS_LABELS } from '@/lib/utils'
import { APPLICATION_STATUSES, type ApplicationStatus } from '@/types/api'

export interface StatusChangeDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Status the user picked (or the current one when opened from a menu). */
  status: ApplicationStatus | null
  /** Shown above the picker, e.g. "Frontend Engineer at Netflix". */
  subject?: string
  /** When true the dialog lets the user pick the status too. */
  allowPickStatus?: boolean
  loading?: boolean
  onConfirm: (status: ApplicationStatus, note?: string) => void | Promise<void>
}

/** Manual status change with an optional note that lands on the timeline. */
export function StatusChangeDialog({
  open,
  onOpenChange,
  status,
  subject,
  allowPickStatus = false,
  loading = false,
  onConfirm,
}: StatusChangeDialogProps) {
  const [note, setNote] = React.useState('')
  const [picked, setPicked] = React.useState<ApplicationStatus | null>(status)
  const [pending, setPending] = React.useState(false)
  const busy = pending || loading
  const noteId = React.useId()

  React.useEffect(() => {
    if (open) {
      setNote('')
      setPicked(status)
    }
  }, [open, status])

  async function handleConfirm() {
    if (!picked) return
    setPending(true)
    try {
      await onConfirm(picked, note.trim() || undefined)
      onOpenChange(false)
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={busy ? undefined : onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Change status</DialogTitle>
          <DialogDescription>
            {subject ? `${subject} — ` : ''}
            this is recorded on the application timeline as a manual change.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {allowPickStatus ? (
            <div className="space-y-2">
              <Label htmlFor={`${noteId}-status`}>New status</Label>
              <Select value={picked ?? undefined} onValueChange={(value) => setPicked(value as ApplicationStatus)}>
                <SelectTrigger id={`${noteId}-status`}>
                  <SelectValue placeholder="Pick a status" />
                </SelectTrigger>
                <SelectContent>
                  {APPLICATION_STATUSES.map((value) => (
                    <SelectItem key={value} value={value}>
                      {APPLICATION_STATUS_LABELS[value]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : (
            <p className="text-sm">
              New status: <strong>{picked ? APPLICATION_STATUS_LABELS[picked] : '—'}</strong>
            </p>
          )}

          <div className="space-y-2">
            <Label htmlFor={noteId}>Note (optional)</Label>
            <Textarea
              id={noteId}
              rows={3}
              value={note}
              placeholder="e.g. recruiter called, moving to a technical round next week"
              onChange={(event) => setNote(event.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={handleConfirm} loading={busy} disabled={!picked}>
            Save status
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
