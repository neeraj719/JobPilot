import { Bookmark, Pencil, Trash2 } from 'lucide-react'
import * as React from 'react'

import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { LoadingState } from '@/components/common/LoadingState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { toast } from '@/components/ui/toaster'
import { AnswerField } from '@/features/applications/components/AnswerField'
import {
  COMPANY_PLACEHOLDER,
  useDeleteStandingAnswer,
  useSaveStandingAnswer,
  useStandingAnswers,
} from '@/features/profile/standingAnswers'
import { errorMessage } from '@/lib/api'
import { formatDate, sourceLabel } from '@/lib/utils'
import type { StandingAnswerRead } from '@/types/api'

/** Show `{company}` as the reader would understand it. */
function wording(text: string): string {
  return text.split(COMPANY_PLACEHOLDER).join('[the company]')
}

function scopeLabel(row: StandingAnswerRead): string {
  if (row.applies_to === 'ALL') return 'All sources'
  return row.applies_to.map((source) => sourceLabel(source)).join(', ')
}

function isExpired(row: StandingAnswerRead): boolean {
  return Boolean(row.expires_at && new Date(row.expires_at).getTime() <= Date.now())
}

interface RowProps {
  row: StandingAnswerRead
  onDelete: (row: StandingAnswerRead) => void
}

function StandingAnswerRow({ row, onDelete }: RowProps) {
  const save = useSaveStandingAnswer()
  const [editing, setEditing] = React.useState(false)
  const [draft, setDraft] = React.useState(row.answer)
  const [active, setActive] = React.useState(row.is_active)

  React.useEffect(() => {
    if (!editing) {
      setDraft(row.answer)
      setActive(row.is_active)
    }
  }, [editing, row.answer, row.is_active])

  async function handleSave() {
    try {
      await save.mutateAsync({
        question_key: row.question_key,
        question_text: row.question_text,
        field_type: row.field_type,
        answer: draft.trim(),
        applies_to: row.applies_to,
        expires_at: row.expires_at,
        is_active: active,
      })
      toast.success('Standing answer saved')
      setEditing(false)
    } catch (error) {
      toast.error('Could not save the standing answer', { description: errorMessage(error) })
    }
  }

  const expired = isExpired(row)
  return (
    <li className="space-y-2 py-4 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 space-y-1">
          <p className="text-sm font-medium leading-snug">{wording(row.question_text)}</p>
          <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <Badge variant="outline">{scopeLabel(row)}</Badge>
            {!row.is_active ? <Badge variant="muted">Off</Badge> : null}
            {expired ? <Badge variant="warning">Expired</Badge> : null}
            {row.expires_at && !expired ? <span>Until {formatDate(row.expires_at)}</span> : null}
          </div>
        </div>
        {!editing ? (
          <div className="flex shrink-0 items-center gap-1">
            <Button variant="ghost" size="icon-sm" onClick={() => setEditing(true)} aria-label="Edit standing answer">
              <Pencil aria-hidden />
            </Button>
            <Button variant="ghost" size="icon-sm" onClick={() => onDelete(row)} aria-label="Delete standing answer">
              <Trash2 aria-hidden />
            </Button>
          </div>
        ) : null}
      </div>

      {editing ? (
        <div className="space-y-3 rounded-md border bg-muted/30 p-3">
          <AnswerField
            id={`standing-${row.id}`}
            fieldType={row.field_type}
            options={[]}
            value={draft}
            onChange={setDraft}
            disabled={save.isPending}
            aria-label="Answer"
          />
          <div className="flex items-center gap-2">
            <Switch id={`standing-active-${row.id}`} checked={active} onCheckedChange={setActive} />
            <Label htmlFor={`standing-active-${row.id}`} className="font-normal">
              Use this answer on new applications
            </Label>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setEditing(false)} disabled={save.isPending}>
              Cancel
            </Button>
            <Button size="sm" onClick={() => void handleSave()} loading={save.isPending} disabled={!draft.trim()}>
              Save
            </Button>
          </div>
        </div>
      ) : (
        <p className="whitespace-pre-wrap rounded-md bg-muted/40 px-3 py-2 text-sm">{row.answer}</p>
      )}
    </li>
  )
}

/**
 * The answers the user gave once — consent, start date, notice period... — that every
 * later application reuses instead of pausing. Saved from the Approval Center with
 * "Remember this answer"; edited or removed here.
 */
export function StandingAnswersCard() {
  const query = useStandingAnswers()
  const remove = useDeleteStandingAnswer()
  const [pendingDelete, setPendingDelete] = React.useState<StandingAnswerRead | null>(null)

  async function handleDelete() {
    if (!pendingDelete) return
    try {
      await remove.mutateAsync(pendingDelete.id)
      toast.success('Standing answer deleted')
    } catch (error) {
      toast.error('Could not delete the standing answer', { description: errorMessage(error) })
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Bookmark className="size-4" aria-hidden />
          Standing answers
        </CardTitle>
        <CardDescription>
          Answers you gave once and want reused on every application. A consent or legal declaration is only reused
          when the form words it the same way; demographic questions are always asked.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {query.error ? (
          <ErrorState error={query.error} title="Could not load your standing answers" onRetry={() => void query.refetch()} />
        ) : query.isLoading ? (
          <LoadingState variant="list" rows={2} />
        ) : (query.data ?? []).length === 0 ? (
          <EmptyState
            size="sm"
            icon={Bookmark}
            title="No standing answers yet"
            description='When an application asks something only you can answer, tick "Remember this answer" to reuse it next time.'
          />
        ) : (
          <ul className="divide-y">
            {(query.data ?? []).map((row) => (
              <StandingAnswerRow key={row.id} row={row} onDelete={setPendingDelete} />
            ))}
          </ul>
        )}
      </CardContent>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null)
        }}
        title="Delete this standing answer?"
        description="Applications that ask this question will pause for your answer again."
        confirmLabel="Delete"
        variant="destructive"
        loading={remove.isPending}
        onConfirm={handleDelete}
      />
    </Card>
  )
}
