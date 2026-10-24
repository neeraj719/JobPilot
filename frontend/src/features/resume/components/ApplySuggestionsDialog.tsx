import { ChevronDown, Wand2 } from 'lucide-react'
import * as React from 'react'

import { SkeletonLine, SkeletonRegion } from '@/components/common/skeletons'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { toast } from '@/components/ui/toaster'
import { errorMessage, isApiError } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useApplyPlan, useApplySuggestions } from '@/features/resume/api'
import { CATEGORY_LABELS, PRIORITY_LABELS } from '@/features/resume/recommendations'
import type { ResumeApplicableChange, ResumeApplyPlan, ResumeManualItem } from '@/types/api'

const PLACEHOLDER_RE = /\[[^[\]]*\]/
const TOKEN_RE = /\[[^[\]]*\]|\s+|[\p{L}\p{N}_'’+#-]+|[^\s]/gu

export function hasPlaceholder(text: string): boolean {
  return PLACEHOLDER_RE.test(text)
}

function formatGain(value: number): string {
  const rounded = Math.round(value * 10) / 10
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1)
}

/* ------------------------------------------------------------------ diff */

type DiffOp = { type: 'same' | 'add' | 'del'; text: string }

/** Word-level diff (LCS). Bracketed placeholders stay one token so they can be highlighted. */
function diffWords(before: string, after: string): DiffOp[] {
  const a = before.match(TOKEN_RE) ?? []
  const b = after.match(TOKEN_RE) ?? []
  const rows = a.length + 1
  const cols = b.length + 1
  const table = new Uint16Array(rows * cols)
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      table[i * cols + j] =
        a[i] === b[j] ? table[(i + 1) * cols + j + 1] + 1 : Math.max(table[(i + 1) * cols + j], table[i * cols + j + 1])
    }
  }
  const ops: DiffOp[] = []
  const push = (type: DiffOp['type'], text: string) => {
    const last = ops[ops.length - 1]
    if (last && last.type === type) last.text += text
    else ops.push({ type, text })
  }
  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      push('same', a[i])
      i += 1
      j += 1
    } else if (table[(i + 1) * cols + j] >= table[i * cols + j + 1]) {
      push('del', a[i])
      i += 1
    } else {
      push('add', b[j])
      j += 1
    }
  }
  while (i < a.length) push('del', a[i++])
  while (j < b.length) push('add', b[j++])
  return ops
}

/** Highlight `[...]` placeholders inside a run of text. */
function WithPlaceholders({ text }: { text: string }) {
  const parts = text.split(/(\[[^[\]]*\])/g)
  return (
    <>
      {parts.map((part, index) =>
        PLACEHOLDER_RE.test(part) ? (
          <mark key={index} className="rounded bg-warning/30 px-0.5 text-foreground ring-1 ring-warning/60">
            {part}
          </mark>
        ) : (
          <React.Fragment key={index}>{part}</React.Fragment>
        ),
      )}
    </>
  )
}

function ChangeDiff({ before, after }: { before: string | null; after: string }) {
  if (!before) {
    return (
      <p className="text-sm">
        <span className="rounded bg-success/15 px-1">
          <WithPlaceholders text={after} />
        </span>
      </p>
    )
  }
  const ops = diffWords(before, after)
  const kept = ops.filter((op) => op.type === 'same').reduce((n, op) => n + op.text.trim().split(/\s+/).filter(Boolean).length, 0)
  const total = Math.max(1, (after.match(/\S+/g) ?? []).length)
  if (kept / total < 0.5) {
    // Mostly rewritten: an interleaved word diff is unreadable, so show both versions.
    return (
      <div className="space-y-2 text-sm leading-relaxed" aria-label="Before and after">
        <div className="rounded-md border border-border bg-muted/40 p-2.5">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Now</p>
          <p className="whitespace-pre-line break-words text-muted-foreground">{before}</p>
        </div>
        <div className="rounded-md border border-success/30 bg-success/10 p-2.5">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-success">After</p>
          <p className="whitespace-pre-line break-words">
            <WithPlaceholders text={after} />
          </p>
        </div>
      </div>
    )
  }
  return (
    <p className="whitespace-pre-line break-words text-sm leading-relaxed" aria-label="Before and after">
      {ops.map((op, index) =>
        op.type === 'same' ? (
          <WithPlaceholders key={index} text={op.text} />
        ) : op.type === 'del' ? (
          <del key={index} className="rounded bg-destructive/10 text-muted-foreground decoration-destructive/70">
            {op.text}
          </del>
        ) : (
          <ins key={index} className="rounded bg-success/15 no-underline">
            <WithPlaceholders text={op.text} />
          </ins>
        ),
      )}
    </p>
  )
}

