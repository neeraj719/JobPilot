import * as React from 'react'

import { cn } from '@/lib/utils'

export interface PageContainerProps extends React.HTMLAttributes<HTMLDivElement> {
  /** `default` caps at ~1400px; `wide` fills the shell; `narrow` suits forms. */
  width?: 'narrow' | 'default' | 'wide'
}

/** Consistent page gutters and max width for everything rendered inside the AppShell. */
export function PageContainer({ className, width = 'default', children, ...props }: PageContainerProps) {
  return (
    <div
      className={cn(
        'mx-auto w-full space-y-6 px-4 py-6 sm:px-6 lg:px-8',
        width === 'narrow' && 'max-w-3xl',
        width === 'default' && 'max-w-[1400px]',
        className,
      )}
      {...props}
    >
      {children}
    </div>
  )
}
