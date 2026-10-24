import {
  Archive,
  ArchiveRestore,
  Copy,
  Crosshair,
  Download,
  FileText,
  FileType2,
  MoreVertical,
  PencilLine,
  PencilRuler,
  Star,
  Trash2,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn, formatRelative } from '@/lib/utils'

import type { ExportFormat, ResumeTemplate, StudioResumeRead } from '../types'
import { ArchivedBadge, KindBadge } from './badges'
import { ResumePreview } from './ResumePreview'

export interface StudioResumeCardProps {
  resume: StudioResumeRead
  sourceName?: string | null
  template?: ResumeTemplate
  busy?: boolean
  onRename: () => void
  onDuplicate: () => void
  onSetDefault: () => void
  onArchive: () => void
  onUnarchive: () => void
  onDelete: () => void
  onExport: (format: ExportFormat) => void
}

export function StudioResumeCard({
  resume,
  sourceName,
  template,
  busy,
  onRename,
  onDuplicate,
  onSetDefault,
  onArchive,
  onUnarchive,
  onDelete,
  onExport,
}: StudioResumeCardProps) {
  const archived = Boolean(resume.archived_at)
  const updated = resume.draft_saved_at && resume.draft_saved_at > resume.updated_at ? resume.draft_saved_at : resume.updated_at
  return (
    <Card className={cn('group flex flex-col overflow-hidden transition-colors hover:border-primary/40', busy && 'opacity-60', archived && 'opacity-80')}>
      <Link
        to={`/resume/my/${resume.id}`}
        className="relative block h-36 overflow-hidden border-b border-border bg-muted/60 px-4 pt-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
        aria-label={`Open ${resume.name}`}
      >
        {template && resume.parse_status === 'PARSED' ? (
          <div aria-hidden className="pointer-events-none">
            <ResumePreview data={resume.parsed_data} template={template} scale={0.3} bare />
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground" aria-hidden>
            <FileText className="size-10" />
          </div>
        )}
      </Link>
      <CardContent className="flex flex-1 flex-col gap-2 p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <Link to={`/resume/my/${resume.id}`} className="block truncate font-semibold hover:underline">
              {resume.name}
            </Link>
            <p className="truncate text-xs text-muted-foreground">{resume.target_role || 'No target role'}</p>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${resume.name}`} disabled={busy}>
                <MoreVertical aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52">
              <DropdownMenuItem asChild>
                <Link to={`/resume/my/${resume.id}/edit`}>
                  <PencilRuler aria-hidden /> Edit in editor
                </Link>
              </DropdownMenuItem>
              {!archived ? (
                <DropdownMenuItem asChild>
                  <Link to={`/resume/targets/new?resume=${resume.id}`}>
                    <Crosshair aria-hidden /> Optimize for a job
                  </Link>
                </DropdownMenuItem>
              ) : null}
              <DropdownMenuItem onSelect={onRename}>
                <PencilLine aria-hidden /> Rename
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={onDuplicate}>
                <Copy aria-hidden /> Duplicate
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={onSetDefault} disabled={resume.is_default || archived}>
                <Star aria-hidden /> Set as default
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">Export</DropdownMenuLabel>
              <DropdownMenuItem onSelect={() => onExport('pdf')}>
                <Download aria-hidden /> PDF
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => onExport('docx')}>
                <FileType2 aria-hidden /> Word (DOCX)
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              {archived ? (
                <DropdownMenuItem onSelect={onUnarchive}>
                  <ArchiveRestore aria-hidden /> Restore from archive
                </DropdownMenuItem>
              ) : (
                <DropdownMenuItem onSelect={onArchive}>
                  <Archive aria-hidden /> Archive
                </DropdownMenuItem>
              )}
              <DropdownMenuItem destructive onSelect={onDelete}>
                <Trash2 aria-hidden /> Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {resume.is_default ? (
            <Badge className="gap-1">
              <Star className="size-3" aria-hidden /> Default
            </Badge>
          ) : null}
          <KindBadge kind={resume.kind} sourceName={sourceName} />
          {archived ? <ArchivedBadge /> : null}
          <Badge variant="outline">v{resume.current_version}</Badge>
          {resume.draft_saved_at ? (
            <Badge variant="outline" className="border-warning/40 bg-warning/10 text-warning">
              Unsaved draft
            </Badge>
          ) : null}
        </div>
        <p className="mt-auto text-xs text-muted-foreground">Edited {formatRelative(updated)}</p>
      </CardContent>
    </Card>
  )
}