/* ------------------------------------------------------------------ rows */

interface RowProps {
  change: ResumeApplicableChange
  checked: boolean
  text: string
  error: string | undefined
  disabled: boolean
  onCheckedChange: (checked: boolean) => void
  onTextChange: (text: string) => void
}

function ChangeRow({ change, checked, text, error, disabled, onCheckedChange, onTextChange }: RowProps) {
  const checkboxId = React.useId()
  const hintId = React.useId()
  const editable = change.kind !== 'ADD_SKILL'
  const placeholderLeft = editable && hasPlaceholder(text)
  const empty = editable && text.trim().length === 0
  const blocked = placeholderLeft || empty

  return (
    <li
      className={cn(
        'rounded-md border border-border p-3 transition-colors',
        checked && 'border-primary/50 bg-primary/5',
        error && 'border-destructive/60',
      )}
      data-change-id={change.id}
    >
      <div className="flex items-start gap-3">
        <Checkbox
          id={checkboxId}
          className="mt-0.5"
          checked={checked && !blocked}
          disabled={disabled || blocked}
          onCheckedChange={(value) => onCheckedChange(value === true)}
          aria-describedby={placeholderLeft ? hintId : undefined}
        />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor={checkboxId} className="cursor-pointer text-sm font-medium">
              {change.confirmation_label ?? change.title}
            </label>
            {change.estimated_score_gain > 0 ? (
              <Badge variant="success" title="Estimated average match score gain across your target jobs">
                +{formatGain(change.estimated_score_gain)} avg match
              </Badge>
            ) : null}
          </div>
          {change.confirmation_label ? <p className="text-xs text-muted-foreground">{change.title}</p> : null}

          <ChangeDiff before={change.before} after={editable ? text : change.after} />

          {editable ? (
            <Textarea
              value={text}
              onChange={(event) => onTextChange(event.target.value)}
              rows={change.kind === 'REPLACE_SUMMARY' ? 4 : 2}
              disabled={disabled}
              aria-label={`Edit: ${change.title}`}
              aria-invalid={Boolean(error) || undefined}
              className="text-sm"
            />
          ) : null}
          {placeholderLeft ? (
            <p id={hintId} className="text-xs text-warning">
              Replace the bracketed part with your real result
            </p>
          ) : null}
          {error ? (
            <p role="alert" className="text-xs text-destructive">
              {error}
            </p>
          ) : null}
        </div>
      </div>
    </li>
  )
}

