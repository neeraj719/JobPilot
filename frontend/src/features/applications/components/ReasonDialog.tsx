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
import { Textarea } from '@/components/ui/textarea'

export interface ReasonDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: React.ReactNode
  label?: string
  placeholder?: string
  confirmLabel?: string
  variant?: 'default' | 'destructive'
  loading?: boolean
  /** Receives the trimmed reason, or `undefined` when the user left it blank. */
  onConfirm: (reason?: string) => void | Promise<void>
}

/** Confirm an action while capturing an optional free-text reason (skip, withdraw, note). */
export function ReasonDialog({
  open,
  onOpenChange,
  title,
  description,
  label = 'Reason (optional)',
  placeholder = 'Why?',
  confirmLabel = 'Confirm',
  variant = 'default',
  loading = false,
  onConfirm,
}: ReasonDialogProps) {
  const [reason, setReason] = React.useState('')
  const [pending, setPending] = React.useState(false)
  const busy = pending || loading
  const fieldId = React.useId()

  React.useEffect(() => {
    if (open) setReason('')
  }, [open])

  async function handleConfirm() {
    setPending(true)
    try {
      await onConfirm(reason.trim() || undefined)
      onOpenChange(false)
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={busy ? undefined : onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor={fieldId}>{label}</Label>
          <Textarea
            id={fieldId}
            rows={3}
            value={reason}
            placeholder={placeholder}
            onChange={(event) => setReason(event.target.value)}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button variant={variant} onClick={handleConfirm} loading={busy}>
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
