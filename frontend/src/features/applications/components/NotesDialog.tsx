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
import { Textarea } from '@/components/ui/textarea'
import type { ApplicationPatch } from '@/types/api'

export interface NotesDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  notes: string | null
  nextAction: string | null
  nextActionDue: string | null
  loading?: boolean
  onSave: (patch: ApplicationPatch) => Promise<void> | void
}

/** `2026-09-19T10:00:00` -> `2026-09-19`, for an `<input type="date">`. */
function toDateInput(value: string | null): string {
  if (!value) return ''
  return value.slice(0, 10)
}

/** Private notes plus the next action and when it is due. */
export function NotesDialog({
  open,
  onOpenChange,
  notes,
  nextAction,
  nextActionDue,
  loading = false,
  onSave,
}: NotesDialogProps) {
  const [noteDraft, setNoteDraft] = React.useState(notes ?? '')
  const [actionDraft, setActionDraft] = React.useState(nextAction ?? '')
  const [dueDraft, setDueDraft] = React.useState(toDateInput(nextActionDue))
  const [pending, setPending] = React.useState(false)
  const busy = pending || loading
  const id = React.useId()

  React.useEffect(() => {
    if (!open) return
    setNoteDraft(notes ?? '')
    setActionDraft(nextAction ?? '')
    setDueDraft(toDateInput(nextActionDue))
  }, [open, notes, nextAction, nextActionDue])

  async function handleSave() {
    setPending(true)
    try {
      await onSave({
        notes: noteDraft.trim() || null,
        next_action: actionDraft.trim() || null,
        next_action_due: dueDraft ? new Date(`${dueDraft}T09:00:00`).toISOString() : null,
      })
      onOpenChange(false)
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={busy ? undefined : onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Notes &amp; next action</DialogTitle>
          <DialogDescription>Private to you — nothing here is sent to the company.</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor={`${id}-notes`}>Notes</Label>
            <Textarea
              id={`${id}-notes`}
              rows={4}
              value={noteDraft}
              placeholder="Anything you want to remember about this application"
              onChange={(event) => setNoteDraft(event.target.value)}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_auto]">
            <div className="space-y-2">
              <Label htmlFor={`${id}-action`}>Next action</Label>
              <Input
                id={`${id}-action`}
                value={actionDraft}
                placeholder="e.g. follow up with the recruiter"
                onChange={(event) => setActionDraft(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor={`${id}-due`}>Due</Label>
              <Input
                id={`${id}-due`}
                type="date"
                value={dueDraft}
                onChange={(event) => setDueDraft(event.target.value)}
              />
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={handleSave} loading={busy}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
