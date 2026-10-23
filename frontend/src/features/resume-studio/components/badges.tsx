import { Archive, Bot, FilePlus2, FileUp, Settings2, Sparkles, Target, UserRound } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { SimpleTooltip } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { ResumeChangeSource, ResumeKind } from '@/types/api'

const KIND: Record<ResumeKind, { label: string; Icon: typeof FileUp; className: string }> = {
  UPLOADED: { label: 'Uploaded', Icon: FileUp, className: 'border-border text-muted-foreground' },
  CREATED: { label: 'Built', Icon: FilePlus2, className: 'border-primary/30 bg-primary/5 text-primary' },
  TAILORED: { label: 'Tailored', Icon: Target, className: 'border-info/30 bg-info/10 text-info' },
}

export function KindBadge({ kind, sourceName }: { kind: ResumeKind; sourceName?: string | null }) {
  const meta = KIND[kind] ?? KIND.UPLOADED
  const Icon = meta.Icon
  const label = kind === 'TAILORED' && sourceName ? `Tailored from ${sourceName}` : meta.label
  return (
    <Badge variant="outline" className={cn('gap-1 font-medium', meta.className)}>
      <Icon className="size-3" aria-hidden />
      <span className="max-w-[12rem] truncate">{label}</span>
    </Badge>
  )
}

export function ArchivedBadge() {
  return (
    <Badge variant="muted" className="gap-1">
      <Archive className="size-3" aria-hidden />
      Archived
    </Badge>
  )
}

const SOURCE: Record<ResumeChangeSource, { label: string; hint: string; Icon: typeof Bot; className: string }> = {
  USER: {
    label: 'You',
    hint: 'Edited by you',
    Icon: UserRound,
    className: 'border-border text-foreground',
  },
  AI: {
    label: 'AI',
    hint: 'Made by AI (a suggestion you applied, or AI tailoring). Review it before you send it anywhere.',
    Icon: Sparkles,
    className: 'border-ai/30 bg-ai-soft text-ai-soft-foreground',
  },
  SYSTEM: {
    label: 'System',
    hint: 'Made by JobPilot: an upload, import, re-parse, duplicate or restore',
    Icon: Settings2,
    className: 'border-border bg-muted text-muted-foreground',
  },
}

export function ChangeSourceBadge({ source }: { source: ResumeChangeSource }) {
  const meta = SOURCE[source] ?? SOURCE.USER
  const Icon = meta.Icon
  return (
    <SimpleTooltip label={meta.hint} side="top">
      <Badge variant="outline" className={cn('gap-1', meta.className)} tabIndex={0}>
        <Icon className="size-3" aria-hidden />
        {meta.label}
        <span className="sr-only">: {meta.hint}</span>
      </Badge>
    </SimpleTooltip>
  )
}
