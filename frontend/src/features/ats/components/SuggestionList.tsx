import { Bot, Check, ChevronDown, EyeOff, Pencil, RotateCcw, ShieldCheck, Wand2 } from 'lucide-react'
import * as React from 'react'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { toast } from '@/components/ui/toaster'
import { errorMessage, isApiError } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useApplySuggestions, useIgnoreSuggestions } from '@/features/ats/api'
import { SUGGESTION_KIND_LABELS } from '@/features/ats/labels'
import type { ApplyResult, AtsAnalysis, Suggestion } from '@/features/ats/types'
import { WordDiff } from '@/features/ats/components/WordDiff'

const PLACEHOLDER_RE = /\[[^[\]]*\]/

function editable(s: Suggestion): boolean {
  return s.kind === 'REPLACE_BULLET' || s.kind === 'REPLACE_SUMMARY' || s.kind === 'ADD_KEYWORD_CONTEXT'
}

function gainLabel(gain: number): string | null {
  if (gain <= 0) return null
  const rounded = Math.round(gain * 10) / 10
  return `+${Number.isInteger(rounded) ? rounded : rounded.toFixed(1)} est.`
}

function SuggestionPreview({ suggestion }: { suggestion: Suggestion }) {
  if (suggestion.kind === 'ADD_SKILL') {
    return (
      <p className="text-sm">
        Skills: <ins className="rounded bg-success/15 px-1.5 font-medium no-underline">+ {suggestion.after}</ins>
      </p>
    )
  }
  if (suggestion.kind === 'REORDER_SECTION') {
    return (
      <div className="space-y-1 text-xs">
        <p className="text-muted-foreground">
          <span className="font-semibold uppercase tracking-wide">Now </span>
          {suggestion.before}
        </p>
        <p>
          <span className="font-semibold uppercase tracking-wide text-success">After </span>
          {suggestion.after}
        </p>
      </div>
    )
  }
  if (suggestion.kind === 'MANUAL') return null
  return <WordDiff before={suggestion.before} after={suggestion.after} />
}

interface RowProps {
  suggestion: Suggestion
  busy: boolean
  readOnly: boolean
  onApply: (suggestion: Suggestion, text?: string) => void
  onIgnore: (suggestion: Suggestion, ignore: boolean) => void
}

function SuggestionRow({ suggestion, busy, readOnly, onApply, onIgnore }: RowProps) {
  const [editing, setEditing] = React.useState(false)
  const [text, setText] = React.useState(suggestion.after ?? suggestion.before ?? '')
  const needsWords = editable(suggestion) && !suggestion.after
  const handled = suggestion.status !== 'PROPOSED'
  const gain = gainLabel(suggestion.estimated_gain)
  const aiPolished = Boolean(suggestion.checks?.ai_polished)
  const placeholder = PLACEHOLDER_RE.test(text)

  React.useEffect(() => {
    setText(suggestion.after ?? suggestion.before ?? '')
  }, [suggestion.after, suggestion.before])

  return (
    <li
      className={cn('rounded-lg border border-border p-3', handled && 'opacity-75', suggestion.safe && !handled && 'border-success/30')}
      data-suggestion-id={suggestion.id}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{suggestion.title}</span>
        <Badge variant="outline">{SUGGESTION_KIND_LABELS[suggestion.kind]}</Badge>
        {suggestion.safe ? (
          <Badge variant="success" title="Uses only facts from your resume or profile">
            <ShieldCheck aria-hidden />
            Safe
          </Badge>
        ) : null}
        {aiPolished ? (
          <Badge variant="secondary" title="Rewritten by the AI model, checked by JobPilot's rules">
            <Bot aria-hidden />
            AI suggestion
          </Badge>
        ) : null}
        {gain ? <Badge variant="muted">{gain}</Badge> : null}
        {suggestion.status === 'APPLIED' ? <Badge variant="success">Applied v{suggestion.applied_version}</Badge> : null}
        {suggestion.status === 'EDITED' ? <Badge variant="success">Applied with your edit</Badge> : null}
        {suggestion.status === 'IGNORED' ? <Badge variant="muted">Ignored</Badge> : null}
      </div>
      <p className="mt-1 text-sm text-muted-foreground">{suggestion.rationale}</p>
      <div className="mt-2">
        <SuggestionPreview suggestion={suggestion} />
      </div>
      {editing ? (
        <div className="mt-2 space-y-1.5">
          <Textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={suggestion.kind === 'REPLACE_BULLET' ? 2 : 4}
            aria-label={`Edit: ${suggestion.title}`}
            className="text-sm"
          />
          <p className={cn('text-xs', placeholder ? 'text-warning' : 'text-muted-foreground')}>
            {placeholder
              ? 'Replace the bracketed part with your real result.'
              : 'Your words are saved as your own edit. Only state what is true; numbers in a summary must already be on your resume.'}
          </p>
        </div>
      ) : null}
      {!readOnly && !handled ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {suggestion.kind !== 'MANUAL' ? (
            editing ? (
              <Button size="sm" onClick={() => onApply(suggestion, text)} disabled={busy || !text.trim() || placeholder} loading={busy}>
                <Check aria-hidden />
                Apply my version
              </Button>
            ) : needsWords ? null : (
              <Button size="sm" variant={suggestion.safe ? 'default' : 'outline'} onClick={() => onApply(suggestion)} disabled={busy}>
                <Check aria-hidden />
                {suggestion.confirmation_label ? `${suggestion.confirmation_label} — add it` : 'Apply'}
              </Button>
            )
          ) : null}
          {editable(suggestion) ? (
            <Button size="sm" variant="ghost" onClick={() => setEditing((value) => !value)} disabled={busy}>
              <Pencil aria-hidden />
              {editing ? 'Cancel edit' : needsWords ? 'Write it' : 'Edit'}
            </Button>
          ) : null}
          <Button size="sm" variant="ghost" onClick={() => onIgnore(suggestion, true)} disabled={busy}>
            <EyeOff aria-hidden />
            {suggestion.kind === 'MANUAL' ? 'Dismiss' : 'Ignore'}
          </Button>
        </div>
      ) : null}
      {!readOnly && suggestion.status === 'IGNORED' ? (
        <Button size="sm" variant="ghost" className="mt-2" onClick={() => onIgnore(suggestion, false)} disabled={busy}>
          <RotateCcw aria-hidden />
          Restore
        </Button>
      ) : null}
    </li>
  )
}

