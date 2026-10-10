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

export interface ConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: React.ReactNode
  confirmLabel?: string
  cancelLabel?: string
  /** `destructive` for irreversible actions (withdraw, delete, disconnect). */
  variant?: 'default' | 'destructive'
  loading?: boolean
  /** May be async — the dialog closes once it resolves. */
  onConfirm: () => void | Promise<void>
}

/**
 * Confirmation modal for destructive or irreversible actions. The caller owns the
 * open state so it can also own the mutation.
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'default',
  loading = false,
  onConfirm,
}: ConfirmDialogProps) {
  const [pending, setPending] = React.useState(false)
  const busy = pending || loading

  async function handleConfirm() {
    try {
      setPending(true)
      await onConfirm()
      onOpenChange(false)
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (busy ? undefined : onOpenChange(next))}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription asChild={typeof description !== 'string'}>{description}</DialogDescription> : null}
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button variant={variant === 'destructive' ? 'destructive' : 'default'} onClick={handleConfirm} loading={busy}>
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
