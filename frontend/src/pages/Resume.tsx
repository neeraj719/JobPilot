import { useQueryClient } from '@tanstack/react-query'
import { FileText, UserRound } from 'lucide-react'
import * as React from 'react'
import { Link } from 'react-router-dom'

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
import { qk } from '@/lib/queryClient'
import {
  downloadResume,
  useDeleteResume,
  useReparseResume,
  useResumes,
  useUpdateResume,
} from '@/features/resume/api'
import { ParsedDataPanel } from '@/features/resume/components/ParsedDataPanel'
import { ResumeCard } from '@/features/resume/components/ResumeCard'
import { ResumeInsights } from '@/features/resume/components/ResumeInsights'
import { ResumeUploadCard } from '@/features/resume/components/ResumeUploadCard'
import { ResumeVersionHistory } from '@/features/resume/components/ResumeVersionHistory'
import type { ResumeRead } from '@/types/api'

export default function ResumePage() {
  useDocumentTitle('Resume')

  const resumesQuery = useResumes()
  const updateResume = useUpdateResume()
  const queryClient = useQueryClient()
  const reparse = useReparseResume()
  const deleteResume = useDeleteResume()

  const [selectedId, setSelectedId] = React.useState<string | null>(null)
  const [pendingDelete, setPendingDelete] = React.useState<ResumeRead | null>(null)
  const [busyId, setBusyId] = React.useState<string | null>(null)

  const resumes = React.useMemo(() => resumesQuery.data ?? [], [resumesQuery.data])

  // Keep a valid selection as the list changes (upload, delete, first load).
  React.useEffect(() => {
    if (resumes.length === 0) {
      if (selectedId !== null) setSelectedId(null)
      return
    }
    if (!selectedId || !resumes.some((resume) => resume.id === selectedId)) {
      setSelectedId(resumes.find((resume) => resume.is_default)?.id ?? resumes[0]?.id ?? null)
    }
  }, [resumes, selectedId])

  const selected = resumes.find((resume) => resume.id === selectedId) ?? null

  const withBusy = async (id: string, action: () => Promise<unknown>) => {
    setBusyId(id)
    try {
      await action()
    } finally {
      setBusyId(null)
    }
  }

  const handleRename = (resume: ResumeRead, name: string) =>
    withBusy(resume.id, async () => {
      try {
        await updateResume.mutateAsync({ id: resume.id, name })
        toast.success('Resume renamed')
      } catch (error) {
        toast.error('Could not rename the resume', { description: errorMessage(error) })
      }
    })

  const handleRetarget = (resume: ResumeRead, role: string | null) =>
    withBusy(resume.id, async () => {
      try {
        await updateResume.mutateAsync({ id: resume.id, target_role: role ?? '' })
        // The analysis is aimed at the target role, so it has to be recomputed.
        void queryClient.invalidateQueries({ queryKey: qk.resumes.recommendations(resume.id) })
        toast.success(role ? `Target role set to ${role}` : 'Target role cleared', {
          description: 'Recommendations are being updated for this role.',
        })
      } catch (error) {
        toast.error('Could not update the target role', { description: errorMessage(error) })
      }
    })

  const handleSetDefault = (resume: ResumeRead) =>
    withBusy(resume.id, async () => {
      try {
        await updateResume.mutateAsync({ id: resume.id, is_default: true })
        toast.success(`“${resume.name}” is now your default resume`)
      } catch (error) {
        toast.error('Could not set the default resume', { description: errorMessage(error) })
      }
    })

  const handleDownload = (resume: ResumeRead) =>
    withBusy(resume.id, async () => {
      try {
        await downloadResume(resume)
      } catch (error) {
        toast.error('Could not download the file', { description: errorMessage(error) })
      }
    })

  const handleReparse = (resume: ResumeRead) =>
    withBusy(resume.id, async () => {
      if ((resume.current_version ?? 1) > 1 && !window.confirm('Re-running extraction reads your uploaded file again and replaces the information below, including edits and applied suggestions. The current version stays in the history so you can restore it. Continue?')) return
      try {
        const updated = await reparse.mutateAsync(resume.id)
        toast[updated.parse_status === 'PARSED' ? 'success' : 'warning'](
          updated.parse_status === 'PARSED' ? 'Extraction re-run' : 'Extraction did not finish',
          { description: updated.parse_error ?? undefined },
        )
      } catch (error) {
        toast.error('Could not re-run extraction', { description: errorMessage(error) })
      }
    })

  const confirmDelete = async () => {
    if (!pendingDelete) return
    try {
      await deleteResume.mutateAsync(pendingDelete.id)
      toast.success(`Deleted “${pendingDelete.name}”`)
      if (selectedId === pendingDelete.id) setSelectedId(null)
      setPendingDelete(null)
    } catch (error) {
      toast.error('Could not delete the resume', { description: errorMessage(error) })
    }
  }

  return (
    <PageContainer>
      <PageHeader
        title="Resume"
        description="Upload a resume, check what the parser read, and fix anything it got wrong. The default resume is the one attached to applications."
        actions={
          <Button variant="outline" asChild>
            <Link to="/profile">
              <UserRound aria-hidden />
              Edit profile
            </Link>
          </Button>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
        <div className="space-y-4">
          <ResumeUploadCard isFirstResume={resumes.length === 0} onUploaded={(id) => setSelectedId(id)} />

          {resumesQuery.isLoading ? (
            <LoadingState variant="cards" rows={2} />
          ) : resumesQuery.error ? (
            <ErrorState
              error={resumesQuery.error}
              title="Could not load your resumes"
              onRetry={() => void resumesQuery.refetch()}
            />
          ) : resumes.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="No resumes yet"
              description="Upload a PDF or DOCX above. JobPilot parses it and uses the result to answer application forms."
            />
          ) : (
            <div className="space-y-3">
              {resumes.map((resume) => (
                <ResumeCard
                  key={resume.id}
                  resume={resume}
                  selected={resume.id === selectedId}
                  busy={busyId === resume.id}
                  onSelect={() => setSelectedId(resume.id)}
                  onRename={(name) => void handleRename(resume, name)}
                  onRetarget={(role) => void handleRetarget(resume, role)}
                  onSetDefault={() => void handleSetDefault(resume)}
                  onDownload={() => void handleDownload(resume)}
                  onReparse={() => void handleReparse(resume)}
                  onDelete={() => setPendingDelete(resume)}
                />
              ))}
            </div>
          )}
        </div>

        <div className="space-y-6">
          {selected ? (
            <>
              <ResumeInsights resume={selected} />
              <ParsedDataPanel resume={selected} />
              <ResumeVersionHistory resumeId={selected.id} currentVersion={selected.current_version} />
            </>
          ) : resumesQuery.isLoading ? (
            <LoadingState variant="cards" rows={2} />
          ) : (
            <EmptyState
              icon={FileText}
              title="Nothing selected"
              description="Pick a resume on the left to review and edit the information extracted from it."
            />
          )}
        </div>
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null)
        }}
        title={`Delete “${pendingDelete?.name ?? ''}”?`}
        description="The stored file and every parsed version are removed. Applications already submitted keep their own copy."
        confirmLabel="Delete resume"
        variant="destructive"
        loading={deleteResume.isPending}
        onConfirm={confirmDelete}
      />
    </PageContainer>
  )
}
