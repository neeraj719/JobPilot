import { zodResolver } from '@hookform/resolvers/zod'
import { Eye, EyeOff, LogIn } from 'lucide-react'
import * as React from 'react'
import { useForm } from 'react-hook-form'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { z } from 'zod'

import { AuthLayout } from '@/components/layout/AuthLayout'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { errorMessage } from '@/lib/api'
import { offerToSavePassword } from '@/lib/credentials'
import { roleLabel } from '@/lib/roles'
import { useAuthStore } from '@/stores/auth'

const loginSchema = z.object({
  email: z.string().min(1, 'Email is required').email('Enter a valid email address'),
  password: z.string().min(1, 'Password is required'),
  /** "Stay signed in on this device": only how long the session cookie lives. */
  remember_me: z.boolean(),
})

type LoginValues = z.infer<typeof loginSchema>

export default function LoginPage() {
  useDocumentTitle('Sign in')
  const navigate = useNavigate()
  const location = useLocation()
  const login = useAuthStore((state) => state.login)
  const [showPassword, setShowPassword] = React.useState(false)

  const redirectTo = (location.state as { from?: string } | null)?.from ?? '/dashboard'

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
        navigate('/choose-role', { replace: true, state: { from: redirectTo } })
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
      navigate(redirectTo, { replace: true })
    } catch (error) {
      toast.error('Could not sign in', { description: errorMessage(error, 'Check your email and password.') })
      form.setError('password', { message: 'Invalid email or password' })
    }
  }

  return (
    <AuthLayout
      title="Sign in"
      description="Pick up where your job search left off."
      footer={
        <>
          New here?{' '}
          <Link to="/register" className="font-medium text-primary underline-offset-4 hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Email</FormLabel>
                <FormControl>
                  <Input type="email" autoComplete="email" placeholder="you@example.com" autoFocus {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="password"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Password</FormLabel>
                <FormControl>
                  <div className="relative">
                    <Input
                      type={showPassword ? 'text' : 'password'}
                      autoComplete="current-password"
                      placeholder="Your password"
                      className="pr-10"
                      {...field}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((value) => !value)}
                      className="absolute right-0 top-0 flex h-9 w-10 items-center justify-center text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                    >
                      {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                    </button>
                  </div>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="remember_me"
            render={({ field }) => (
              <FormItem className="flex items-start gap-2 space-y-0">
                <FormControl>
                  <Checkbox
                    checked={field.value}
                    onCheckedChange={(value) => field.onChange(value === true)}
                    className="mt-0.5"
                  />
                </FormControl>
                <div className="space-y-0.5">
                  <FormLabel className="text-sm font-normal">Stay signed in on this device</FormLabel>
                  <FormDescription className="text-xs">
                    Keeps you signed in for 14 days. Only use on a device you own.
                  </FormDescription>
                </div>
              </FormItem>
            )}
          />

          <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
            {!form.formState.isSubmitting ? <LogIn /> : null}
            Sign in
          </Button>
        </form>
      </Form>
    </AuthLayout>
  )
}
