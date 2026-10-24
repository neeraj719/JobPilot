import { Link, useLocation } from 'react-router-dom'

import { AuthLayout } from '@/components/layout/AuthLayout'
import { RegisterForm } from '@/features/auth/components/RegisterForm'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

/** `/register`: the shared sign-up form (also used by the landing page's modal) in the split layout. */
export default function RegisterPage() {
  useDocumentTitle('Create account')
  const location = useLocation()

  return (
    <AuthLayout
      title="Create your account"
      description="Set up your profile once — JobPilot reuses those facts on every application."
      footer={
        <>
          Already have an account?{' '}
          {/* Keep a deep link the user was sent away from when switching to sign-in. */}
          <Link to="/login" state={location.state} className="font-medium text-primary underline-offset-4 hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <RegisterForm />
    </AuthLayout>
  )
}
