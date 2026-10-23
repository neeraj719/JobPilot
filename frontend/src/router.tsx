import * as React from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import { Spinner } from '@/components/ui/spinner'
import { useAuthStore } from '@/stores/auth'
import AnalyticsPage from '@/pages/Analytics'
import ApplicationDetailPage from '@/pages/ApplicationDetail'
import ApplicationsPage from '@/pages/Applications'
import AutomationPage from '@/pages/Automation'
import CompaniesPage from '@/pages/Companies'
import DashboardPage from '@/pages/Dashboard'
import EmailsPage from '@/pages/Emails'
import InterviewsPage from '@/pages/Interviews'
import JobsPage from '@/pages/Jobs'
import ChooseRolePage from '@/pages/ChooseRole'
import LoginPage from '@/pages/Login'
import NotFoundPage from '@/pages/NotFound'
import ProfilePage from '@/pages/Profile'
import QueuePage from '@/pages/Queue'
import RegisterPage from '@/pages/Register'
import SettingsPage from '@/pages/Settings'
import AiModelSettingsPage from '@/pages/resume/AiModelSettings'
import AtsOptimizerPage from '@/pages/resume/AtsOptimizer'
import CreateResumePage from '@/pages/resume/CreateResume'
import JobTargetDetailPage from '@/pages/resume/JobTargetDetail'
import JobTargetsPage from '@/pages/resume/JobTargets'
import MyResumesPage from '@/pages/resume/MyResumes'
import ResumeDashboardPage from '@/pages/resume/ResumeDashboard'
import ResumeEditorPage from '@/pages/resume/ResumeEditor'
import VersionHistoryPage from '@/pages/resume/VersionHistory'

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
  if (accessToken) return <Navigate to={(location.state as { from?: string } | null)?.from ?? '/dashboard'} replace />
  if (!pendingRoleSelection) return <Navigate to="/login" replace />
  return <>{children}</>
}

/** Keeps signed-in users away from /login and /register. */
function PublicOnlyRoute({ children }: { children: React.ReactNode }) {
  const accessToken = useAuthStore((state) => state.accessToken)
  const isBootstrapped = useAuthStore((state) => state.isBootstrapped)

  if (!isBootstrapped) return <FullPageSpinner />
  if (accessToken) return <Navigate to="/dashboard" replace />
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
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/queue" element={<QueuePage />} />
        <Route path="/applications" element={<ApplicationsPage />} />
        <Route path="/applications/:id" element={<ApplicationDetailPage />} />
        <Route path="/companies" element={<CompaniesPage />} />
        {/* Resume workspace — one sidebar group, see notes/resume-studio-plan.md */}
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
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/automation" element={<AutomationPage />} />
        <Route path="/emails" element={<EmailsPage />} />
        <Route path="/interviews" element={<InterviewsPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}

export default AppRoutes
