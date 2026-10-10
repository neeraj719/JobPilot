import { CalendarClock, CalendarPlus, History } from 'lucide-react'
import * as React from 'react'

import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { LoadingState } from '@/components/common/LoadingState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { toast } from '@/components/ui/toaster'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { errorMessage } from '@/lib/api'
import {
  useCreateInterview,
  useDeleteInterview,
  useGenerateInterviewPrep,
  useInterviews,
  useUpdateInterview,
} from '@/features/interviews/api'
import { InterviewCard } from '@/features/interviews/components/InterviewCard'
import { InterviewDetailSheet } from '@/features/interviews/components/InterviewDetailSheet'
import {
  InterviewFormDialog,
  type InterviewFormSubmit,
} from '@/features/interviews/components/InterviewFormDialog'
import { splitInterviews } from '@/features/interviews/helpers'
import type { InterviewRead } from '@/types/api'

function Section({
  title,
  count,
  icon: Icon,
  children,
}: {
  title: string
  count: number
  icon: typeof CalendarClock
  children: React.ReactNode
}) {
  return (
    <section className="space-y-3">
      <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        <Icon className="size-4" aria-hidden />
        {title}
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs tabular-nums text-muted-foreground">{count}</span>
      </h2>
      {children}
    </section>
  )
}

