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
import { ApplicationPicker } from '@/features/emails/components/ApplicationPicker'
import type { UUID } from '@/types/api'

export interface LinkApplicationDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Subject of the email being linked, shown for context. */
  subject?: string
  currentApplicationId?: UUID | null
  saving?: boolean
  onConfirm: (applicationId: UUID) => Promise<void> | void
}

/** Pick the application an email belongs to when the classifier could not work it out. */
export function LinkApplicationDialog({
  open,
  onOpenChange,
  subject,
  currentApplicationId = null,
  saving = false,
  onConfirm,
}: LinkApplicationDialogProps) {
  const [selected, setSelected] = React.useState<UUID | null>(currentApplicationId)

  React.useEffect(() => {
    if (open) setSelected(currentApplicationId)
  }, [open, currentApplicationId])

  return (
    <Dialog open={open} onOpenChange={(next) => (saving ? undefined : onOpenChange(next))}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Link to an application</DialogTitle>
          <DialogDescription>
            {subject
              ? `Attach “${subject}” to the application it belongs to so its status can follow the conversation.`
              : 'Attach this message to the application it belongs to.'}
          </DialogDescription>
        </DialogHeader>

        <ApplicationPicker value={selected} onChange={(id) => setSelected(id)} label="Choose an application" />

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button
            disabled={!selected}
            loading={saving}
            onClick={() => {
              if (selected) void onConfirm(selected)
            }}
          >
            Link email
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
