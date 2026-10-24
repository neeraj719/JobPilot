import { Eye, EyeOff } from 'lucide-react'
import * as React from 'react'

import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

export interface PasswordInputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> {
  /** Controlled reveal, so two fields (password + confirm) can share one toggle. */
  revealed?: boolean
  onRevealedChange?: (revealed: boolean) => void
  /** Hide the eye button (the confirm field follows the first field's toggle). */
  showToggle?: boolean
}

/** Password field with the show / hide button used by the sign-in and sign-up forms. */
export const PasswordInput = React.forwardRef<HTMLInputElement, PasswordInputProps>(
  ({ className, revealed: revealedProp, onRevealedChange, showToggle = true, ...props }, ref) => {
    const [revealedState, setRevealedState] = React.useState(false)
    const revealed = revealedProp ?? revealedState
    const setRevealed = (value: boolean) => {
      if (onRevealedChange) onRevealedChange(value)
      else setRevealedState(value)
    }

    return (
      <div className="relative">
        {/* The toggle's padding goes last so a caller's `px-*` cannot remove it. */}
        <Input ref={ref} type={revealed ? 'text' : 'password'} className={cn(className, showToggle && 'pr-12')} {...props} />
        {showToggle ? (
          <button
            type="button"
            onClick={() => setRevealed(!revealed)}
            className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-md text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label={revealed ? 'Hide password' : 'Show password'}
            aria-pressed={revealed}
          >
            {revealed ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
          </button>
        ) : null}
      </div>
    )
  },
)
PasswordInput.displayName = 'PasswordInput'
