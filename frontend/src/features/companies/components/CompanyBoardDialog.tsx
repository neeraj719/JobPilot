import { CheckCircle2, ExternalLink, Trash2 } from 'lucide-react'
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
import { toast } from '@/components/ui/toaster'
import { errorMessage } from '@/lib/api'
import { SOURCE_LABELS, formatNumber } from '@/lib/utils'
import { useClearCompanyBoard, useSetCompanyBoard } from '@/features/companies/api'
import { BOARD_ATS_TYPES, type BoardAtsType, type CompanyRead } from '@/types/api'

/** Example board URL per vendor, shown as the input placeholder. */
export const BOARD_URL_EXAMPLES: Record<BoardAtsType, string> = {
  GREENHOUSE: 'https://boards.greenhouse.io/stripe',
  LEVER: 'https://jobs.lever.co/spotify',
  ASHBY: 'https://jobs.ashbyhq.com/ramp',
  SMARTRECRUITERS: 'https://jobs.smartrecruiters.com/BoschGroup',
}

function isBoardAtsType(value: string | null | undefined): value is BoardAtsType {
  return !!value && (BOARD_ATS_TYPES as readonly string[]).includes(value)
}

export interface CompanyBoardDialogProps {
  company: CompanyRead | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * Configure where JobPilot reads a company's real postings from. "Verify & save" calls
 * `PUT /companies/{id}/board`, which fetches the board once and only stores it when it
 * exists and has open jobs — the count it found is shown here.
 */
export function CompanyBoardDialog({ company, open, onOpenChange }: CompanyBoardDialogProps) {
  const setBoard = useSetCompanyBoard()
  const clearBoard = useClearCompanyBoard()
  const [atsType, setAtsType] = React.useState<BoardAtsType>('GREENHOUSE')
  const [boardUrl, setBoardUrl] = React.useState('')
  const [verifiedCount, setVerifiedCount] = React.useState<number | null>(null)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (!open || !company) return
    setAtsType(isBoardAtsType(company.ats_type) ? company.ats_type : 'GREENHOUSE')
    setBoardUrl(company.ats_board_url ?? company.ats_board_token ?? '')
    setVerifiedCount(null)
    setError(null)
  }, [open, company])

  const busy = setBoard.isPending || clearBoard.isPending

  async function handleVerify(event: React.FormEvent) {
    event.preventDefault()
    if (!company || !boardUrl.trim()) return
    setError(null)
    setVerifiedCount(null)
    try {
      const result = await setBoard.mutateAsync({ companyId: company.id, ats_type: atsType, board_url: boardUrl.trim() })
      setVerifiedCount(result.board_job_count)
      toast.success(`${company.name}: ${formatNumber(result.board_job_count)} open jobs on ${SOURCE_LABELS[atsType]}`)
    } catch (err) {
      setError(errorMessage(err, 'Could not verify this board.'))
    }
  }

  async function handleRemove() {
    if (!company) return
    try {
      await clearBoard.mutateAsync(company.id)
      toast.success(`${company.name} will no longer be searched on its career board`)
      onOpenChange(false)
    } catch (err) {
      toast.error('Could not remove the board', { description: errorMessage(err) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (busy ? undefined : onOpenChange(next))}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Career board{company ? ` — ${company.name}` : ''}</DialogTitle>
          <DialogDescription>
            JobPilot reads real openings from the company&apos;s public job board (no login, no scraping). Paste the
            board URL or just its name, then verify it.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleVerify} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="board-vendor">Applicant tracking system</Label>
            <Select
              value={atsType}
              onValueChange={(value) => {
                setAtsType(value as BoardAtsType)
                setVerifiedCount(null)
                setError(null)
              }}
              disabled={busy}
            >
              <SelectTrigger id="board-vendor">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {BOARD_ATS_TYPES.map((value) => (
                  <SelectItem key={value} value={value}>
                    {SOURCE_LABELS[value]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="board-url">Board URL or token</Label>
            <Input
              id="board-url"
              value={boardUrl}
              onChange={(event) => {
                setBoardUrl(event.target.value)
                setVerifiedCount(null)
                setError(null)
              }}
              placeholder={BOARD_URL_EXAMPLES[atsType]}
              autoComplete="off"
              disabled={busy}
            />
            {company?.ats_board_url ? (
              <a
                href={company.ats_board_url}
                target="_blank"
                rel="noreferrer noopener"
                className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
              >
                Current board <ExternalLink className="size-3" aria-hidden />
              </a>
            ) : null}
          </div>

          {verifiedCount !== null ? (
            <p className="flex items-center gap-2 rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm" role="status">
              <CheckCircle2 className="size-4 text-success" aria-hidden />
              Verified — {formatNumber(verifiedCount)} open {verifiedCount === 1 ? 'job' : 'jobs'} on this board. Saved.
            </p>
          ) : null}
          {error ? (
            <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : null}

          <DialogFooter className="gap-2 sm:justify-between">
            {company?.ats_board_token ? (
              <Button type="button" variant="ghost" onClick={() => void handleRemove()} disabled={busy}>
                <Trash2 aria-hidden />
                Remove board
              </Button>
            ) : (
              <span />
            )}
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
                {verifiedCount !== null ? 'Done' : 'Cancel'}
              </Button>
              <Button type="submit" loading={setBoard.isPending} disabled={!boardUrl.trim() || clearBoard.isPending}>
                Verify &amp; save
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
