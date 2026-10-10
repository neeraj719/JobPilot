import { ArrowLeft, FlaskConical, Search } from 'lucide-react'
import * as React from 'react'
import { useSearchParams } from 'react-router-dom'

import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Pagination } from '@/components/ui/pagination'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { toast } from '@/components/ui/toaster'
import { useDebounce } from '@/hooks/useDebounce'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { errorMessage } from '@/lib/api'
import { EMAIL_CLASSIFICATION_LABELS, cn } from '@/lib/utils'
import {
  useApplicationOptions,
  useClassifyEmail,
  useConnectGmail,
  useEmail,
  useEmails,
  useIntegrations,
  useLinkEmail,
  useMarkEmailRead,
  useSimulateEmail,
  useSyncGmail,
  useUnlinkEmail,
} from '@/features/emails/api'
import { EmailDetail } from '@/features/emails/components/EmailDetail'
import { EmailList } from '@/features/emails/components/EmailList'
import { GmailConnectionBanner } from '@/features/emails/components/GmailConnectionBanner'
import { LinkApplicationDialog } from '@/features/emails/components/LinkApplicationDialog'
import { SimulateEmailDialog } from '@/features/emails/components/SimulateEmailDialog'
import {
  EMAIL_CLASSIFICATIONS,
  type ApplicationRead,
  type EmailClassification,
  type EmailListParams,
  type EmailSimulateRequest,
  type UUID,
} from '@/types/api'

const PAGE_SIZE = 20

/** Friendly copy for the `?error=` codes the Gmail OAuth callback can redirect with. */
const OAUTH_ERRORS: Record<string, string> = {
  access_denied: 'You declined the Google permission prompt, so nothing was connected.',
  connection_failed: 'The Gmail connection could not be completed. Please try again.',
  invalid_state: 'That authorisation link had expired. Start the connection again.',
  gmail_not_configured: 'Gmail OAuth is not configured on this server.',
}

