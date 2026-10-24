import { Check, ChevronDown, Copy, Sparkles, Wand2 } from 'lucide-react'
import * as React from 'react'

import { EmptyState } from '@/components/common/EmptyState'
import { Button } from '@/components/ui/button'
import { toast } from '@/components/ui/toaster'
import { cn } from '@/lib/utils'
import { formatApiDateTime } from '@/features/automation/datetime'
import { InterviewPrepSkeleton } from '@/features/interviews/components/InterviewSkeletons'
import { hasPrep, prepSections } from '@/features/interviews/helpers'
import type { InterviewPrep, InterviewRead } from '@/types/api'

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = React.useState(false)

  React.useEffect(() => {
    if (!copied) return
    const timer = window.setTimeout(() => setCopied(false), 1500)
    return () => window.clearTimeout(timer)
  }, [copied])

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-sm"
      aria-label={label}
      title={label}
      onClick={async () => {
        const ok = await copyText(text)
        if (ok) setCopied(true)
        else toast.error('Could not copy to the clipboard')
      }}
    >
      {copied ? <Check className="text-success" /> : <Copy />}
    </Button>
  )
}

function PrepSectionBlock({
  title,
  description,
  questions,
  defaultOpen,
}: {
  title: string
  description: string
  questions: string[]
  defaultOpen: boolean
}) {
  const [open, setOpen] = React.useState(defaultOpen)
  const contentId = React.useId()

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <div className="flex items-center gap-1 bg-muted/40 pr-2">
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-controls={contentId}
          className="flex min-w-0 flex-1 items-center gap-2 px-3 py-2.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
        >
          <ChevronDown className={cn('size-4 shrink-0 transition-transform', !open && '-rotate-90')} aria-hidden />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium">{title}</span>
            <span className="block truncate text-xs text-muted-foreground">{description}</span>
          </span>
          <span className="shrink-0 rounded-full bg-card px-2 py-0.5 text-xs tabular-nums text-muted-foreground">
            {questions.length}
          </span>
        </button>
        <CopyButton text={questions.map((question, index) => `${index + 1}. ${question}`).join('\n')} label={`Copy all ${title.toLowerCase()}`} />
      </div>

      {open ? (
        <ol id={contentId} className="divide-y divide-border/60">
          {questions.map((question, index) => (
            <li key={`${question}-${index}`} className="flex items-start gap-2 px-3 py-2">
              <span className="mt-0.5 w-5 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
                {index + 1}.
              </span>
              <p className="min-w-0 flex-1 text-sm leading-relaxed">{question}</p>
              <CopyButton text={question} label="Copy this question" />
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  )
}

export interface InterviewPrepPanelProps {
  interview: InterviewRead
  generating?: boolean
  onGenerate: () => void
}

/** The AI preparation sheet: five collapsible sections, each list copyable. */
export function InterviewPrepPanel({ interview, generating = false, onGenerate }: InterviewPrepPanelProps) {
  const sections = prepSections(interview)
  const ready = hasPrep(interview)
  const generatedAt = (interview.prep_material as InterviewPrep | undefined)?.generated_at

  if (generating && !ready) {
    return (
      <InterviewPrepSkeleton />
    )
  }

  if (!ready) {
    return (
      <EmptyState
        icon={Wand2}
        title="No preparation yet"
        description="Generate a tailored sheet: likely technical questions, behavioral prompts, what to know about the company, and the questions your own resume invites."
        action={
          <Button onClick={onGenerate} loading={generating}>
            <Sparkles />
            Generate preparation
          </Button>
        }
      />
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          {generatedAt ? `Generated ${formatApiDateTime(generatedAt)}` : 'Generated for this round'} ·{' '}
          {sections.reduce((total, section) => total + section.questions.length, 0)} questions
        </p>
        <Button variant="outline" size="sm" onClick={onGenerate} loading={generating}>
          <Sparkles />
          Regenerate
        </Button>
      </div>

      <div className="space-y-2">
        {sections.map((section, index) => (
          <PrepSectionBlock
            key={section.key}
            title={section.title}
            description={section.description}
            questions={section.questions}
            defaultOpen={index === 0}
          />
        ))}
      </div>
    </div>
  )
}
