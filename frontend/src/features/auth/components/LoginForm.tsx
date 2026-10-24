import { zodResolver } from '@hookform/resolvers/zod'
import { LogIn } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { PasswordInput } from '@/features/auth/components/PasswordInput'
import { StaySignedInField } from '@/features/auth/components/StaySignedInField'
import { AUTH_FORM, AUTH_INPUT, AUTH_ITEM, AUTH_LABEL, AUTH_SUBMIT } from '@/features/auth/components/authFormStyles'
import { usePostAuthRedirect } from '@/features/auth/usePostAuthRedirect'
import { errorMessage } from '@/lib/api'
import { offerToSavePassword } from '@/lib/credentials'
import { roleLabel } from '@/lib/roles'
import { useAuthStore } from '@/stores/auth'

export const loginSchema = z.object({
  email: z.string().min(1, 'Email is required').email('Enter a valid email address'),
  password: z.string().min(1, 'Password is required'),
  /** "Stay signed in on this device": only how long the session cookie lives. */
  remember_me: z.boolean(),
})

export type LoginValues = z.infer<typeof loginSchema>

export interface LoginFormProps {
  /** Focus the email field on mount (the full page; Radix focuses it inside the modal). */
  autoFocus?: boolean
}

/**
 * The one sign-in form: used by `/login` and by the landing page's modal. Owns validation,
 * the credential-save offer, toasts and the post-sign-in routing (deep link → else /home;
 * several roles → /choose-role).
 */
export function LoginForm({ autoFocus = true }: LoginFormProps) {
  const navigate = useNavigate()
  const login = useAuthStore((state) => state.login)
  const { from, redirectTo, redirectState } = usePostAuthRedirect()

  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '', remember_me: false },
  })

  async function onSubmit(values: LoginValues) {
    try {
      const outcome = await login(values.email, values.password, values.remember_me)
      // The password was accepted: let the browser's password manager offer to save it.
      // That is the only place it goes; our code keeps no copy after this call.
      offerToSavePassword({ email: values.email, password: values.password, name: outcome.user.full_name })
      form.resetField('password')
      if (outcome.status === 'role_selection') {
        // Several roles held: the session starts only once one is chosen.
        navigate('/choose-role', { replace: true, state: { from: from ?? undefined } })
        return
      }
      const { user } = outcome
      if (outcome.autoSelected) {
        // Picked silently from this device's remembered role; make switching one click away.
        toast.success(`Signed in as ${roleLabel(outcome.autoSelected)}.`, {
          description: `Welcome back, ${user.full_name || user.email}`,
          action: { label: 'Switch', onClick: () => navigate('/settings?section=roles') },
        })
      } else {
        toast.success(`Welcome back, ${user.full_name || user.email}`)
      }
      navigate(redirectTo, { replace: true, state: redirectState })
    } catch (error) {
      toast.error('Could not sign in', { description: errorMessage(error, 'Check your email and password.') })
      form.setError('password', { message: 'Invalid email or password' })
    }
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className={AUTH_FORM} noValidate>
        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem className={AUTH_ITEM}>
              <FormLabel className={AUTH_LABEL}>Email</FormLabel>
              <FormControl>
                <Input type="email" autoComplete="email" placeholder="you@example.com" autoFocus={autoFocus} className={AUTH_INPUT} {...field} />
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
                <PasswordInput autoComplete="current-password" placeholder="Your password" className={AUTH_INPUT} {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <StaySignedInField control={form.control} />

        <Button type="submit" size="lg" className={AUTH_SUBMIT} loading={form.formState.isSubmitting}>
          {!form.formState.isSubmitting ? <LogIn /> : null}
          Sign in
        </Button>
      </form>
    </Form>
  )
}
