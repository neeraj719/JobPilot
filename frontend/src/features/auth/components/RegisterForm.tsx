import { zodResolver } from '@hookform/resolvers/zod'
import { Check, Circle, UserPlus } from 'lucide-react'
import * as React from 'react'
import { type Control, useForm, useWatch } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { AUTH_FORM, AUTH_INPUT, AUTH_ITEM, AUTH_LABEL, AUTH_ROW_GAP, AUTH_SUBMIT } from '@/features/auth/components/authFormStyles'
import { PasswordInput } from '@/features/auth/components/PasswordInput'
import { StaySignedInField } from '@/features/auth/components/StaySignedInField'
import { usePostAuthRedirect } from '@/features/auth/usePostAuthRedirect'
import { errorMessage } from '@/lib/api'
import { offerToSavePassword } from '@/lib/credentials'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth'

/** The backend password policy (at least 8 characters, one letter, one digit), as a checklist. */
const REQUIREMENTS: { id: string; label: string; test: (value: string) => boolean }[] = [
  { id: 'length', label: 'At least 8 characters', test: (value) => value.length >= 8 },
  { id: 'letter', label: 'At least one letter', test: (value) => /[A-Za-z]/.test(value) },
  { id: 'digit', label: 'At least one digit', test: (value) => /\d/.test(value) },
]

// Mirrors the backend password policy: at least 8 chars, one letter and one digit.
export const registerSchema = z
  .object({
    first_name: z.string().trim().min(1, 'Tell us your first name').max(60, 'That name is too long'),
    last_name: z.string().trim().max(60, 'That name is too long'),
    email: z.string().min(1, 'Email is required').email('Enter a valid email address'),
    password: z
      .string()
      .min(8, 'Use at least 8 characters')
      .regex(/[A-Za-z]/, 'Include at least one letter')
      .regex(/\d/, 'Include at least one digit'),
    confirm_password: z.string().min(1, 'Confirm your password'),
    /** "Stay signed in on this device", as on the sign-in form. */
    remember_me: z.boolean(),
  })
  .refine((values) => values.password === values.confirm_password, {
    message: 'Passwords do not match',
    path: ['confirm_password'],
  })

export type RegisterValues = z.infer<typeof registerSchema>

/** 0 empty · 1 weak · 2 fair · 3 good (policy met) · 4 strong (policy + 12 chars or mixed case and a symbol). */
function passwordScore(value: string): number {
  if (!value) return 0
  const met = REQUIREMENTS.filter((rule) => rule.test(value)).length
  if (met < REQUIREMENTS.length) return Math.max(1, met)
  const extra = value.length >= 12 || (/[a-z]/.test(value) && /[A-Z]/.test(value) && /[^A-Za-z0-9]/.test(value))
  return extra ? 4 : 3
}

const SCORE_COPY = ['', 'Weak', 'Fair', 'Good', 'Strong'] as const
const SCORE_BAR = ['bg-muted', 'bg-destructive', 'bg-warning', 'bg-success', 'bg-success'] as const
const SCORE_TEXT = ['text-muted-foreground', 'text-destructive', 'text-warning', 'text-success', 'text-success'] as const

/**
 * Strength meter + requirement list under the password field. Subscribes to the password alone
 * (`useWatch`), so typing re-renders this block, not the whole form.
 */