function Section({ title, hint, items, children, defaultOpen = true }: { title: string; hint?: string; items: number; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = React.useState(defaultOpen)
  const id = React.useId()
  if (items === 0) return null
  return (
    <section className="space-y-2">
      <button
        type="button"
        className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground hover:text-foreground"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((value) => !value)}
      >
        <ChevronDown className={cn('size-3.5 transition-transform', !open && '-rotate-90')} aria-hidden />
        {title} ({items})
      </button>
      {open ? (
        <div id={id} className="space-y-2">
          {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
          <ul className="space-y-2">{children}</ul>
        </div>
      ) : null}
    </section>
  )
}

/* ------------------------------------------------------------------ apply all safe */

function ApplyAllDialog({
  open,
  onOpenChange,
  analysis,
  onApply,
  busy,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  analysis: AtsAnalysis
  onApply: (ids: string[]) => Promise<void>
  busy: boolean
}) {
  const safe = analysis.suggestions.filter((s) => s.status === 'PROPOSED' && s.safe && s.after)
  const confirm = analysis.suggestions.filter((s) => s.status === 'PROPOSED' && s.requires_confirmation)
  const [selected, setSelected] = React.useState<Set<string>>(new Set())
  const key = `${analysis.id}:${safe.map((s) => s.id).join(',')}`
  React.useEffect(() => {
    if (open) setSelected(new Set(safe.map((s) => s.id)))
    // the key captures the inputs
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, key])

  const toggle = (id: string, checked: boolean) =>
    setSelected((previous) => {
      const next = new Set(previous)
      if (checked) next.add(id)
      else next.delete(id)
      return next
    })

  const row = (s: Suggestion) => (
    <li key={s.id} className={cn('rounded-md border border-border p-3', selected.has(s.id) && 'border-primary/50 bg-primary/5')}>
      <label className="flex cursor-pointer items-start gap-3">
        <Checkbox className="mt-0.5" checked={selected.has(s.id)} onCheckedChange={(value) => toggle(s.id, value === true)} disabled={busy} />
        <span className="min-w-0 flex-1 space-y-1.5">
          <span className="block text-sm font-medium">{s.confirmation_label ?? s.title}</span>
          {s.confirmation_label ? <span className="block text-xs text-muted-foreground">{s.rationale}</span> : null}
          <SuggestionPreview suggestion={s} />
        </span>
      </label>
    </li>
  )

  return (
    <Dialog open={open} onOpenChange={(next) => (busy ? undefined : onOpenChange(next))}>
      <DialogContent className="flex max-h-[90vh] max-w-2xl flex-col gap-0 p-0">
        <DialogHeader className="border-b border-border p-6 pb-4 pr-12">
          <DialogTitle className="flex items-center gap-2">
            <Wand2 className="size-5 text-primary" aria-hidden />
            Apply safe suggestions
          </DialogTitle>
          <DialogDescription>
            Safe changes use only facts already on your resume or profile, and start ticked. Skills you have not shown
            anywhere start unticked: tick one only if you have really used it. Everything is saved as a new version; the
            current one stays in the history.
          </DialogDescription>
        </DialogHeader>
        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-6">
          {safe.length > 0 ? (
            <section className="space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Safe ({safe.length})</h3>
              <ul className="space-y-2">{safe.map(row)}</ul>
            </section>
          ) : (
            <p className="text-sm text-muted-foreground">Nothing is safe to apply automatically.</p>
          )}
          {confirm.length > 0 ? (
            <section className="space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Confirm first ({confirm.length})</h3>
              <ul className="space-y-2">{confirm.map(row)}</ul>
            </section>
          ) : null}
        </div>
        <DialogFooter className="border-t border-border p-4">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={() => void onApply([...selected])} disabled={selected.size === 0 || busy} loading={busy}>
            {`Apply ${selected.size} and re-analyse`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/* ------------------------------------------------------------------ list */

export interface SuggestionListProps {
  analysis: AtsAnalysis
  /** False when the resume has a newer version than the one analysed. */
  readOnly?: boolean
  onApplied: (result: ApplyResult) => void
}

export function SuggestionList({ analysis, readOnly = false, onApplied }: SuggestionListProps) {
  const apply = useApplySuggestions(analysis.id)
  const ignore = useIgnoreSuggestions(analysis.id)
  const [dialogOpen, setDialogOpen] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const busy = apply.isPending || ignore.isPending

  const proposed = analysis.suggestions.filter((s) => s.status === 'PROPOSED')
  const ready = proposed.filter((s) => s.safe && s.after && s.kind !== 'MANUAL')
  const confirm = proposed.filter((s) => s.requires_confirmation)
  const words = proposed.filter((s) => !s.safe && !s.requires_confirmation && s.kind !== 'MANUAL')
  const manual = proposed.filter((s) => s.kind === 'MANUAL')
  const handled = analysis.suggestions.filter((s) => s.status !== 'PROPOSED')

  const run = async (ids: string[], edits?: Record<string, string>) => {
    setError(null)
    try {
      const result = await apply.mutateAsync({ suggestion_ids: ids, edits })
      setDialogOpen(false)
      onApplied(result)
    } catch (err) {
      if (isApiError(err) && err.status === 409) {
        toast.warning('Your resume changed', { description: 'Run the analysis again to get fresh suggestions.' })
        return
      }
      const details = isApiError(err) ? (err.details as { id?: string } | undefined) : undefined
      if (details?.id) {
        document.querySelector(`[data-suggestion-id="${CSS.escape(details.id)}"]`)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
      }
      setError(errorMessage(err))
      toast.error('Could not apply', { description: errorMessage(err) })
    }
  }

  const onApply = (s: Suggestion, text?: string) => void run([s.id], text !== undefined ? { [s.id]: text } : undefined)
  const onIgnore = (s: Suggestion, value: boolean) =>
    void ignore.mutateAsync({ suggestion_ids: [s.id], ignore: value }).catch((err) => toast.error('Could not update', { description: errorMessage(err) }))

  const rows = (items: Suggestion[]) =>
    items.map((s) => <SuggestionRow key={s.id} suggestion={s} busy={busy} readOnly={readOnly} onApply={onApply} onIgnore={onIgnore} />)

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          {ready.length} safe · {confirm.length} to confirm · {words.length} need your words · {manual.length} for you to act on
        </p>
        {!readOnly ? (
          <Button size="sm" onClick={() => setDialogOpen(true)} disabled={busy || (ready.length === 0 && confirm.length === 0)}>
            <Wand2 aria-hidden />
            Apply all safe
            {ready.length ? <span className="ml-0.5 rounded-full bg-primary-foreground/20 px-1.5 text-xs tabular-nums">{ready.length}</span> : null}
          </Button>
        ) : null}
      </div>
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {readOnly ? (
        <Alert>
          <AlertDescription>This analysis is of an older version of the resume. Run it again to apply suggestions.</AlertDescription>
        </Alert>
      ) : null}
      <Section title="Ready to apply" hint="Built only from facts on your resume or profile." items={ready.length}>
        {rows(ready)}
      </Section>
      <Section title="Confirm first" hint="The posting asks for these and nothing on your resume shows them. Add one only if it is true." items={confirm.length}>
        {rows(confirm)}
      </Section>
      <Section title="Needs your words" hint="JobPilot will not invent results or claims: write these yourself." items={words.length}>
        {rows(words)}
      </Section>
      <Section title="For you to act on" items={manual.length}>
        {rows(manual)}
      </Section>
      <Section title="Handled" items={handled.length} defaultOpen={false}>
        {rows(handled)}
      </Section>
      <ApplyAllDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        analysis={analysis}
        busy={apply.isPending}
        onApply={(ids) => run(ids)}
      />
    </div>
  )
}
