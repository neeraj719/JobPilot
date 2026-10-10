import { CheckCircle2, ExternalLink, SearchX } from 'lucide-react'
import * as React from 'react'

import { Badge } from '@/components/ui/badge'
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
import { useCreateCompany, useSetCompanyBoard } from '@/features/companies/api'
import { BOARD_URL_EXAMPLES } from '@/features/companies/components/CompanyBoardDialog'
import {
  BOARD_ATS_TYPES,
  type BoardAtsType,
  type BoardDetection,
  type CompanyDetectResult,
  type DetectionMethod,
  type JobSourceType,
} from '@/types/api'

const DETECT = '__detect__'

/** How each detection method is described to the user. */
export const DETECTION_METHOD_LABELS: Record<DetectionMethod, string> = {
  KNOWN: 'Known company',
  GUESS: 'Matched by name',
  SCAN: 'Found on the careers page',
  NONE: 'Not found',
}

function vendorLabel(atsType: string | null | undefined): string {
  if (!atsType) return 'Unknown'
  return SOURCE_LABELS[atsType as JobSourceType] ?? atsType
}

/** The outcome of a board detection: vendor badge, open jobs and method, or why nothing was found. */
export function DetectionSummary({ detection }: { detection: BoardDetection }) {
  const [showTried, setShowTried] = React.useState(false)
  const found = detection.method !== 'NONE' && detection.supported
  return (
    <div className="space-y-2" role="status">
      {found ? (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm">
          <CheckCircle2 className="size-4 text-success" aria-hidden />
          <Badge variant="secondary">{vendorLabel(detection.ats_type)}</Badge>
          <span className="font-medium">{detection.token}</span>
          {detection.board_company ? (
            <span className="text-muted-foreground">({detection.board_company})</span>
          ) : null}
          <span className="text-muted-foreground">
            {detection.open_jobs !== null
              ? `${formatNumber(detection.open_jobs)} open ${detection.open_jobs === 1 ? 'job' : 'jobs'}`
              : 'open jobs not counted'}
          </span>
          <Badge variant="outline">{DETECTION_METHOD_LABELS[detection.method]}</Badge>
          {detection.board_url ? (
            <a
              href={detection.board_url}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              Board <ExternalLink className="size-3" aria-hidden />
            </a>
          ) : null}
        </div>
      ) : detection.ats_type === 'WORKDAY' ? (
        <p className="rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-sm">
          This company hires through <strong>Workday</strong>, which JobPilot cannot read yet. If it also has a
          Greenhouse, Lever, Ashby or SmartRecruiters board, add it below.
        </p>
      ) : (
        <p className="flex items-center gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
          <SearchX className="size-4 text-muted-foreground" aria-hidden />
          No public job board was found automatically. Paste its board URL below if you know it.
        </p>
      )}
      {detection.tried.length > 0 ? (
        <div className="text-xs text-muted-foreground">
          <button type="button" className="underline-offset-2 hover:underline" onClick={() => setShowTried((v) => !v)}>
            {showTried ? 'Hide' : 'Show'} what was checked ({detection.tried.length})
          </button>
          {showTried ? (
            <ul className="mt-1 max-h-40 list-disc space-y-0.5 overflow-y-auto pl-4">
              {detection.tried.map((line, index) => (
                <li key={index} className="break-all">
                  {line}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

export interface AddCompanyDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * `POST /companies` — add an employer by name and (optionally) website. The server looks
 * the company's career board up (known list, name guess, careers page scan) and shows what
 * it found; when nothing was found the manual board URL field appears, which verifies and
 * saves through `PUT /companies/{id}/board`.
 */
export function AddCompanyDialog({ open, onOpenChange }: AddCompanyDialogProps) {
  const create = useCreateCompany()
  const setBoard = useSetCompanyBoard()
  const [name, setName] = React.useState('')
  const [website, setWebsite] = React.useState('')
  const [result, setResult] = React.useState<CompanyDetectResult | null>(null)
  const [boardUrl, setBoardUrl] = React.useState('')
  const [atsType, setAtsType] = React.useState<BoardAtsType | typeof DETECT>(DETECT)
  const [savedCount, setSavedCount] = React.useState<number | null>(null)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (!open) return
    setName('')
    setWebsite('')
    setResult(null)
    setBoardUrl('')
    setAtsType(DETECT)
    setSavedCount(null)
    setError(null)
  }, [open])

  const busy = create.isPending || setBoard.isPending
  const hasBoard = !!result?.ats_board_token
  const needsManualBoard = result !== null && !hasBoard && savedCount === null

  async function handleAdd(event: React.FormEvent) {
    event.preventDefault()
    if (!name.trim()) return
    setError(null)
    try {
      const company = await create.mutateAsync({ name: name.trim(), website: website.trim() || null, auto_detect: true })
      setResult(company)
      if (company.ats_board_token) {
        toast.success(`${company.name} added — its ${vendorLabel(company.ats_type)} board will be searched`)
      }
    } catch (err) {
      setError(errorMessage(err, 'Could not add this company.'))
    }
  }

  async function handleManualBoard(event: React.FormEvent) {
    event.preventDefault()
    if (!result || !boardUrl.trim()) return
    setError(null)
    const vendor = atsType === DETECT ? inferVendor(boardUrl) : atsType
    if (!vendor) {
      setError('Choose the ATS (Greenhouse, Lever, Ashby or SmartRecruiters) for this board.')
      return
    }
    try {
      const saved = await setBoard.mutateAsync({ companyId: result.id, ats_type: vendor, board_url: boardUrl.trim() })
      setSavedCount(saved.board_job_count)
      toast.success(`${result.name}: ${formatNumber(saved.board_job_count)} open jobs on ${SOURCE_LABELS[vendor]}`)
    } catch (err) {
      setError(errorMessage(err, 'Could not verify this board.'))
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (busy ? undefined : onOpenChange(next))}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Add company</DialogTitle>
          <DialogDescription>
            Type the company&apos;s name (and its website if you know it). JobPilot looks up its public career board
            and starts reading its real openings on the next discovery run.
          </DialogDescription>
        </DialogHeader>

        {result === null ? (
          <form onSubmit={handleAdd} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="new-company-name">Company name</Label>
              <Input
                id="new-company-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Acme Robotics"
                maxLength={255}
                required
                disabled={busy}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-company-website">Website (optional)</Label>
              <Input
                id="new-company-website"
                value={website}
                onChange={(event) => setWebsite(event.target.value)}
                placeholder="acme.com"
                maxLength={500}
                disabled={busy}
              />
              <p className="text-xs text-muted-foreground">
                Helps find the board: JobPilot reads the public careers page (respecting robots.txt).
              </p>
            </div>
            {error ? <ErrorNote message={error} /> : null}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
                Cancel
              </Button>
              <Button type="submit" loading={create.isPending} disabled={!name.trim()}>
                {create.isPending ? 'Looking for the board…' : 'Add & find board'}
              </Button>
            </DialogFooter>
          </form>
        ) : (
          <form onSubmit={handleManualBoard} className="space-y-4">
            <p className="text-sm">
              <span className="font-medium">{result.name}</span> is in your directory.
            </p>
            {result.detection ? (
              <DetectionSummary detection={result.detection} />
            ) : hasBoard ? (
              <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                Already reading its board:
                <Badge variant="secondary">
                  {vendorLabel(result.ats_type)} · {result.ats_board_token}
                </Badge>
              </p>
            ) : null}

            {needsManualBoard ? (
              <div className="grid gap-4 sm:grid-cols-[11rem_1fr]">
                <div className="space-y-2">
                  <Label htmlFor="new-company-ats">Career board</Label>
                  <Select
                    value={atsType}
                    onValueChange={(value) => setAtsType(value as BoardAtsType | typeof DETECT)}
                    disabled={busy}
                  >
                    <SelectTrigger id="new-company-ats">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={DETECT}>Detect from URL</SelectItem>
                      {BOARD_ATS_TYPES.map((value) => (
                        <SelectItem key={value} value={value}>
                          {SOURCE_LABELS[value]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="new-company-board">Board URL</Label>
                  <Input
                    id="new-company-board"
                    value={boardUrl}
                    onChange={(event) => setBoardUrl(event.target.value)}
                    placeholder={atsType === DETECT ? BOARD_URL_EXAMPLES.GREENHOUSE : BOARD_URL_EXAMPLES[atsType]}
                    maxLength={500}
                    autoComplete="off"
                    disabled={busy}
                  />
                </div>
              </div>
            ) : null}

            {savedCount !== null ? (
              <p className="flex items-center gap-2 rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm" role="status">
                <CheckCircle2 className="size-4 text-success" aria-hidden />
                Verified — {formatNumber(savedCount)} open {savedCount === 1 ? 'job' : 'jobs'} on this board. Saved.
              </p>
            ) : null}
            {error ? <ErrorNote message={error} /> : null}

            <DialogFooter>
              <Button type="button" variant={needsManualBoard ? 'outline' : 'default'} onClick={() => onOpenChange(false)} disabled={busy}>
                {needsManualBoard ? 'Skip for now' : 'Done'}
              </Button>
              {needsManualBoard ? (
                <Button type="submit" loading={setBoard.isPending} disabled={!boardUrl.trim()}>
                  Verify &amp; save
                </Button>
              ) : null}
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}

function ErrorNote({ message }: { message: string }) {
  return (
    <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
      {message}
    </p>
  )
}

/** The vendor a pasted board URL points at (mirrors the server's `infer_ats_type`). */
function inferVendor(value: string): BoardAtsType | null {
  const text = value.trim().toLowerCase()
  if (text.includes('greenhouse.io')) return 'GREENHOUSE'
  if (text.includes('lever.co')) return 'LEVER'
  if (text.includes('ashbyhq.com')) return 'ASHBY'
  if (text.includes('smartrecruiters.com')) return 'SMARTRECRUITERS'
  return null
}
