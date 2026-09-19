import { ArrowLeft, ChevronDown, ExternalLink, MoreHorizontal, Play, StickyNote, Undo2 } from 'lucide-react'
import * as React from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { ErrorState } from '@/components/common/ErrorState'
import { PageContainer } from '@/components/layout/PageContainer'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { toast } from '@/components/ui/toaster'
import {
  useApplication,
  useApplicationEvents,
  useApproveApplication,
  useGenerateAnswers,
  useGenerateCoverLetter,
  usePatchApplication,
  useResumeAutomation,
  useResumeOptions,
  useSaveCoverLetter,
  useSetApplicationStatus,
  useSkipApplication,
  useStartApplication,
  useUpdateAnswers,
  useWithdrawApplication,
} from '@/features/applications/api'
import { AnswersTab } from '@/features/applications/components/AnswersTab'
import { ApplicationHeader } from '@/features/applications/components/ApplicationHeader'
import { automationSummary, isManualStepPause } from '@/features/applications/components/AutomationBadge'
import { CoverLetterTab } from '@/features/applications/components/CoverLetterTab'
import { NotesDialog } from '@/features/applications/components/NotesDialog'
import { ReasonDialog } from '@/features/applications/components/ReasonDialog'
import { RefreshErrorBanner } from '@/features/applications/components/RefreshErrorBanner'
import { ReviewPanel } from '@/features/applications/components/ReviewPanel'
import { ScreenshotGallery, collectScreenshotNames } from '@/features/applications/components/ScreenshotGallery'
import { StatusChangeDialog } from '@/features/applications/components/StatusChangeDialog'
import { TimelineTab } from '@/features/applications/components/TimelineTab'
import { UserInputCard } from '@/features/applications/components/UserInputCard'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { errorMessage } from '@/lib/api'
import { APPLICATION_STATUS_LABELS } from '@/lib/utils'
import type { AnswerUpdate, ApplicationPatch, ApplicationStatus } from '@/types/api'

const RUNNING_POLL_MS = 3_000

function DetailSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex items-start gap-4">
        <Skeleton className="size-14 rounded-lg" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-6 w-64" />
          <Skeleton className="h-4 w-48" />
        </div>
      </div>
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-96 w-full" />
    </div>
  )
}