function PasswordStrength({ control }: { control: Control<RegisterValues> }) {
  const value = useWatch({ control, name: 'password' }) ?? ''
  const score = passwordScore(value)
  return (
    <div className="space-y-2.5 pt-0.5 [@media(min-height:801px)_and_(max-height:900px)]:space-y-1.5 [@media(min-height:801px)_and_(max-height:900px)]:pt-0" id="register-password-strength">
      <div className="flex items-center gap-3">
        <div
          role="meter"
          aria-label="Password strength"
          aria-valuemin={0}
          aria-valuemax={4}
          aria-valuenow={score}
          aria-valuetext={SCORE_COPY[score] || 'No password yet'}
          className="grid flex-1 grid-cols-4 gap-1.5"
        >
          {[1, 2, 3, 4].map((step) => (
            <span key={step} className={cn('h-1.5 rounded-full transition-colors duration-200', step <= score ? SCORE_BAR[score] : 'bg-muted')} />
          ))}
        </div>
        <span aria-live="polite" className={cn('w-14 shrink-0 text-right text-sm font-medium', SCORE_TEXT[score])}>
          {SCORE_COPY[score]}
        </span>
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-sm" aria-label="Password requirements">
        {REQUIREMENTS.map((rule) => {
          const met = rule.test(value)
          return (
            <li key={rule.id} className={cn('flex items-center gap-1.5 whitespace-nowrap', met ? 'text-success' : 'text-muted-foreground')}>
              {met ? <Check className="size-4 shrink-0" aria-hidden /> : <Circle className="size-3.5 shrink-0" aria-hidden />}
              <span>{rule.label}</span>
              <span className="sr-only">{met ? '(met)' : '(not met yet)'}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

/**
 * The one sign-up form: used by `/register` and by the landing page's modal. Same routing
 * as sign-in (deep link → else /home; several roles → /choose-role). First + last name sit
 * side by side from 768 px; everything else spans the form column.
 */
export function RegisterForm({ autoFocus = true }: { autoFocus?: boolean; /** @deprecated the layout is the same everywhere now */ wide?: boolean }) {
  const navigate = useNavigate()
  const register = useAuthStore((state) => state.register)
  const { from, redirectTo, redirectState } = usePostAuthRedirect()
  const [showPassword, setShowPassword] = React.useState(false)

  const form = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { first_name: '', last_name: '', email: '', password: '', confirm_password: '', remember_me: false },
  })

  async function onSubmit(values: RegisterValues) {
    const fullName = [values.first_name, values.last_name].map((part) => part.trim()).filter(Boolean).join(' ')
    try {
      const outcome = await register(fullName, values.email, values.password, values.remember_me)
      // New credentials accepted: let the browser's password manager offer to save them.
      offerToSavePassword({ email: values.email, password: values.password, name: fullName })
      form.resetField('password')
      form.resetField('confirm_password')
      if (outcome.status === 'role_selection') {
        navigate('/choose-role', { replace: true, state: { from: from ?? undefined } })
        return
      }
      const { user } = outcome
      toast.success('Account created', { description: `Welcome aboard, ${user.full_name || user.email}.` })
      navigate(redirectTo, { replace: true, state: redirectState })
    } catch (error) {
      toast.error('Could not create your account', { description: errorMessage(error) })
      form.setError('email', { message: errorMessage(error, 'Registration failed') })
    }
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className={AUTH_FORM} noValidate>
        <div className={cn('grid items-start md:grid-cols-2', AUTH_ROW_GAP)}>
          <FormField
            control={form.control}
            name="first_name"
            render={({ field }) => (
              <FormItem className={AUTH_ITEM}>
                <FormLabel className={AUTH_LABEL}>First name</FormLabel>
                <FormControl>
                  <Input autoComplete="given-name" placeholder="Ada" autoFocus={autoFocus} className={AUTH_INPUT} {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="last_name"
            render={({ field }) => (
              <FormItem className={AUTH_ITEM}>
                <FormLabel className={AUTH_LABEL}>
                  Last name <span className="font-normal text-muted-foreground">(optional)</span>
                </FormLabel>
                <FormControl>
                  <Input autoComplete="family-name" placeholder="Lovelace" className={AUTH_INPUT} {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem className={AUTH_ITEM}>
              <FormLabel className={AUTH_LABEL}>Email</FormLabel>
              <FormControl>
                <Input type="email" autoComplete="email" placeholder="you@example.com" className={AUTH_INPUT} {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="password"
          render={({ field }) => (
            <FormItem className={AUTH_ITEM}>
              <FormLabel className={AUTH_LABEL}>Password</FormLabel>
              <FormControl>
                <PasswordInput
                  autoComplete="new-password"
                  placeholder="At least 8 characters"
                  revealed={showPassword}
                  onRevealedChange={setShowPassword}
                  aria-describedby="register-password-strength"
                  className={AUTH_INPUT}
                  {...field}
                />
              </FormControl>
              <PasswordStrength control={form.control} />
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="confirm_password"
          render={({ field }) => (
            <FormItem className={AUTH_ITEM}>
              <FormLabel className={AUTH_LABEL}>Confirm password</FormLabel>
              <FormControl>
                <PasswordInput
                  autoComplete="new-password"
                  placeholder="Repeat your password"
                  revealed={showPassword}
                  showToggle={false}
                  className={AUTH_INPUT}
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <StaySignedInField control={form.control} />

        <div className="space-y-3 [@media(min-height:801px)_and_(max-height:900px)]:space-y-2">
          <Button type="submit" size="lg" className={AUTH_SUBMIT} loading={form.formState.isSubmitting}>
            {!form.formState.isSubmitting ? <UserPlus /> : null}
            Create account
          </Button>
          <p className="text-center text-xs leading-5 text-muted-foreground">
            By creating an account you agree to JobPilot&rsquo;s terms of use.
          </p>
        </div>
      </form>
    </Form>
  )
}
