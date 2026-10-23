import * as React from 'react'
import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import { Spinner } from '@/components/ui/spinner'
import { ModuleRoute, PageLoading } from '@/modules/ModuleRoute'
import { useAuthStore } from '@/stores/auth'
import ChooseRolePage from '@/pages/ChooseRole'
import HomePage from '@/pages/Home'
import LoginPage from '@/pages/Login'
import NotFoundPage from '@/pages/NotFound'
import RegisterPage from '@/pages/Register'

/*
 * Code-splitting: each workspace module's pages are one lazily loaded bundle
 * (`src/modules/<code>/pages.ts`), and so are the account pages. The sign-in pages and the
 * launcher stay in the main bundle so the first paint after login needs nothing else.
 */
const loadResume = () => import('@/modules/resume/pages')
const loadApply = () => import('@/modules/apply/pages')
const loadAccount = () => import('@/modules/account/pages')

function lazyPage<M extends Record<string, unknown>, K extends keyof M & string>(load: () => Promise<M>, name: K) {
  return React.lazy(async () => ({ default: (await load())[name] as React.ComponentType }))
}

const DashboardPage = lazyPage(loadApply, 'DashboardPage')
const AnalyticsPage = lazyPage(loadApply, 'AnalyticsPage')
const JobsPage = lazyPage(loadApply, 'JobsPage')
const QueuePage = lazyPage(loadApply, 'QueuePage')
const ApplicationsPage = lazyPage(loadApply, 'ApplicationsPage')
const ApplicationDetailPage = lazyPage(loadApply, 'ApplicationDetailPage')
const CompaniesPage = lazyPage(loadApply, 'CompaniesPage')
const InterviewsPage = lazyPage(loadApply, 'InterviewsPage')
const AutomationPage = lazyPage(loadApply, 'AutomationPage')
const EmailsPage = lazyPage(loadApply, 'EmailsPage')

const ResumeDashboardPage = lazyPage(loadResume, 'ResumeDashboardPage')
const MyResumesPage = lazyPage(loadResume, 'MyResumesPage')
const ResumeEditorPage = lazyPage(loadResume, 'ResumeEditorPage')
const CreateResumePage = lazyPage(loadResume, 'CreateResumePage')
const AtsOptimizerPage = lazyPage(loadResume, 'AtsOptimizerPage')
const JobTargetsPage = lazyPage(loadResume, 'JobTargetsPage')
const JobTargetDetailPage = lazyPage(loadResume, 'JobTargetDetailPage')
const AiModelSettingsPage = lazyPage(loadResume, 'AiModelSettingsPage')
const VersionHistoryPage = lazyPage(loadResume, 'VersionHistoryPage')

const ProfilePage = lazyPage(loadAccount, 'ProfilePage')
const SettingsPage = lazyPage(loadAccount, 'SettingsPage')

/** Account pages belong to no module: they only need a Suspense boundary of their own. */
function AccountRoute() {
  return (
    <React.Suspense fallback={<PageLoading />}>
      <Outlet />
    </React.Suspense>
  )
}

function FullPageSpinner() {
  return (
    <div className="flex min-h-svh items-center justify-center">
      <Spinner size="lg" label="Loading JobPilot" />
    </div>
  )
}

/** Waits for the stored session to be validated, then redirects anonymous users to /login. */
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const accessToken = useAuthStore((state) => state.accessToken)
  const isBootstrapped = useAuthStore((state) => state.isBootstrapped)
  const pendingRoleSelection = useAuthStore((state) => state.pendingRoleSelection)

  if (!isBootstrapped) return <FullPageSpinner />
  const from = location.pathname + location.search
  // Password accepted but no role chosen yet: finish that before anything else.
  if (!accessToken && pendingRoleSelection) return <Navigate to="/choose-role" replace state={{ from }} />
  if (!accessToken) return <Navigate to="/login" replace state={{ from }} />
  return <>{children}</>
}

/** /choose-role is only meaningful while a role selection is pending. */
function RoleSelectionRoute({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const accessToken = useAuthStore((state) => state.accessToken)
  const isBootstrapped = useAuthStore((state) => state.isBootstrapped)
  const pendingRoleSelection = useAuthStore((state) => state.pendingRoleSelection)

  if (!isBootstrapped) return <FullPageSpinner />
  if (accessToken) return <Navigate to={(location.state as { from?: string } | null)?.from ?? '/home'} replace />
  if (!pendingRoleSelection) return <Navigate to="/login" replace />
  return <>{children}</>
}

/** Keeps signed-in users away from /login and /register. */
function PublicOnlyRoute({ children }: { children: React.ReactNode }) {
  const accessToken = useAuthStore((state) => state.accessToken)
  const isBootstrapped = useAuthStore((state) => state.isBootstrapped)

  if (!isBootstrapped) return <FullPageSpinner />
  if (accessToken) return <Navigate to="/home" replace />
  return <>{children}</>
}

export function AppRoutes() {
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <PublicOnlyRoute>
            <LoginPage />
          </PublicOnlyRoute>
        }
      />
      <Route
        path="/choose-role"
        element={
          <RoleSelectionRoute>
            <ChooseRolePage />
          </RoleSelectionRoute>
        }
      />
      <Route
        path="/register"
        element={
          <PublicOnlyRoute>
            <RegisterPage />
          </PublicOnlyRoute>
        }
      />

      <Route
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      >
        {/* The module launcher. */}
        <Route index element={<HomePage />} />
        <Route path="/home" element={<HomePage />} />

        {/* Job Apply. URLs are unchanged: notifications in the database link to them. */}
        <Route element={<ModuleRoute code="apply" />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/queue" element={<QueuePage />} />
          <Route path="/applications" element={<ApplicationsPage />} />
          <Route path="/applications/:id" element={<ApplicationDetailPage />} />
          <Route path="/companies" element={<CompaniesPage />} />
          <Route path="/interviews" element={<InterviewsPage />} />
          <Route path="/automation" element={<AutomationPage />} />
          <Route path="/emails" element={<EmailsPage />} />
        </Route>

        {/* Resume Studio — see notes/resume-studio-plan.md */}
        <Route element={<ModuleRoute code="resume" />}>
          <Route path="/resume" element={<ResumeDashboardPage />} />
          <Route path="/resume/my" element={<MyResumesPage />} />
          <Route path="/resume/my/:id" element={<MyResumesPage />} />
          <Route path="/resume/my/:id/edit" element={<ResumeEditorPage />} />
          <Route path="/resume/new" element={<CreateResumePage />} />
          <Route path="/resume/ats" element={<AtsOptimizerPage />} />
          <Route path="/resume/targets" element={<JobTargetsPage />} />
          <Route path="/resume/targets/:id" element={<JobTargetDetailPage />} />
          <Route path="/resume/ai-settings" element={<AiModelSettingsPage />} />
          <Route path="/resume/history" element={<VersionHistoryPage />} />
        </Route>

        {/* Account pages: in no module, reachable from the account menu everywhere. */}
        <Route element={<AccountRoute />}>
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}

export default AppRoutes
