import * as React from 'react'

import { cn } from '@/lib/utils'

/**
 * Surfaces (v2):
 * - `default` hairline card, 16 px radius, faint shadow (+ inner highlight on dark).
 * - `glass` translucent + blur — only for panels that float over imagery or the hero.
 * - `gradient` 1 px brand-gradient border (the active / featured item).
 * - `soft` the soft brand gradient panel with a soft gradient border (AI content).
 */
const CARD_VARIANTS = {
  default: 'border border-border bg-card shadow-xs dark:shadow-highlight',
  glass: 'glass border border-border/70 shadow-lg dark:border-glass-border/40',
  gradient: 'border-gradient shadow-sm dark:shadow-highlight',
  soft: 'border-gradient-soft',
} as const

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: keyof typeof CARD_VARIANTS
}

const Card = React.forwardRef<HTMLDivElement, CardProps>(({ className, variant = 'default', ...props }, ref) => (
  // min-w-0: a card is usually a grid / flex child; without it, one long unbreakable line inside
  // (a pill row, a 'Role · Company' line) widens the track and the page scrolls sideways.
  <div ref={ref} className={cn('min-w-0 rounded-xl text-card-foreground', CARD_VARIANTS[variant], className)} {...props} />
))
Card.displayName = 'Card'

const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('flex flex-col space-y-1.5 p-6', className)} {...props} />
  ),
)
CardHeader.displayName = 'CardHeader'

const CardTitle = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('font-display text-base font-semibold leading-tight tracking-tight', className)} {...props} />
  ),
)
CardTitle.displayName = 'CardTitle'

const CardDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <p ref={ref} className={cn('text-sm text-muted-foreground', className)} {...props} />
  ),
)
CardDescription.displayName = 'CardDescription'

const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => <div ref={ref} className={cn('p-6 pt-0', className)} {...props} />,
)
CardContent.displayName = 'CardContent'

const CardFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('flex items-center p-6 pt-0', className)} {...props} />
  ),
)
CardFooter.displayName = 'CardFooter'

export { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle }
