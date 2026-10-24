import { ArrowLeft, FileArchive, FileText, Info, Linkedin, RefreshCw, ShieldCheck, TriangleAlert, Unplug } from 'lucide-react'
import * as React from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { ErrorState } from '@/components/common/ErrorState'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { toast } from '@/components/ui/toaster'
import { errorMessage, isApiError } from '@/lib/api'
import { pluralize } from '@/lib/utils'

import {
  useAddLinkedInExport,
  useConnectLinkedIn,
  useCreateResumeFromLinkedIn,
  useDisconnectLinkedIn,
  useLinkedIn,
  useLinkedInDiff,
  useSyncLinkedIn,
  useUpdateLinkedIn,
} from '../api'
import { WHAT_LINKEDIN_SHARES, linkedinErrorMessage } from '../copy'
import type { LinkedInStatus, LinkedInSyncResult } from '../types'
import { LinkedInCardSkeleton, LinkedInIdentity, LinkedInMark, LinkedInSourceBadge, SWITCH_DARK_FIX } from './LinkedInParts'
import { LinkedInReviewDialog } from './LinkedInReviewDialog'

/** Opens LinkedIn's consent screen in this tab (the callback brings the user back here). */
export function useStartLinkedInConnect() {
  const connect = useConnectLinkedIn()
  const start = async () => {
    try {
      const { authorization_url } = await connect.mutateAsync()
      window.location.assign(authorization_url)
    } catch (error) {
      toast.error('Could not start the LinkedIn connection', { description: errorMessage(error) })
    }
  }
  return { start, isPending: connect.isPending }
}

function WhatLinkedInShares() {
  return (
    <ul className="grid gap-3 sm:grid-cols-3">
      {WHAT_LINKEDIN_SHARES.map((item) => (
        <li key={item.title} className="rounded-lg border border-border bg-surface-2 p-3">
          <p className="text-sm font-semibold">{item.title}</p>
          <p className="mt-1 text-xs text-muted-foreground">{item.body}</p>
        </li>
      ))}
    </ul>
  )
}

function ExportDropzone({ onDone }: { onDone: (result: LinkedInSyncResult) => void }) {
  const addExport = useAddLinkedInExport()
  const [files, setFiles] = React.useState<File[]>([])
  const submit = async () => {
    try {
      onDone(await addExport.mutateAsync(files))
    } catch (error) {
      toast.error('Could not read that export', { description: errorMessage(error) })
    }
  }
  return (
    <div className="space-y-3 rounded-lg border border-dashed border-input/60 bg-surface-2 p-4">
      <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
        <li>On LinkedIn open <strong>Settings &amp; Privacy → Data privacy → Get a copy of your data</strong>.</li>
        <li>Request the archive (or Profile, Positions, Education, Skills) and download the ZIP LinkedIn emails you.</li>
        <li>Upload it here. It is read in memory; only the details you see in the review are kept on your connection.</li>
      </ol>
      <div className="space-y-1">
        <Label htmlFor="linkedin-export">LinkedIn export (.zip or .csv files)</Label>
        <Input
          id="linkedin-export"
          type="file"
          multiple
          accept=".zip,.csv,application/zip,text/csv"
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
        />
      </div>
      <Button type="button" variant="soft" disabled={!files.length} loading={addExport.isPending} onClick={() => void submit()}>
        <FileArchive aria-hidden /> Read export and review
      </Button>
    </div>
  )
}

function NotConnected({ status, error, onRetry, starting }: { status: LinkedInStatus; error: string | null; onRetry: () => void; starting: boolean }) {
  const reconnect = status.status === 'expired' || status.status === 'revoked'
  return (
    <div className="space-y-4">
      {error ? (
        <Alert variant="destructive">
          <TriangleAlert aria-hidden />
          <AlertTitle>LinkedIn was not connected</AlertTitle>
          <AlertDescription className="space-y-2">
            <p>{linkedinErrorMessage(error)}</p>
            {status.configured ? (
              <Button type="button" size="sm" variant="outline" onClick={onRetry} loading={starting}>
                <RefreshCw aria-hidden /> Try again
              </Button>
            ) : null}
          </AlertDescription>
        </Alert>
      ) : null}
      {reconnect ? (
        <Alert variant="warning">
          <TriangleAlert aria-hidden />
          <AlertTitle>{status.status === 'expired' ? 'Your LinkedIn sign-in expired' : 'LinkedIn access was removed'}</AlertTitle>
          <AlertDescription>
            {status.last_error ?? 'Reconnect to keep your details in sync.'} LinkedIn sign-ins last 60 days; reconnecting takes a few seconds.
          </AlertDescription>
        </Alert>
      ) : null}
      <WhatLinkedInShares />
      {status.configured ? (
        <div className="flex flex-wrap items-center gap-3">
          <Button type="button" size="lg" onClick={onRetry} loading={starting}>
            <Linkedin aria-hidden /> {reconnect ? 'Reconnect LinkedIn' : 'Connect LinkedIn'}
          </Button>
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <ShieldCheck className="size-3.5 text-success" aria-hidden /> Official LinkedIn sign-in. You can disconnect any time.
          </span>
        </div>
      ) : (
        <Alert variant="warning">
          <AlertTitle>LinkedIn is not configured on this server</AlertTitle>
          <AlertDescription>
            The owner needs to register a LinkedIn app and set <code>LINKEDIN_CLIENT_ID</code> / <code>LINKEDIN_CLIENT_SECRET</code>{' '}
            (see <code>docs/INTEGRATIONS.md</code>). Until then,{' '}
            <Link className="underline" to="/resume/new?mode=linkedin">
              import your LinkedIn export
            </Link>{' '}
            instead.
          </AlertDescription>
        </Alert>
      )}
    </div>
  )
}

