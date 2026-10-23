import {
  CircleAlert,
  CircleCheck,
  Clock,
  Download,
  MoreVertical,
  Pencil,
  RefreshCw,
  Star,
  Trash2,
} from 'lucide-react'
import * as React from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { cn, formatDate } from '@/lib/utils'
import { formatBytes } from '@/features/resume/api'
import type { ResumeParseStatus, ResumeRead } from '@/types/api'
import { TargetRoleSelect } from '@/features/resume/components/TargetRoleSelect'

export interface ResumeCardProps {
  resume: ResumeRead
  selected: boolean
  busy: boolean
  onSelect: () => void
  onRename: (name: string) => void
  onRetarget: (role: string | null) => void
  onSetDefault: () => void
  onDownload: () => void
  onReparse: () => void
  onDelete: () => void
}

const PARSE_STATUS: Record<ResumeParseStatus, { label: string; className: string; Icon: typeof CircleCheck }> = {
  PARSED: { label: 'Parsed', className: 'bg-success/10 text-success border-success/25', Icon: CircleCheck },
  PENDING: { label: 'Pending', className: 'bg-warning/15 text-warning border-warning/25', Icon: Clock },
  FAILED: { label: 'Failed', className: 'bg-destructive/10 text-destructive border-destructive/25', Icon: CircleAlert },
}

export function ResumeCard({
  resume,
  selected,
  busy,
  onSelect,
  onRename,
  onRetarget,
  onSetDefault,
  onDownload,
  onReparse,
  onDelete,
}: ResumeCardProps) {
  const [editing, setEditing] = React.useState(false)
  const [draft, setDraft] = React.useState(resume.name)
  const status = PARSE_STATUS[resume.parse_status] ?? PARSE_STATUS.PENDING
  const StatusIcon = status.Icon

  React.useEffect(() => {
    setDraft(resume.name)
  }, [resume.name])

  const commitRename = () => {
    const next = draft.trim()
    setEditing(false)
    if (next && next !== resume.name) onRename(next)
    else setDraft(resume.name)
  }

  return (
    <Card
      className={cn(
        'transition-colors',
        selected ? 'border-primary ring-1 ring-primary/30' : 'hover:border-primary/40',
        busy && 'opacity-60',
      )}
    >
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-2">
          <button
            type="button"
            onClick={onSelect}
            className="min-w-0 flex-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            aria-pressed={selected}
          >
            {editing ? (
              <Input
                autoFocus
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onBlur={commitRename}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    commitRename()
                  }
                  if (event.key === 'Escape') {
                    setDraft(resume.name)
                    setEditing(false)
                  }
                }}
                onClick={(event) => event.stopPropagation()}
                aria-label="Resume name"
                className="h-8"
              />
            ) : (
              <h3 className="truncate text-sm font-semibold">{resume.name}</h3>
            )}
          </button>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${resume.name}`} disabled={busy}>
                <MoreVertical aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                onSelect={(event) => {
                  event.preventDefault()
                  setEditing(true)
                }}
              >
                <Pencil aria-hidden />
                Rename
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => onSetDefault()} disabled={resume.is_default}>
                <Star aria-hidden />
                Set as default
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => onDownload()}>
                <Download aria-hidden />
                Download
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => onReparse()}>
                <RefreshCw aria-hidden />
                Re-run extraction
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem destructive onSelect={() => onDelete()}>
                <Trash2 aria-hidden />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        <div className="flex items-center gap-2">
          <span className="shrink-0 text-xs text-muted-foreground">Target</span>
          <TargetRoleSelect
            size="sm"
            allowNone
            value={resume.target_role}
            onChange={onRetarget}
            disabled={busy}
            className="min-w-0 flex-1"
          />
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {resume.is_default ? (
            <Badge variant="default" className="gap-1">
              <Star aria-hidden />
              Default
            </Badge>
          ) : null}
          <span
            className={cn(
              'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium',
              status.className,
            )}
          >
            <StatusIcon className="size-3" aria-hidden />
            {status.label}
          </span>
          <Badge variant="outline">v{resume.current_version}</Badge>
        </div>

        {resume.parse_status === 'FAILED' && resume.parse_error ? (
          <p className="rounded-md bg-destructive/5 px-2 py-1.5 text-xs text-destructive">{resume.parse_error}</p>
        ) : null}

        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <div className="col-span-2 truncate">
            <dt className="sr-only">Original file</dt>
            <dd className="truncate" title={resume.original_filename ?? undefined}>
              {resume.original_filename ?? (resume.kind === 'TAILORED' ? 'Tailored copy' : 'Built in the editor')}
            </dd>
          </div>
          <div>
            <dt className="sr-only">Size</dt>
            <dd>{formatBytes(resume.size_bytes)}</dd>
          </div>
          <div className="text-right">
            <dt className="sr-only">Uploaded</dt>
            <dd>{formatDate(resume.created_at)}</dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  )
}
