import { type VariantProps, cva } from 'class-variance-authority'
import * as React from 'react'

import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 [&_svg]:size-3 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        default: 'border-transparent bg-primary text-primary-foreground',
        secondary: 'border-transparent bg-secondary text-secondary-foreground',
        /* Status badges are soft (tint + darker text of the same hue): colour used sparingly. */
        destructive: 'border-destructive/20 bg-destructive-soft text-destructive-soft-foreground',
        success: 'border-success/20 bg-success-soft text-success-soft-foreground',
        warning: 'border-warning/25 bg-warning-soft text-warning-soft-foreground',
        info: 'border-info/20 bg-info-soft text-info-soft-foreground',
        primary: 'border-primary/20 bg-primary/10 text-primary',
        outline: 'border-border text-foreground',
        muted: 'border-transparent bg-muted text-muted-foreground',
        /* Solid status fills, for the rare case that needs the strongest emphasis. */
        'destructive-solid': 'border-transparent bg-destructive text-destructive-foreground',
        'success-solid': 'border-transparent bg-success text-success-foreground',
        'warning-solid': 'border-transparent bg-warning text-warning-foreground',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge, badgeVariants }
