import * as React from 'react'

import { ErrorState } from '@/components/common/ErrorState'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useResumeVersions } from '@/features/resume/api'

import { useVersionDiff } from '../api'
import { DiffView } from './DiffView'
import { DiffViewSkeleton } from './ResumeStudioSkeletons'

export interface CompareDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  resumeId: string
  resumeName: string
  /** The newer side. */
  version: number
  /** Versions that exist (newest first), for the "compare with" picker. */
  versions?: number[]
  /** Default base version (default: the previous one). */
  against?: number | null
}

/** Side-by-side field diff of two versions of one resume. */
export function CompareDialog({ open, onOpenChange, resumeId, resumeName, version, versions, against }: CompareDialogProps) {
  const [base, setBase] = React.useState<number | null>(against ?? (version > 1 ? version - 1 : null))
  React.useEffect(() => {
    if (open) setBase(against ?? (version > 1 ? version - 1 : null))
  }, [open, version, against])
  const diff = useVersionDiff(open ? resumeId : null, version, base)
  const listed = useResumeVersions(open && !versions ? resumeId : null)
  const options = (versions ?? (listed.data ?? []).map((v) => v.version_number)).filter((v) => v !== version)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-4xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {resumeName}: compare v{version}
          </DialogTitle>
          <DialogDescription>Removed text is struck through on the left, added text is highlighted on the right.</DialogDescription>
        </DialogHeader>
        {options.length ? (
          <div className="flex items-center gap-2">
            <Label htmlFor="compare-base" className="text-sm">
              Compare with
            </Label>
            <Select value={base ? String(base) : ''} onValueChange={(v) => setBase(Number(v))}>
              <SelectTrigger id="compare-base" className="h-8 w-40">
                <SelectValue placeholder="Choose a version" />
              </SelectTrigger>
              <SelectContent>
                {options.map((v) => (
                  <SelectItem key={v} value={String(v)}>
                    Version {v}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ) : null}
        {diff.isLoading ? (
          <DiffViewSkeleton />
        ) : diff.error ? (
          <ErrorState error={diff.error} size="sm" onRetry={() => void diff.refetch()} />
        ) : diff.data ? (
          <DiffView diff={diff.data} />
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