export default function ApplicationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [isRunning, setIsRunning] = React.useState(false)
  const applicationQuery = useApplication(id, { refetchInterval: isRunning ? RUNNING_POLL_MS : false })
  const application = applicationQuery.data
  const eventsQuery = useApplicationEvents(id)
  const resumesQuery = useResumeOptions()

  useDocumentTitle(
    application ? `${application.job_title ?? 'Application'} · ${application.company_name ?? ''}`.trim() : 'Application',
  )

  React.useEffect(() => {
    const state = application?.automation_state
    setIsRunning(state === 'RUNNING' || state === 'RETRYING')
  }, [application?.automation_state])

  const startApplication = useStartApplication()
  const approve = useApproveApplication()
  const resumeAutomation = useResumeAutomation()
  const updateAnswers = useUpdateAnswers()
  const generateAnswers = useGenerateAnswers()
  const generateCoverLetter = useGenerateCoverLetter()
  const saveCoverLetter = useSaveCoverLetter()
  const skip = useSkipApplication()
  const withdraw = useWithdrawApplication()
  const setStatus = useSetApplicationStatus()
  const patchApplication = usePatchApplication()

  const [editingReview, setEditingReview] = React.useState(false)
  const [approveOpen, setApproveOpen] = React.useState(false)
  const [skipOpen, setSkipOpen] = React.useState(false)
  const [withdrawOpen, setWithdrawOpen] = React.useState(false)
  const [statusOpen, setStatusOpen] = React.useState(false)
  const [notesOpen, setNotesOpen] = React.useState(false)

  const screenshotNames = React.useMemo(
    () => (application ? collectScreenshotNames(application) : []),
    [application],
  )

  if (!id) return <PageContainer><ErrorState title="Missing application id" /></PageContainer>
  // Narrowed once so the hoisted action handlers below see a plain `string`.
  const appId: string = id

  // Only a *first* load failure replaces the page; a failed poll keeps the last good data.
  if (applicationQuery.isError && !application) {
    return (
      <PageContainer>
        <ErrorState
          error={applicationQuery.error}
          title="Could not load this application"
          onRetry={() => void applicationQuery.refetch()}
        />
        <Button variant="outline" onClick={() => navigate('/applications')}>
          <ArrowLeft />
          Back to applications
        </Button>
      </PageContainer>
    )
  }

  if (!application) {
    return (
      <PageContainer>
        <DetailSkeleton />
      </PageContainer>
    )
  }

  const summary = automationSummary(application)
  // The input card is for open questions and security steps. A plain failure, or a run
  // paused for review, is handled by the header alert and the review panel instead.
  const needsUserInput =
    application.automation_state === 'REQUIRES_USER' || isManualStepPause(application.pause_reason)
  const canStart =
    !isRunning && !summary.needsUser && (application.status === 'QUEUED' || application.status === 'IN_PROGRESS')
  const applyUrl = application.job?.apply_url ?? application.external_url ?? application.job?.canonical_url ?? null

  async function run<T>(action: () => Promise<T>, success: string, failure: string): Promise<T | undefined> {
    try {
      const result = await action()
      toast.success(success)
      return result
    } catch (error) {
      toast.error(failure, { description: errorMessage(error) })
      return undefined
    }
  }

  async function handleStart() {
    const updated = await run(
      () => startApplication.mutateAsync(appId),
      'Automation started',
      'Could not start the automation',
    )
    if (updated) setIsRunning(updated.automation_state === 'RUNNING' || updated.automation_state === 'RETRYING')
  }

  async function handleApprove() {
    const updated = await run(
      () => approve.mutateAsync(appId),
      'Application submitted',
      'Could not submit this application',
    )
    if (updated) {
      toast.success(
        updated.confirmation_message ??
          (updated.external_application_id
            ? `Confirmed — reference ${updated.external_application_id}`
            : `Status is now ${APPLICATION_STATUS_LABELS[updated.status]}`),
      )
    }
  }

  async function handleSaveAnswers(updates: AnswerUpdate[]) {
    if (updates.length === 0) {
      setEditingReview(false)
      return
    }
    const saved = await run(
      () => updateAnswers.mutateAsync({ id: appId, answers: updates }),
      `Saved ${updates.length} ${updates.length === 1 ? 'answer' : 'answers'}`,
      'Could not save your answers',
    )
    if (saved) setEditingReview(false)
  }

  async function handleSaveAndContinue(updates: AnswerUpdate[]) {
    if (updates.length > 0) {
      const saved = await run(
        () => updateAnswers.mutateAsync({ id: appId, answers: updates }),
        'Answers saved',
        'Could not save your answers',
      )
      if (!saved) return
    }
    await handleContinue()
  }

  async function handleContinue() {
    const updated = await run(
      () => resumeAutomation.mutateAsync({ id: appId }),
      'Automation resumed',
      'Could not resume the automation',
    )
    if (updated) setIsRunning(updated.automation_state === 'RUNNING' || updated.automation_state === 'RETRYING')
  }

  async function handleRegenerate() {
    await run(
      () => generateAnswers.mutateAsync(appId),
      'Answers regenerated — your own edits were kept',
      'Could not regenerate the answers',
    )
  }

  async function handleGenerateCoverLetter(): Promise<string | null | undefined> {
    const result = await run(
      () => generateCoverLetter.mutateAsync(appId),
      'Cover letter drafted',
      'Could not draft a cover letter',
    )
    return result?.cover_letter ?? undefined
  }

  async function handleSaveCoverLetter(content: string) {
    await run(
      () => saveCoverLetter.mutateAsync({ id: appId, content }),
      'Cover letter saved',
      'Could not save the cover letter',
    )
  }

  async function handleSkip(reason?: string) {
    const updated = await run(
      () => skip.mutateAsync({ id: appId, ...(reason ? { reason } : {}) }),
      'Application skipped',
      'Could not skip this application',
    )
    if (updated) navigate('/queue')
  }

  async function handleWithdraw(reason?: string) {
    await run(
      () => withdraw.mutateAsync({ id: appId, ...(reason ? { reason } : {}) }),
      'Application withdrawn',
      'Could not withdraw this application',
    )
  }

  async function handleStatus(status: ApplicationStatus, note?: string) {
    await run(
      () => setStatus.mutateAsync({ id: appId, status, ...(note ? { note } : {}) }),
      `Status set to ${APPLICATION_STATUS_LABELS[status]}`,
      'Could not change the status',
    )
  }

  async function handlePatch(patch: ApplicationPatch) {
    await run(() => patchApplication.mutateAsync({ id: appId, patch }), 'Saved', 'Could not save your changes')
  }

  return (
    <PageContainer>
      <div className="flex items-center justify-between gap-2">
        <Button variant="ghost" size="sm" asChild>
          <Link to="/queue">
            <ArrowLeft />
            Back to queue
          </Link>
        </Button>
        {applicationQuery.isFetching ? (
          <span className="text-xs text-muted-foreground" aria-live="polite">
            {isRunning ? 'Watching the run…' : 'Refreshing…'}
          </span>
        ) : null}
      </div>

      {applicationQuery.isError ? (
        <RefreshErrorBanner error={applicationQuery.error} onRetry={() => void applicationQuery.refetch()} />
      ) : null}

      <ApplicationHeader
        application={application}
        resumes={resumesQuery.data}
        resumeChanging={patchApplication.isPending}
        onResumeChange={(resumeId) => void handlePatch({ resume_id: resumeId })}
        actions={
          <>
            {canStart ? (
              <Button onClick={() => void handleStart()} loading={startApplication.isPending}>
                <Play />
                {application.automation_state === 'IDLE' ? 'Start automation' : 'Run again'}
              </Button>
            ) : null}
            {summary.needsUser && !needsUserInput ? (
              <Button
                variant={application.automation_state === 'FAILED' ? 'default' : 'outline'}
                onClick={() => void handleContinue()}
                loading={resumeAutomation.isPending}
              >
                <Play />
                {application.automation_state === 'FAILED' ? 'Retry automation' : 'Continue'}
              </Button>
            ) : null}
            {applyUrl ? (
              <Button variant="outline" asChild>
                <a href={applyUrl} target="_blank" rel="noreferrer noopener">
                  <ExternalLink />
                  Open posting
                </a>
              </Button>
            ) : null}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" aria-label="More application actions">
                  <MoreHorizontal />
                  <ChevronDown />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={() => setStatusOpen(true)}>
                  <Undo2 />
                  Change status manually
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setNotesOpen(true)}>
                  <StickyNote />
                  Notes &amp; next action
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={() => setSkipOpen(true)}>Skip application</DropdownMenuItem>
                <DropdownMenuItem
                  onSelect={() => setWithdrawOpen(true)}
                  className="text-destructive focus:text-destructive"
                >
                  Withdraw application
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </>
        }
      />

      {needsUserInput ? (
        <UserInputCard
          application={application}
          onSaveAndContinue={handleSaveAndContinue}
          onContinue={handleContinue}
          saving={updateAnswers.isPending}
          resuming={resumeAutomation.isPending}
        />
      ) : null}

      {application.notes ? (
        <div className="rounded-lg border border-border bg-muted/40 p-3">
          <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Your notes</p>
          <p className="whitespace-pre-wrap text-sm">{application.notes}</p>
        </div>
      ) : null}

      <Tabs defaultValue="review">
        <TabsList className="flex-wrap">
          <TabsTrigger value="review">Review</TabsTrigger>
          <TabsTrigger value="answers">Answers ({application.answers?.length ?? 0})</TabsTrigger>
          <TabsTrigger value="cover-letter">Cover letter</TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
        </TabsList>

        <TabsContent value="review" className="mt-4 space-y-4">
          <ReviewPanel
            application={application}
            editing={editingReview}
            onToggleEdit={() => setEditingReview((value) => !value)}
            onSaveEdits={handleSaveAnswers}
            onApprove={() => setApproveOpen(true)}
            onSkip={() => setSkipOpen(true)}
            saving={updateAnswers.isPending}
            approving={approve.isPending}
          />
          <ScreenshotGallery applicationId={appId} names={screenshotNames} />
        </TabsContent>

        <TabsContent value="answers" className="mt-4">
          <AnswersTab
            answers={application.answers ?? []}
            onSave={handleSaveAnswers}
            onRegenerate={handleRegenerate}
            saving={updateAnswers.isPending}
            regenerating={generateAnswers.isPending}
            readOnly={isRunning}
          />
        </TabsContent>

        <TabsContent value="cover-letter" className="mt-4">
          <CoverLetterTab
            application={application}
            onGenerate={handleGenerateCoverLetter}
            onSave={handleSaveCoverLetter}
            generating={generateCoverLetter.isPending}
            saving={saveCoverLetter.isPending}
          />
        </TabsContent>

        <TabsContent value="timeline" className="mt-4">
          <TimelineTab
            events={eventsQuery.data ?? application.events}
            emails={application.emails ?? []}
            interviews={application.interviews ?? []}
            loading={eventsQuery.isLoading}
          />
        </TabsContent>
      </Tabs>

      <ConfirmDialog
        open={approveOpen}
        onOpenChange={setApproveOpen}
        title="Submit this application?"
        description={`${application.review?.job_title || application.job_title || 'This role'} at ${
          application.review?.company || application.company_name || 'this company'
        } will be submitted with the answers shown above. This cannot be undone from JobPilot.`}
        confirmLabel="Approve & submit"
        loading={approve.isPending}
        onConfirm={handleApprove}
      />

      <ReasonDialog
        open={skipOpen}
        onOpenChange={setSkipOpen}
        title="Skip this application?"
        description="It leaves your queue and nothing is submitted."
        placeholder="e.g. found a better role at the same company"
        confirmLabel="Skip"
        variant="destructive"
        loading={skip.isPending}
        onConfirm={handleSkip}
      />

      <ReasonDialog
        open={withdrawOpen}
        onOpenChange={setWithdrawOpen}
        title="Withdraw this application?"
        description="Marks the application as withdrawn on your tracker. Contact the company directly if they also need to know."
        placeholder="e.g. accepted another offer"
        confirmLabel="Withdraw"
        variant="destructive"
        loading={withdraw.isPending}
        onConfirm={handleWithdraw}
      />

      <StatusChangeDialog
        open={statusOpen}
        onOpenChange={setStatusOpen}
        status={application.status}
        subject={`${application.job_title ?? 'Application'} at ${application.company_name ?? '—'}`}
        allowPickStatus
        loading={setStatus.isPending}
        onConfirm={handleStatus}
      />

      <NotesDialog
        open={notesOpen}
        onOpenChange={setNotesOpen}
        notes={application.notes}
        nextAction={application.next_action}
        nextActionDue={application.next_action_due}
        loading={patchApplication.isPending}
        onSave={handlePatch}
      />
    </PageContainer>
  )
}
