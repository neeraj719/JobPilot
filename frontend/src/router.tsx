import * as React from 'react'
import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import { AppShellSkeleton, AuthSkeleton } from '@/components/common/skeletons'
import { LandingSkeleton } from '@/features/landing/LandingSkeleton'
import { loadLanding } from '@/features/landing/loadLanding'
import { ModuleRoute, PageLoading } from '@/modules/ModuleRoute'
import { isLauncherPath } from '@/modules/registry'
import { hasSessionHint, useAuthStore } from '@/stores/auth'
import { RouteErrorBoundary } from '@/components/common/ErrorBoundary'
import { loadAuthPages, loadHome, loadResumePages } from '@/modules/prefetch'
import NotFoundPage from '@/pages/NotFound'

/*
 * Code-splitting: each workspace module's pages are one lazily loaded bundle
 * (`src/modules/<code>/pages.ts`), and so are the account pages. The sign-in pages and the
 * launcher stay in the main bundle so the first paint after login needs nothing else.
 */
const loadResume = loadResumePages
const loadApply = () => import('@/modules/apply/pages')
const loadAccount = () => import('@/modules/account/pages')
const loadAuth = loadAuthPages
// The launcher (`loadHome`) is its own chunk too: it keeps the main bundle in budget and is
// prefetched (idle, from the landing / sign-in pages; eagerly on a launcher reload).

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
const TailorComposerPage = lazyPage(loadResume, 'TailorComposerPage')
const AiModelSettingsPage = lazyPage(loadResume, 'AiModelSettingsPage')
const VersionHistoryPage = lazyPage(loadResume, 'VersionHistoryPage')

const ProfilePage = lazyPage(loadAccount, 'ProfilePage')
const LoginPage = lazyPage(loadAuth, 'LoginPage')
const RegisterPage = lazyPage(loadAuth, 'RegisterPage')
const ChooseRolePage = lazyPage(loadAuth, 'ChooseRolePage')
const SettingsPage = lazyPage(loadAccount, 'SettingsPage')
/** The public landing page (anonymous `/`): its own chunk, no app shell. */
const LandingPage = React.lazy(loadLanding)
const HomePage = React.lazy(loadHome)
// A visitor opening `/` without a session token: start downloading the landing chunk now, in
// parallel with React's first render, instead of after the route resolves.
if (typeof window !== 'undefined') {
  const hasToken = Boolean(useAuthStore.getState().accessToken)
  if (window.location.pathname === '/' && !hasToken) void loadLanding()
  // A member reloading the launcher: fetch its chunk while the session is validated.
  else if (hasToken && isLauncherPath(window.location.pathname)) void loadHome()
}

/** Account pages belong to no module: they only need a Suspense boundary of their own. */
function AccountRoute() {
  return (
    <RouteErrorBoundary label="this page">
      <React.Suspense fallback={<PageLoading />}>
        <Outlet />
      </React.Suspense>
    </RouteErrorBoundary>
  )
}

/** The launcher's Suspense + error boundary (its chunk is usually prefetched already). */
function LauncherRoute() {
  return (
    <RouteErrorBoundary label="the launcher">
      <React.Suspense fallback={<PageLoading />}>
        <HomePage />
      </React.Suspense>
    </RouteErrorBoundary>
  )
}


/**
 * Waits for the stored session to be validated, then redirects anonymous users to /login —
 * except on `/`, where they get the landing page.
 */
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const accessToken = useAuthStore((state) => state.accessToken)
  const isBootstrapped = useAuthStore((state) => state.isBootstrapped)
  const pendingRoleSelection = useAuthStore((state) => state.pendingRoleSelection)
  const signOutReason = useAuthStore((state) => state.signOutReason)

  const isRoot = location.pathname === '/'

  // Anonymous `/`: the public landing page — right away when this device has no session to
  // restore (no wait for the bootstrap; skeleton only while the landing chunk downloads).
  // A pending role selection does not hijack `/`: a visitor who left the chooser, or signed
  // out, asked for the landing page.
  if (isRoot && !accessToken && (isBootstrapped || !hasSessionHint())) {
    return (
      <RouteErrorBoundary label="the home page">
        <React.Suspense fallback={<LandingSkeleton />}>
          <LandingPage />
        </React.Suspense>
      </RouteErrorBoundary>
    )
  }
  if (!isBootstrapped) {
    // `/` is the landing page for visitors and the launcher for members: guess from the
    // token this tab already holds which of the two to sketch.
    if (isRoot && !accessToken) return <LandingSkeleton />
    return <AppShellSkeleton withSidebar={!isLauncherPath(location.pathname)} />
  }
  const from = location.pathname + location.search
  // Password accepted but no role chosen yet: finish that before anything else.
  if (!accessToken && pendingRoleSelection) return <Navigate to="/choose-role" replace state={{ from }} />
  if (!accessToken) {
    // Session refused by the API: the sign-in modal on the landing page, back here afterwards.
    if (signOutReason === 'expired') return <Navigate to="/?auth=login" replace state={{ from }} />
    // Signed out (here or in another tab): the landing page.
    if (signOutReason) return <Navigate to="/" replace />
    // Never signed in (a deep link): sign in, then come back.
    return <Navigate to="/login" replace state={{ from }} />
  }
  return <>{children}</>
}

/** /choose-role is only meaningful while a role selection is pending. */
function RoleSelectionRoute({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const accessToken = useAuthStore((state) => state.accessToken)
  const isBootstrapped = useAuthStore((state) => state.isBootstrapped)
  const pendingRoleSelection = useAuthStore((state) => state.pendingRoleSelection)

  if (!isBootstrapped) return <ChooseRoleSkeleton />
  if (accessToken) return <Navigate to={(location.state as { from?: string } | null)?.from ?? '/home'} replace />
  // Nothing to choose (signed out, expired or abandoned selection): the landing page.
  if (!pendingRoleSelection) return <Navigate to="/" replace />
  return <>{children}</>
}

/** The role chooser's skeleton, one row per pending role (the store knows them already). */
function ChooseRoleSkeleton() {
  const roles = useAuthStore((state) => state.pendingRoleSelection?.roles.length ?? 2)
  return <AuthSkeleton variant="roles" roles={roles} />
}

/** Keeps signed-in users away from /login and /register. */
function PublicOnlyRoute({ children }: { children: React.ReactNode }) {
  const accessToken = useAuthStore((state) => state.accessToken)
  const isBootstrapped = useAuthStore((state) => state.isBootstrapped)

  if (!isBootstrapped) return <AuthSkeleton />
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
            <RouteErrorBoundary label="sign-in">
              <React.Suspense fallback={<AuthSkeleton />}>
                <LoginPage />
              </React.Suspense>
            </RouteErrorBoundary>
          </PublicOnlyRoute>
        }
      />
      <Route
        path="/choose-role"
        element={
          <RoleSelectionRoute>
            <RouteErrorBoundary label="sign-in">
              <React.Suspense fallback={<ChooseRoleSkeleton />}>
                <ChooseRolePage />
              </React.Suspense>
            </RouteErrorBoundary>
          </RoleSelectionRoute>
        }
      />
      <Route
        path="/register"
        element={
          <PublicOnlyRoute>
            <RouteErrorBoundary label="sign-in">
              <React.Suspense fallback={<AuthSkeleton />}>
                <RegisterPage />
              </React.Suspense>
            </RouteErrorBoundary>
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
        <Route index element={<LauncherRoute />} />
        <Route path="/home" element={<LauncherRoute />} />

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
          <Route path="/resume/targets/new" element={<TailorComposerPage />} />
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
