import { Building2, Search } from 'lucide-react'
import * as React from 'react'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage, isApiError } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useResumes } from '@/features/resume/api'
import { useCompanyLookup, useCreateTarget } from '@/features/ats/api'
import type { CompanyLookupResult, JobTargetDetail, OpenRole, SnapshotCreate } from '@/features/ats/types'

const NONE = '__none__'

function toIso(date: string): string | null {
  return date ? new Date(`${date}T09:00:00`).toISOString() : null
}

export interface TargetFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (target: JobTargetDetail) => void
}

/** "New target": company (look up its real open roles), role, URL, dates, notes and the JD. */
export function TargetFormDialog({ open, onOpenChange, onCreated }: TargetFormDialogProps) {
  const resumes = useResumes()
  const lookup = useCompanyLookup()
  const create = useCreateTarget()
  const [company, setCompany] = React.useState('')
  const [role, setRole] = React.useState('')
  const [url, setUrl] = React.useState('')
  const [deadline, setDeadline] = React.useState('')
  const [followUp, setFollowUp] = React.useState('')
  const [notes, setNotes] = React.useState('')
  const [jdText, setJdText] = React.useState('')
  const [fetchUrl, setFetchUrl] = React.useState(true)
  const [resumeId, setResumeId] = React.useState(NONE)
  const [result, setResult] = React.useState<CompanyLookupResult | null>(null)
  const [picked, setPicked] = React.useState<OpenRole | null>(null)
  const [showAll, setShowAll] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (!open) return
    setCompany('')
    setRole('')
    setUrl('')
    setDeadline('')
    setFollowUp('')
    setNotes('')
    setJdText('')
    setFetchUrl(true)
    setResult(null)
    setPicked(null)
    setShowAll(false)
    setError(null)
    setResumeId(NONE)
  }, [open])

  const runLookup = async () => {
    setError(null)
    setPicked(null)
    try {
      setResult(await lookup.mutateAsync({ name: company.trim(), role: role.trim() || undefined }))
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const pick = (openRole: OpenRole) => {
    setPicked(openRole)
    setRole(openRole.title)
    if (openRole.url) setUrl(openRole.url)
  }

  const submit = async () => {
    setError(null)
    let jd: SnapshotCreate | undefined
    if (picked) jd = { source: 'BOARD', board: { vendor: picked.vendor, token: picked.token, external_id: picked.external_id } }
    else if (jdText.trim().length >= 120) jd = { source: 'PASTED', text: jdText }
    else if (url.trim() && fetchUrl) jd = { source: 'URL', url: url.trim() }
    try {
      const target = await create.mutateAsync({
        company_name: result?.company?.name && picked ? result.company.name : company.trim(),
        role_title: role.trim(),
        job_url: url.trim() || null,
        deadline: toIso(deadline),
        follow_up_at: toIso(followUp),
        notes: notes.trim() || null,
        source_resume_id: resumeId === NONE ? null : resumeId,
        jd,
      })
      onOpenChange(false)
      onCreated(target)
    } catch (err) {
      if (isApiError(err) && err.code === 'jd_unreadable') {
        setFetchUrl(false)
        setError(`${errorMessage(err)} The target can still be saved without it.`)
        return
      }
      setError(errorMessage(err))
    }
  }

  const roles = result ? (showAll || !result.matching_roles.length ? result.open_roles : result.matching_roles) : []
  const canSave = company.trim().length > 0 && role.trim().length > 0 && !create.isPending

  return (
    <Dialog open={open} onOpenChange={(next) => (create.isPending ? undefined : onOpenChange(next))}>
      <DialogContent className="flex max-h-[92vh] max-w-2xl flex-col gap-0 p-0">
        <DialogHeader className="border-b border-border p-6 pb-4 pr-12">
          <DialogTitle>New job target</DialogTitle>
          <DialogDescription>
            Save one opportunity. JobPilot can look up the company's real open roles on its public job board; it never
            guesses which one you mean.
          </DialogDescription>
        </DialogHeader>
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-6">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="target-company">Company</Label>
              <Input id="target-company" value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Stripe" autoFocus />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="target-role">Role</Label>
              <Input id="target-role" value={role} onChange={(e) => setRole(e.target.value)} placeholder="Backend Engineer" />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => void runLookup()} disabled={!company.trim() || lookup.isPending} loading={lookup.isPending}>
              <Search aria-hidden />
              Look up open roles
            </Button>
            <span className="text-xs text-muted-foreground">Reads Greenhouse, Lever, Ashby or SmartRecruiters boards.</span>
          </div>

          {result ? (
            <div className="space-y-2 rounded-lg border border-border p-3">
              <p className="flex items-center gap-2 text-sm">
                <Building2 className="size-4 text-muted-foreground" aria-hidden />
                {result.message}
              </p>
              {roles.length ? (
                <ul className="max-h-64 space-y-1 overflow-y-auto" role="radiogroup" aria-label="Open roles">
                  {roles.map((openRole) => (
                    <li key={openRole.external_id}>
                      <button
                        type="button"
                        role="radio"
                        aria-checked={picked?.external_id === openRole.external_id}
                        onClick={() => pick(openRole)}
                        className={cn(
                          'flex w-full items-center justify-between gap-2 rounded-md border border-transparent px-2.5 py-1.5 text-left text-sm hover:bg-accent',
                          picked?.external_id === openRole.external_id && 'border-primary/50 bg-primary/5',
                        )}
                      >
                        <span className="min-w-0 truncate">{openRole.title}</span>
                        <span className="shrink-0 text-xs text-muted-foreground">{openRole.location ?? ''}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
              {result.matching_roles.length && result.open_roles.length > result.matching_roles.length ? (
                <Button variant="link" size="sm" className="h-auto p-0" onClick={() => setShowAll((value) => !value)}>
                  {showAll ? `Show the ${result.matching_roles.length} matching roles` : `Show all ${result.total_open} open roles`}
                </Button>
              ) : null}
            </div>
          ) : null}

          <div className="space-y-1.5">
            <Label htmlFor="target-url">Job posting URL</Label>
            <Input id="target-url" type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" />
            {url.trim() && !picked && jdText.trim().length < 120 ? (
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <Checkbox checked={fetchUrl} onCheckedChange={(value) => setFetchUrl(value === true)} />
                Read the job description from this URL now
              </label>
            ) : null}
          </div>
          {!picked ? (
            <div className="space-y-1.5">
              <Label htmlFor="target-jd">Job description (optional)</Label>
              <Textarea id="target-jd" rows={5} value={jdText} onChange={(e) => setJdText(e.target.value)} placeholder="Paste the posting if there is no readable URL." />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">The job description of “{picked.title}” will be read from the company's board.</p>
          )}
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="target-deadline">Deadline</Label>
              <Input id="target-deadline" type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="target-follow">Follow up on</Label>
              <Input id="target-follow" type="date" value={followUp} onChange={(e) => setFollowUp(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Resume to tailor</Label>
              <Select value={resumeId} onValueChange={setResumeId}>
                <SelectTrigger aria-label="Resume to tailor">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>Choose later</SelectItem>
                  {(resumes.data ?? []).filter((r) => !r.archived_at).map((r) => (
                    <SelectItem key={r.id} value={r.id}>
                      {r.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="target-notes">Notes</Label>
            <Textarea id="target-notes" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Referral, recruiter name, anything to remember" />
          </div>
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
        </div>
        <DialogFooter className="border-t border-border p-4">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={create.isPending}>
            Cancel
          </Button>
          <Button onClick={() => void submit()} disabled={!canSave} loading={create.isPending}>
            Save target
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
