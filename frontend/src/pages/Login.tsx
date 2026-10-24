import { Link } from 'react-router-dom'

import { AuthLayout } from '@/components/layout/AuthLayout'
import { LoginForm } from '@/features/auth/components/LoginForm'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

/** `/login`: the shared sign-in form (also used by the landing page's modal) in the split layout. */
export default function LoginPage() {
  useDocumentTitle('Sign in')

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
      <LoginForm />
    </AuthLayout>
  )
}
