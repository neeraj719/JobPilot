import { ChevronDown, Download, FileText, FileType2 } from 'lucide-react'
import * as React from 'react'

import { Button, type ButtonProps } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { toast } from '@/components/ui/toaster'
import { errorMessage } from '@/lib/api'

import { exportResume } from '../api'
import type { ExportFormat } from '../types'

export interface ExportMenuProps {
  resume: { id: string; name: string }
  template?: string
  version?: number
  size?: ButtonProps['size']
  variant?: ButtonProps['variant']
  /** Called before exporting (e.g. the editor saves its draft as a version first). */
  beforeExport?: () => Promise<void> | void
  label?: string
}

/** PDF / DOCX download rendered on the server from the structured data. */
export function ExportMenu({ resume, template, version, size = 'sm', variant = 'outline', beforeExport, label = 'Export' }: ExportMenuProps) {
  const [busy, setBusy] = React.useState<ExportFormat | null>(null)

  const run = async (format: ExportFormat) => {
    setBusy(format)
    try {
      await beforeExport?.()
      await exportResume(resume, format, { template, version })
      toast.success(`${format.toUpperCase()} downloaded`, {
        description: 'ATS-friendly: one column, real headings and bullet lists, selectable text.',
      })
    } catch (error) {
      toast.error(`Could not export the ${format.toUpperCase()}`, { description: errorMessage(error) })
    } finally {
      setBusy(null)
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size={size} variant={variant} loading={busy !== null}>
          <Download aria-hidden />
          {label}
          <ChevronDown aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
          {version ? `Version ${version}` : 'Latest saved version'}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void run('pdf')}>
          <FileText aria-hidden />
          PDF
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void run('docx')}>
          <FileType2 aria-hidden />
          Word (DOCX)
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
