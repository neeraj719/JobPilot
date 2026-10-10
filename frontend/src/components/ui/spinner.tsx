import { Loader2 } from 'lucide-react'
import * as React from 'react'

import { cn } from '@/lib/utils'

const sizes = { sm: 'size-4', md: 'size-6', lg: 'size-8' } as const

export interface SpinnerProps extends React.HTMLAttributes<HTMLDivElement> {
  size?: keyof typeof sizes
  label?: string
}

export function Spinner({ className, size = 'md', label = 'Loading', ...props }: SpinnerProps) {
  return (
    <div role="status" aria-live="polite" className={cn('inline-flex items-center gap-2', className)} {...props}>
      <Loader2 className={cn('animate-spin text-muted-foreground', sizes[size])} aria-hidden />
      <span className="sr-only">{label}</span>
    </div>
  )
}