export default function EmailsPage() {
  useDocumentTitle('Emails')
  const [searchParams, setSearchParams] = useSearchParams()

  const [classification, setClassification] = React.useState<'all' | EmailClassification>('all')
  const [unlinkedOnly, setUnlinkedOnly] = React.useState(false)
  const [search, setSearch] = React.useState('')
  const [page, setPage] = React.useState(1)
  const [selectedId, setSelectedId] = React.useState<UUID | null>(null)
  const [linkOpen, setLinkOpen] = React.useState(false)
  const [simulateOpen, setSimulateOpen] = React.useState(false)

  const debouncedSearch = useDebounce(search, 300)

  const listParams: EmailListParams = {
    page,
    page_size: PAGE_SIZE,
    classification: classification === 'all' ? undefined : classification,
    unlinked: unlinkedOnly ? true : undefined,
    q: debouncedSearch || undefined,
  }

  const emailsQuery = useEmails(listParams)
  const detailQuery = useEmail(selectedId)
  const integrationsQuery = useIntegrations()
  // One request feeds the "linked to …" chips and the detail pane's application card.
  const applicationsQuery = useApplicationOptions({ page_size: 100 })

  const markRead = useMarkEmailRead()
  const classify = useClassifyEmail()
  const link = useLinkEmail()
  const unlink = useUnlinkEmail()
  const simulate = useSimulateEmail()
  const connectGmail = useConnectGmail()
  const syncGmail = useSyncGmail()

  const applicationsById = React.useMemo(() => {
    const map = new Map<UUID, ApplicationRead>()
    for (const application of applicationsQuery.data?.items ?? []) map.set(application.id, application)
    return map
  }, [applicationsQuery.data?.items])

  const emails = emailsQuery.data?.items
  const selectedEmail = detailQuery.data ?? emails?.find((item) => item.id === selectedId) ?? null
  const linkedApplication = selectedEmail?.application_id
    ? applicationsById.get(selectedEmail.application_id)
    : undefined

  // The Gmail OAuth callback bounces back here with ?connected=1 or ?error=<code>.
  React.useEffect(() => {
    const connected = searchParams.get('connected')
    const error = searchParams.get('error')
    if (!connected && !error) return

    if (connected) {
      toast.success('Gmail connected', { description: 'Read-only access granted. Sync to pull in recent mail.' })
      void integrationsQuery.refetch()
    }
    if (error) {
      toast.error('Gmail could not be connected', {
        description: OAUTH_ERRORS[error] ?? `The connection failed (${error}).`,
      })
    }

    const next = new URLSearchParams(searchParams)
    next.delete('connected')
    next.delete('error')
    setSearchParams(next, { replace: true })
    // Runs once per callback redirect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])

  React.useEffect(() => {
    setPage(1)
  }, [classification, unlinkedOnly, debouncedSearch])

  async function handleConnect() {
    try {
      const { authorization_url } = await connectGmail.mutateAsync()
      toast.info('Opening Google…', { description: 'Approve read-only access to finish connecting.' })
      window.location.assign(authorization_url)
    } catch (error) {
      toast.error('Could not start the Gmail connection', { description: errorMessage(error) })
    }
  }

  async function handleSync() {
    try {
      const result = await syncGmail.mutateAsync()
      toast.success('Inbox synced', {
        description: `${result.fetched} fetched · ${result.new} new · ${result.classified} classified · ${result.linked} linked · ${result.status_updates} status update${result.status_updates === 1 ? '' : 's'}`,
      })
    } catch (error) {
      toast.error('Sync failed', { description: errorMessage(error) })
    }
  }

  async function handleMarkRead() {
    if (!selectedEmail) return
    try {
      await markRead.mutateAsync(selectedEmail.id)
    } catch (error) {
      toast.error('Could not mark the email as read', { description: errorMessage(error) })
    }
  }

  async function handleClassify(next: EmailClassification) {
    if (!selectedEmail || next === selectedEmail.classification) return
    try {
      const updated = await classify.mutateAsync({ id: selectedEmail.id, classification: next })
      toast.success(`Reclassified as ${EMAIL_CLASSIFICATION_LABELS[next]}`, {
        description: updated.status_applied
          ? 'The linked application status was updated to match.'
          : 'The classification was saved.',
      })
    } catch (error) {
      toast.error('Could not reclassify the email', { description: errorMessage(error) })
    }
  }

  async function handleLink(applicationId: UUID) {
    if (!selectedEmail) return
    try {
      await link.mutateAsync({ id: selectedEmail.id, applicationId })
      setLinkOpen(false)
      toast.success('Email linked', { description: 'It now shows on the application timeline.' })
    } catch (error) {
      toast.error('Could not link the email', { description: errorMessage(error) })
    }
  }

  async function handleUnlink() {
    if (!selectedEmail) return
    try {
      await unlink.mutateAsync(selectedEmail.id)
      toast.success('Email unlinked')
    } catch (error) {
      toast.error('Could not unlink the email', { description: errorMessage(error) })
    }
  }

  async function handleSimulate(payload: EmailSimulateRequest) {
    try {
      const created = await simulate.mutateAsync(payload)
      setSimulateOpen(false)
      setSelectedId(created.id)
      toast.success('Simulated email delivered', {
        description: `Classified as ${EMAIL_CLASSIFICATION_LABELS[created.classification]}${created.application_id ? ' and linked to an application.' : '.'}`,
      })
    } catch (error) {
      toast.error('Could not simulate the email', { description: errorMessage(error) })
    }
  }

  const unreadCount = (emails ?? []).filter((email) => !email.is_read).length

  return (
    <PageContainer width="wide">
      <PageHeader
        title="Emails"
        description="Replies detected in your inbox, classified and linked to the application they belong to."
        actions={
          <Button variant="outline" onClick={() => setSimulateOpen(true)}>
            <FlaskConical />
            Simulate email
          </Button>
        }
      />

      <GmailConnectionBanner
        gmail={integrationsQuery.data?.gmail}
        loading={integrationsQuery.isLoading}
        connecting={connectGmail.isPending}
        syncing={syncGmail.isPending}
        onConnect={() => void handleConnect()}
        onSync={() => void handleSync()}
      />

      <div className="grid gap-4 lg:grid-cols-[22rem_minmax(0,1fr)] xl:grid-cols-[26rem_minmax(0,1fr)]">
        <div className={cn('min-w-0 space-y-3', selectedId && 'hidden lg:block')}>
          <div className="space-y-2">
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden
              />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search sender, subject or body…"
                className="pl-8"
                aria-label="Search emails"
              />
            </div>
            <div className="flex items-center gap-2">
              <Select
                value={classification}
                onValueChange={(value) => setClassification(value as 'all' | EmailClassification)}
              >
                <SelectTrigger className="flex-1" aria-label="Filter by classification">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All classifications</SelectItem>
                  {EMAIL_CLASSIFICATIONS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {EMAIL_CLASSIFICATION_LABELS[option]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <div className="flex shrink-0 items-center gap-2 rounded-md border border-input px-3 py-2">
                <Checkbox
                  id="unlinked-only"
                  checked={unlinkedOnly}
                  onCheckedChange={(checked) => setUnlinkedOnly(checked === true)}
                />
                <Label htmlFor="unlinked-only" className="cursor-pointer whitespace-nowrap text-xs">
                  Unlinked only
                </Label>
              </div>
            </div>
          </div>

          <Card className="overflow-hidden">
            <div className="flex items-center justify-between border-b border-border px-3 py-2 text-xs text-muted-foreground">
              <span>
                {emailsQuery.data?.total ?? 0} email{(emailsQuery.data?.total ?? 0) === 1 ? '' : 's'}
              </span>
              {unreadCount > 0 ? <span>{unreadCount} unread on this page</span> : null}
            </div>
            <div className="max-h-[32rem] overflow-y-auto lg:max-h-[38rem]">
              <EmailList
                emails={emails}
                loading={emailsQuery.isLoading}
                error={emailsQuery.isError ? emailsQuery.error : undefined}
                onRetry={() => void emailsQuery.refetch()}
                selectedId={selectedId}
                onSelect={(email) => setSelectedId(email.id)}
                applicationsById={applicationsById}
                emptyTitle={
                  debouncedSearch || classification !== 'all' || unlinkedOnly ? 'No matching emails' : 'No emails yet'
                }
                emptyDescription={
                  debouncedSearch || classification !== 'all' || unlinkedOnly
                    ? 'Try a different filter or clear the search.'
                    : 'Connect Gmail or use “Simulate email” to see how replies are classified and linked.'
                }
              />
            </div>
          </Card>

          {emailsQuery.data ? (
            <Pagination
              page={page}
              pageSize={emailsQuery.data.page_size}
              total={emailsQuery.data.total}
              onPageChange={setPage}
              disabled={emailsQuery.isLoading}
            />
          ) : null}
        </div>

        <div className={cn('min-w-0 space-y-2', !selectedId && 'hidden lg:block')}>
          {selectedId ? (
            <Button variant="ghost" size="sm" className="lg:hidden" onClick={() => setSelectedId(null)}>
              <ArrowLeft />
              Back to inbox
            </Button>
          ) : null}
          <Card className="min-h-[24rem] overflow-hidden lg:h-[calc(38rem+2.25rem)]">
            <EmailDetail
              email={selectedEmail}
              application={linkedApplication}
              loading={Boolean(selectedId) && detailQuery.isLoading && !selectedEmail}
              markReadPending={markRead.isPending}
              classifyPending={classify.isPending}
              unlinkPending={unlink.isPending}
              onMarkRead={() => void handleMarkRead()}
              onClassify={(value) => void handleClassify(value)}
              onLink={() => setLinkOpen(true)}
              onUnlink={() => void handleUnlink()}
            />
          </Card>
        </div>
      </div>

      <LinkApplicationDialog
        open={linkOpen}
        onOpenChange={setLinkOpen}
        subject={selectedEmail?.subject}
        currentApplicationId={selectedEmail?.application_id ?? null}
        saving={link.isPending}
        onConfirm={handleLink}
      />

      <SimulateEmailDialog
        open={simulateOpen}
        onOpenChange={setSimulateOpen}
        saving={simulate.isPending}
        onSubmit={handleSimulate}
      />
    </PageContainer>
  )
}
