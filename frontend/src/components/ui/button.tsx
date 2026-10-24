import { Slot } from '@radix-ui/react-slot'
import { type VariantProps, cva } from 'class-variance-authority'
import { Loader2 } from 'lucide-react'
import * as React from 'react'

import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium transition-[color,background-color,background-position,border-color,box-shadow,opacity,transform] duration-200 ease-out active:scale-[0.98] motion-reduce:active:scale-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        /** The primary action: the brand gradient (white copy >= 6:1 on every stop), a soft
            inner highlight, and a glow + gradient shift on hover. One per view. */
        default:
          'bg-gradient-brand bg-[length:180%_100%] bg-left text-gradient-foreground [box-shadow:inset_0_1px_0_0_hsl(var(--gradient-foreground)/0.18),0_1px_2px_0_hsl(var(--shadow-color)/0.12)] hover:bg-right hover:shadow-glow',
        /** Solid indigo, for places that want the old flat primary (dense toolbars). */
        solid: 'bg-primary text-primary-foreground shadow-xs hover:bg-primary/90 active:bg-primary/85',
        destructive: 'bg-destructive text-destructive-foreground shadow-xs hover:bg-destructive/90 active:bg-destructive/85',
        success: 'bg-success text-success-foreground shadow-xs hover:bg-success/90 active:bg-success/85',
        outline:
          'border border-input/45 bg-card text-foreground shadow-xs hover:border-primary/40 hover:bg-accent hover:text-accent-foreground dark:shadow-highlight',
        secondary: 'bg-secondary text-secondary-foreground hover:bg-surface-3',
        /** Tinted primary: the second-most-important action beside a solid one. */
        soft: 'bg-primary/10 text-primary hover:bg-primary/15',
        ghost: 'hover:bg-accent hover:text-accent-foreground',
        link: 'text-primary underline-offset-4 hover:underline',
      },
      size: {
        /* Control heights: 32 / 36 / 40 px. */
        default: 'h-9 px-4 py-2',
        sm: 'h-8 rounded-md px-3 text-xs',
        lg: 'h-11 rounded-xl px-6 text-[0.9375rem]',
        icon: 'h-9 w-9',
        'icon-sm': 'h-8 w-8 rounded-md',
        'icon-lg': 'h-10 w-10',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  /** Render the single child element with button styling (e.g. a react-router `<Link>`). */
  asChild?: boolean
  /** Shows a spinner and disables the button. Ignored when `asChild` is set. */
  loading?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, loading = false, disabled, children, ...props }, ref) => {
    // Radix `Slot` accepts exactly one child, so the spinner slot only exists for real buttons.
    if (asChild) {
      return (
        <Slot className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props}>
          {children}
        </Slot>
      )
    }

    return (
      <button
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        disabled={disabled || loading}
        {...props}
      >
        {loading ? <Loader2 className="animate-spin" aria-hidden /> : null}
        {children}
      </button>
    )
  },
)
Button.displayName = 'Button'

export { Button, buttonVariants }
