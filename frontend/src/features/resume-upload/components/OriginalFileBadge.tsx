import { FileCheck2 } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

/** "Original file": this resume carries the user's own uploaded file, kept as-is. */
export function OriginalFileBadge({ className }: { className?: string }) {
  return (
    <Badge variant="success" className={cn('gap-1 font-medium', className)} title="Your uploaded file, kept exactly as you uploaded it">
      <FileCheck2 className="size-3" aria-hidden />
      Original file
    </Badge>
  )
}