function ManualList({ items }: { items: ResumeManualItem[] }) {
  const [open, setOpen] = React.useState(false)
  const listId = React.useId()
  if (items.length === 0) return null
  return (
    <section className="space-y-2">
      <button
        type="button"
        className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground hover:text-foreground"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((value) => !value)}
      >
        <ChevronDown className={cn('size-3.5 transition-transform', open && 'rotate-180')} aria-hidden />
        Needs your work ({items.length})
      </button>
      {open ? (
        <ul id={listId} className="space-y-2">
          {items.map((item) => (
            <li key={item.recommendation_id} className="rounded-md border border-dashed border-border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium">{item.title}</span>
                <Badge variant="outline">{CATEGORY_LABELS[item.category]}</Badge>
                <Badge variant="muted">{PRIORITY_LABELS[item.priority]}</Badge>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">{item.detail}</p>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}

/* ------------------------------------------------------------------ dialog */

function initialState(plan: ResumeApplyPlan) {
  const texts: Record<string, string> = {}
  const selected = new Set<string>()
  for (const change of plan.changes) {
    texts[change.id] = change.after
    if (change.selected_by_default && !change.has_placeholders) selected.add(change.id)
  }
  return { texts, selected }
}

function selectable(change: ResumeApplicableChange, text: string): boolean {
  if (change.kind === 'ADD_SKILL') return true
  return text.trim().length > 0 && !hasPlaceholder(text)
}

export interface ApplySuggestionsDialogProps {
  resumeId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * Review the applicable suggestions, edit the text ones, and save once as a new version.
 * Safe changes start ticked; anything that needs the candidate's own facts starts empty.
 */
export function ApplySuggestionsDialog({ resumeId, open, onOpenChange }: ApplySuggestionsDialogProps) {
  const planQuery = useApplyPlan(resumeId)
  const applyMutation = useApplySuggestions(resumeId)
  const plan = planQuery.data

  const [texts, setTexts] = React.useState<Record<string, string>>({})
  const [selected, setSelected] = React.useState<Set<string>>(new Set())
  const [errors, setErrors] = React.useState<Record<string, string>>({})
  const [formError, setFormError] = React.useState<string | null>(null)

  const planKey = plan ? `${plan.resume_version}:${plan.changes.map((c) => `${c.id}=${c.after}`).join('|')}` : ''
  React.useEffect(() => {
    if (!open || !plan) return
    const state = initialState(plan)
    setTexts(state.texts)
    setSelected(state.selected)
    setErrors({})
    setFormError(null)
    // planKey captures every field the initial state reads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, planKey])

  const changes = plan?.changes ?? []
  const ready = changes.filter((change) => !change.requires_confirmation)
  const confirm = changes.filter((change) => change.requires_confirmation)
  const textOf = (change: ResumeApplicableChange) => texts[change.id] ?? change.after
  const effective = changes.filter((change) => selected.has(change.id) && selectable(change, textOf(change)))
  const projectedGain = effective.reduce((sum, change) => sum + change.estimated_score_gain, 0)
  const saving = applyMutation.isPending

  const toggle = (id: string, checked: boolean) => {
    setSelected((previous) => {
      const next = new Set(previous)
      if (checked) next.add(id)
      else next.delete(id)
      return next
    })
  }

  const editText = (id: string, text: string) => {
    setTexts((previous) => ({ ...previous, [id]: text }))
    setErrors((previous) => {
      if (!previous[id]) return previous
      const next = { ...previous }
      delete next[id]
      return next
    })
  }

  /** Ticks every change that can be applied as it stands, including the "I have used X" skills. */
  const selectAll = () =>
    setSelected(() => {
      const next = new Set<string>()
      for (const change of changes) if (selectable(change, textOf(change))) next.add(change.id)
      return next
    })

  const submit = async () => {
    if (!plan || effective.length === 0) return
    setErrors({})
    setFormError(null)
    try {
      const result = await applyMutation.mutateAsync({
        resume_version: plan.resume_version,
        changes: effective.map((change) =>
          change.kind === 'ADD_SKILL' ? { id: change.id } : { id: change.id, after: textOf(change).trim() },
        ),
      })
      const count = result.applied.length
      const version = result.resume.current_version
      if (count > 0) {
        toast.success(`Applied ${count} ${count === 1 ? 'suggestion' : 'suggestions'} — saved as version ${version}`, {
          description:
            result.skipped.length > 0
              ? `${result.skipped.length} could not be applied because the resume text had changed.`
              : undefined,
        })
      } else {
        toast.warning('Nothing was applied', { description: 'The resume already had these changes.' })
      }
      onOpenChange(false)
    } catch (error) {
      if (isApiError(error) && error.status === 409 && error.code === 'stale_plan') {
        toast.warning('Your resume changed', {
          description: 'It was edited somewhere else. The suggestions were reloaded; review them and apply again.',
        })
        await planQuery.refetch()
        return
      }
      const details = isApiError(error) ? (error.details as { id?: unknown } | undefined) : undefined
      if (isApiError(error) && error.status === 422 && details && typeof details.id === 'string') {
        setErrors({ [details.id]: error.message })
        document
          .querySelector(`[data-change-id="${CSS.escape(details.id)}"]`)
          ?.scrollIntoView({ block: 'center', behavior: 'smooth' })
        return
      }
      setFormError(errorMessage(error))
    }
  }

  const renderRows = (rows: ResumeApplicableChange[]) => (
    <ul className="space-y-2">
      {rows.map((change) => (
        <ChangeRow
          key={change.id}
          change={change}
          checked={selected.has(change.id)}
          text={textOf(change)}
          error={errors[change.id]}
          disabled={saving}
          onCheckedChange={(checked) => toggle(change.id, checked)}
          onTextChange={(text) => editText(change.id, text)}
        />
      ))}
    </ul>
  )

  return (
    <Dialog open={open} onOpenChange={(next) => (saving ? undefined : onOpenChange(next))}>
      <DialogContent className="flex max-h-[90vh] max-w-2xl flex-col gap-0 p-0">
        <DialogHeader className="border-b border-border p-6 pb-4 pr-12">
          <DialogTitle className="flex items-center gap-2">
            <Wand2 className="size-5 text-primary" aria-hidden />
            Apply suggestions
          </DialogTitle>
          <DialogDescription>
            Changes are saved as a new version of the resume data used for matching and autofill. Your uploaded
            file is not changed. Only tick what is true of you.
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-6">
          {planQuery.isLoading ? (
            <SkeletonRegion label="Loading suggestions" className="space-y-2">
              {/* The "Ready to apply" heading and its checkbox rows. */}
              <SkeletonLine size="xs" className="w-32" />
              <ul className="space-y-2" aria-hidden>
                {[0, 1, 2].map((index) => (
                  <li key={index} className="rounded-md border border-border p-3">
                    <div className="flex items-start gap-3">
                      <Skeleton className="mt-0.5 size-4 shrink-0 rounded" />
                      <div className="min-w-0 flex-1 space-y-2">
                        <div className="flex h-[22px] items-center gap-2">
                          <Skeleton className="h-3.5 w-48 max-w-[60%]" />
                          <Skeleton className="h-[22px] w-24 rounded-full" />
                        </div>
                        <SkeletonLine size="sm" className={index === 1 ? 'w-1/2' : 'w-4/5'} />
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </SkeletonRegion>
          ) : planQuery.error ? (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage(planQuery.error)}</AlertDescription>
            </Alert>
          ) : changes.length === 0 ? (
            <p className="text-sm text-muted-foreground">There is nothing the app can apply for you right now.</p>
          ) : null}

          {formError ? (
            <Alert variant="destructive">
              <AlertDescription>{formError}</AlertDescription>
            </Alert>
          ) : null}

          {ready.length > 0 ? (
            <section className="space-y-2" aria-label="Ready to apply">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Ready to apply ({ready.length})
              </h3>
              {renderRows(ready)}
            </section>
          ) : null}

          {confirm.length > 0 ? (
            <section className="space-y-2" aria-label="Confirm first">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Confirm first ({confirm.length})
              </h3>
              <p className="text-xs text-muted-foreground">
                These need your word: tick a skill only if you have used it, and replace any bracketed part with
                your real result.
              </p>
              {renderRows(confirm)}
            </section>
          ) : null}

          <ManualList items={plan?.manual ?? []} />
        </div>

        <DialogFooter className="flex-col gap-3 border-t border-border p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={selectAll} disabled={saving || changes.length === 0}>
              Select all
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => setSelected(new Set())} disabled={saving}>
              Clear
            </Button>
            <span className="text-xs text-muted-foreground tabular-nums">
              {effective.length} selected
              {projectedGain > 0 ? ` · +${formatGain(projectedGain)} avg match (est.)` : ''}
            </span>
          </div>
          <Button type="button" onClick={() => void submit()} disabled={effective.length === 0 || saving} loading={saving}>
            {`Apply ${effective.length} ${effective.length === 1 ? 'change' : 'changes'} and save`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Changes that are safe to apply without asking: pre-selected, no confirmation, nothing to fill in. */
export function safeChanges(plan: ResumeApplyPlan | undefined): ResumeApplicableChange[] {
  return (plan?.changes ?? []).filter(
    (change) => change.selected_by_default && !change.requires_confirmation && !change.has_placeholders,
  )
}

/**
 * Always-visible actions: one click applies every safe change and saves a new version (with
 * Undo); "Review" opens the dialog for changes that need the candidate's confirmation.
 */
export function ApplySuggestionsButton({
  safeCount,
  reviewCount,
  applying,
  onApply,
  onReview,
}: {
  safeCount: number
  reviewCount: number
  applying: boolean
  onApply: () => void
  onReview: () => void
}) {
  const disabledReason =
    safeCount > 0
      ? undefined
      : reviewCount > 0
        ? 'Nothing is safe to apply automatically. Use Review to confirm the remaining suggestions.'
        : 'Nothing to apply automatically. The suggestions below need your own edits.'
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span title={disabledReason}>
        <Button size="sm" onClick={onApply} disabled={safeCount === 0 || applying} loading={applying}>
          <Wand2 aria-hidden />
          Apply suggestions
          {safeCount > 0 ? (
            <span className="ml-0.5 rounded-full bg-primary-foreground/20 px-1.5 text-xs tabular-nums">{safeCount}</span>
          ) : null}
        </Button>
      </span>
      {reviewCount > 0 ? (
        <Button size="sm" variant="outline" onClick={onReview} disabled={applying}>
          Review
          <span className="ml-0.5 rounded-full bg-muted px-1.5 text-xs tabular-nums text-muted-foreground">{reviewCount}</span>
        </Button>
      ) : null}
    </div>
  )
}