/**
 * "Connect LinkedIn" in Create Resume: connect through LinkedIn's official sign-in, review what
 * it shares before anything reaches the profile, create a resume from it, keep it in sync.
 */
export function LinkedInConnectPanel({ onBack }: { onBack?: () => void }) {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const status = useLinkedIn()
  const { start, isPending: starting } = useStartLinkedInConnect()
  const sync = useSyncLinkedIn()
  const update = useUpdateLinkedIn()
  const disconnect = useDisconnectLinkedIn()
  const createResume = useCreateResumeFromLinkedIn()

  const [error, setError] = React.useState<string | null>(params.get('error'))
  const [reviewOpen, setReviewOpen] = React.useState(false)
  const [result, setResult] = React.useState<LinkedInSyncResult | null>(null)
  const [showExport, setShowExport] = React.useState(false)
  const [confirmOpen, setConfirmOpen] = React.useState(false)
  const [wantStoredDiff, setWantStoredDiff] = React.useState(false)
  const storedDiff = useLinkedInDiff(wantStoredDiff)
  const handled = React.useRef(false)

  const clearParams = React.useCallback(
    (...keys: string[]) =>
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          for (const key of keys) next.delete(key)
          return next
        },
        { replace: true },
      ),
    [setParams],
  )

  const runSync = React.useCallback(
    async (openReview: boolean) => {
      if (openReview) {
        setResult(null)
        setReviewOpen(true)
      }
      try {
        const synced = await sync.mutateAsync()
        setResult(synced)
        if (!openReview) {
          toast.success('LinkedIn synced', {
            description: synced.diff.changes
              ? `${synced.diff.changes} ${synced.diff.changes === 1 ? 'change' : 'changes'} to review.`
              : 'Your profile already matches LinkedIn.',
          })
          if (synced.diff.changes) setReviewOpen(true)
        }
      } catch (err) {
        setReviewOpen(false)
        if (isApiError(err) && err.code === 'reconnect_required') {
          toast.warning('Reconnect LinkedIn', { description: errorMessage(err) })
        } else {
          toast.error('LinkedIn sync failed', { description: errorMessage(err) })
        }
      }
    },
    [sync],
  )

  // Back from LinkedIn (?connected=1): sync once and open the review. From a notification (?review=1): open the stored diff.
  React.useEffect(() => {
    if (handled.current) return
    if (params.get('connected') === '1') {
      handled.current = true
      clearParams('connected', 'error')
      toast.success('LinkedIn connected', { description: 'Reading what LinkedIn shared…' })
      void runSync(true)
    } else if (params.get('review') === '1') {
      handled.current = true
      clearParams('review')
      setWantStoredDiff(true)
    } else if (params.get('error')) {
      handled.current = true
      clearParams('error')
    }
  }, [params, clearParams, runSync])

  React.useEffect(() => {
    if (wantStoredDiff && storedDiff.data) {
      setResult(storedDiff.data)
      setReviewOpen(true)
      setWantStoredDiff(false)
    }
  }, [wantStoredDiff, storedDiff.data])

  const retry = () => {
    setError(null)
    void start()
  }

  const handleCreate = async () => {
    try {
      const resume = await createResume.mutateAsync({})
      toast.success('Resume created from LinkedIn', { description: 'Review every section, then save a version or export it.' })
      navigate(`/resume/my/${resume.id}/edit`)
    } catch (err) {
      toast.error('Could not create the resume', { description: errorMessage(err) })
    }
  }

  const data = status.data
  const reviewing = sync.isPending || reviewOpen

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex-row items-start gap-3 space-y-0">
          <LinkedInMark />
          <div className="min-w-0">
            <CardTitle className="text-base">Connect LinkedIn</CardTitle>
            <CardDescription>Fill your profile from LinkedIn, review every change, and keep it in sync.</CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          {status.isLoading ? (
            <LinkedInCardSkeleton />
          ) : status.error || !data ? (
            <ErrorState error={status.error} title="Could not load your LinkedIn connection" onRetry={() => void status.refetch()} size="sm" />
          ) : data.status !== 'connected' ? (
            <NotConnected status={data} error={error} onRetry={retry} starting={starting} />
          ) : (
            <>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <LinkedInIdentity status={data} />
                <LinkedInSourceBadge status={data} />
              </div>

              {data.history_source === null ? (
                <Alert variant="info">
                  <Info aria-hidden />
                  <AlertTitle>Only your basics were filled</AlertTitle>
                  <AlertDescription className="space-y-2">
                    <p>
                      LinkedIn’s standard sign-in shares your name, email and photo — not positions, education or skills.
                      {data.dma_error && data.dma_enabled
                        ? ' This server asked for your full profile too, but LinkedIn did not grant it (that API is limited to EU/EEA members).'
                        : ''}{' '}
                      Add your LinkedIn export for the full history.
                    </p>
                    {!showExport ? (
                      <Button type="button" size="sm" variant="outline" onClick={() => setShowExport(true)}>
                        <FileArchive aria-hidden /> Add export for full history
                      </Button>
                    ) : null}
                  </AlertDescription>
                </Alert>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Full history available: {data.history_counts.positions} {pluralize(data.history_counts.positions, 'position')} ·{' '}
                  {data.history_counts.education} education · {data.history_counts.skills} {pluralize(data.history_counts.skills, 'skill')} ·{' '}
                  {data.history_counts.certifications} {pluralize(data.history_counts.certifications, 'certification')}.
                </p>
              )}

              {data.export_stale ? (
                <Alert variant="warning">
                  <TriangleAlert aria-hidden />
                  <AlertDescription>
                    Your LinkedIn export is older than {data.export_stale_days} days. Download a fresh copy and add it to pick up recent changes.
                  </AlertDescription>
                </Alert>
              ) : null}

              {data.pending_changes > 0 && !reviewOpen ? (
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm">
                  <span>
                    <strong>{data.pending_changes}</strong> {data.pending_changes === 1 ? 'change' : 'changes'} from LinkedIn not in your profile yet.
                  </span>
                  <Button type="button" size="sm" variant="soft" onClick={() => setWantStoredDiff(true)} loading={storedDiff.isFetching}>
                    Review changes
                  </Button>
                </div>
              ) : null}

              <div className="flex flex-wrap gap-2">
                <Button type="button" onClick={() => void handleCreate()} loading={createResume.isPending} disabled={reviewing}>
                  <FileText aria-hidden /> Create resume from LinkedIn
                </Button>
                <Button type="button" variant="outline" onClick={() => void runSync(false)} loading={sync.isPending}>
                  <RefreshCw aria-hidden /> Sync now
                </Button>
                <Button type="button" variant="outline" onClick={() => setShowExport((v) => !v)} aria-expanded={showExport}>
                  <FileArchive aria-hidden />{' '}
                  {data.history_source === 'export' ? 'Add a newer export' : data.history_source === 'dma' ? 'Add an export' : 'Add export for full history'}
                </Button>
              </div>

              {showExport ? (
                <ExportDropzone
                  onDone={(added) => {
                    setShowExport(false)
                    setResult(added)
                    setReviewOpen(true)
                  }}
                />
              ) : null}

              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
                <label className="flex items-center gap-2 text-sm">
                  <Switch
                    // switch.tsx loses its dark checked fill (tailwind-merge drops bg-primary next to bg-gradient-brand)
                    className={SWITCH_DARK_FIX}
                    checked={data.auto_sync}
                    disabled={update.isPending}
                    onCheckedChange={(next) =>
                      update.mutate(
                        { auto_sync: next },
                        { onError: (err) => toast.error('Could not change auto-sync', { description: errorMessage(err) }) },
                      )
                    }
                  />
                  <span>
                    Check LinkedIn every {data.auto_sync_hours} h and notify me about changes
                    <span className="block text-xs text-muted-foreground">Never changes your profile on its own.</span>
                  </span>
                </label>
                <Button type="button" variant="ghost" size="sm" onClick={() => setConfirmOpen(true)}>
                  <Unplug aria-hidden /> Disconnect
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {onBack ? (
        <Button type="button" variant="ghost" onClick={onBack}>
          <ArrowLeft aria-hidden /> Choose another start
        </Button>
      ) : null}

      <LinkedInReviewDialog
        open={reviewOpen}
        onOpenChange={setReviewOpen}
        result={result}
        loading={sync.isPending && !result}
        onApplied={() => setResult(null)}
      />
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Disconnect LinkedIn?"
        description="JobPilot revokes its access at LinkedIn and deletes the stored LinkedIn details. Your profile and resumes stay as they are."
        confirmLabel="Disconnect"
        variant="destructive"
        loading={disconnect.isPending}
        onConfirm={async () => {
          try {
            await disconnect.mutateAsync()
            toast.success('LinkedIn disconnected', { description: 'Access revoked and stored LinkedIn data deleted.' })
          } catch (err) {
            toast.error('Could not disconnect LinkedIn', { description: errorMessage(err) })
          }
        }}
      />
    </div>
  )
}