export default function InterviewsPage() {
  useDocumentTitle('Interviews')

  const [formOpen, setFormOpen] = React.useState(false)
  const [editing, setEditing] = React.useState<InterviewRead | null>(null)
  const [detailId, setDetailId] = React.useState<string | null>(null)
  const [detailOpen, setDetailOpen] = React.useState(false)
  const [pendingDelete, setPendingDelete] = React.useState<InterviewRead | null>(null)

  // One page covers every round a single user realistically has; split locally so the
  // upcoming and past lists always agree with each other.
  const interviewsQuery = useInterviews({ page_size: 100 })

  const createInterview = useCreateInterview()
  const updateInterview = useUpdateInterview()
  const deleteInterview = useDeleteInterview()
  const generatePrep = useGenerateInterviewPrep()

  const { upcoming, past } = React.useMemo(
    () => splitInterviews(interviewsQuery.data?.items),
    [interviewsQuery.data?.items],
  )

  const allInterviews = interviewsQuery.data?.items ?? []
  const selected = allInterviews.find((interview) => interview.id === detailId) ?? null

  function openDetail(interview: InterviewRead) {
    setDetailId(interview.id)
    setDetailOpen(true)
  }

  function openCreate() {
    setEditing(null)
    setFormOpen(true)
  }

  function openEdit(interview: InterviewRead) {
    setEditing(interview)
    setFormOpen(true)
  }

  async function handleSubmitForm(values: InterviewFormSubmit) {
    const payload = {
      interview_type: values.interview_type,
      status: values.status,
      round_number: values.round_number,
      scheduled_at: values.scheduled_at,
      duration_minutes: values.duration_minutes,
      location_or_link: values.location_or_link,
      interviewer: values.interviewer,
      notes: values.notes,
    }

    try {
      if (editing) {
        await updateInterview.mutateAsync({ id: editing.id, payload })
        toast.success('Interview updated')
      } else {
        if (!values.application_id) return
        const created = await createInterview.mutateAsync({ ...payload, application_id: values.application_id })
        setDetailId(created.id)
        toast.success('Interview added', { description: 'Generate a preparation sheet when you are ready.' })
      }
      setFormOpen(false)
      setEditing(null)
    } catch (error) {
      toast.error(editing ? 'Could not update the interview' : 'Could not add the interview', {
        description: errorMessage(error),
      })
    }
  }

  async function handleGeneratePrep(interview: InterviewRead) {
    try {
      await generatePrep.mutateAsync(interview.id)
      toast.success('Preparation ready', { description: 'Questions tailored to this role, company and your resume.' })
    } catch (error) {
      toast.error('Could not generate the preparation', { description: errorMessage(error) })
    }
  }

  async function handleComplete(interview: InterviewRead, outcome: string) {
    try {
      await updateInterview.mutateAsync({ id: interview.id, payload: { status: 'COMPLETED', outcome } })
      toast.success('Marked as completed')
    } catch (error) {
      toast.error('Could not update the interview', { description: errorMessage(error) })
    }
  }

  async function handleCancelRound(interview: InterviewRead) {
    try {
      await updateInterview.mutateAsync({ id: interview.id, payload: { status: 'CANCELLED' } })
      toast.success('Interview cancelled')
    } catch (error) {
      toast.error('Could not cancel the interview', { description: errorMessage(error) })
    }
  }

  async function handleDelete() {
    if (!pendingDelete) return
    try {
      await deleteInterview.mutateAsync(pendingDelete.id)
      if (detailId === pendingDelete.id) {
        setDetailOpen(false)
        setDetailId(null)
      }
      toast.success('Interview deleted')
    } catch (error) {
      toast.error('Could not delete the interview', { description: errorMessage(error) })
    } finally {
      setPendingDelete(null)
    }
  }

  const isEmpty = !interviewsQuery.isLoading && !interviewsQuery.isError && allInterviews.length === 0

  return (
    <PageContainer>
      <PageHeader
        title="Interviews"
        description="Scheduled rounds and the AI-generated preparation material for each one."
        actions={
          <Button onClick={openCreate}>
            <CalendarPlus />
            Add interview
          </Button>
        }
      />

      {interviewsQuery.isError ? (
        <ErrorState
          error={interviewsQuery.error}
          title="Could not load your interviews"
          onRetry={() => void interviewsQuery.refetch()}
        />
      ) : interviewsQuery.isLoading ? (
        <LoadingState variant="cards" rows={3} />
      ) : isEmpty ? (
        <EmptyState
          icon={CalendarClock}
          title="No interviews yet"
          description="When an application reaches Interview it appears here automatically — from a recruiter email, or added by hand."
          action={
            <Button onClick={openCreate}>
              <CalendarPlus />
              Add interview
            </Button>
          }
        />
      ) : (
        <div className="space-y-8">
          <Section title="Upcoming" count={upcoming.length} icon={CalendarClock}>
            {upcoming.length === 0 ? (
              <EmptyState
                size="sm"
                icon={CalendarClock}
                title="Nothing scheduled"
                description="Every round you have is in the past. New ones show up here as soon as they are booked."
              />
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {upcoming.map((interview) => (
                  <InterviewCard key={interview.id} interview={interview} onOpen={openDetail} highlight />
                ))}
              </div>
            )}
          </Section>

          {past.length > 0 ? (
            <Section title="Past" count={past.length} icon={History}>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {past.map((interview) => (
                  <InterviewCard key={interview.id} interview={interview} onOpen={openDetail} />
                ))}
              </div>
            </Section>
          ) : null}
        </div>
      )}

      <InterviewDetailSheet
        interview={selected}
        open={detailOpen && Boolean(selected)}
        onOpenChange={(open) => {
          setDetailOpen(open)
          if (!open) setDetailId(null)
        }}
        generating={generatePrep.isPending}
        updating={updateInterview.isPending}
        deleting={deleteInterview.isPending}
        onGeneratePrep={(interview) => void handleGeneratePrep(interview)}
        onEdit={(interview) => {
          setDetailOpen(false)
          openEdit(interview)
        }}
        onComplete={(interview, outcome) => void handleComplete(interview, outcome)}
        onCancel={(interview) => void handleCancelRound(interview)}
        onDelete={(interview) => setPendingDelete(interview)}
      />

      <InterviewFormDialog
        open={formOpen}
        onOpenChange={(open) => {
          setFormOpen(open)
          if (!open) setEditing(null)
        }}
        interview={editing}
        saving={createInterview.isPending || updateInterview.isPending}
        onSubmit={handleSubmitForm}
      />

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        onOpenChange={(open) => (open ? undefined : setPendingDelete(null))}
        title="Delete this interview?"
        description={
          pendingDelete
            ? `Round ${pendingDelete.round_number} at ${pendingDelete.company_name ?? 'this company'} will be removed, along with its preparation sheet. This cannot be undone.`
            : undefined
        }
        confirmLabel="Delete interview"
        variant="destructive"
        loading={deleteInterview.isPending}
        onConfirm={handleDelete}
      />
    </PageContainer>
  )
}
