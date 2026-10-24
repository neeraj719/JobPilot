/**
 * Resume Studio's pages, as one lazily loaded bundle (`router.tsx` imports this file with
 * `React.lazy`, `registry.ts` preloads it). Keep every Resume page here and nowhere else in
 * the eager import graph, or it is pulled back into the main bundle.
 */
export { default as AiModelSettingsPage } from '@/pages/resume/AiModelSettings'
export { default as AtsOptimizerPage } from '@/pages/resume/AtsOptimizer'
export { default as CreateResumePage } from '@/pages/resume/CreateResume'
export { default as JobTargetDetailPage } from '@/pages/resume/JobTargetDetail'
export { default as JobTargetsPage } from '@/pages/resume/JobTargets'
export { default as MyResumesPage } from '@/pages/resume/MyResumes'
export { default as ResumeDashboardPage } from '@/pages/resume/ResumeDashboard'
export { default as ResumeEditorPage } from '@/pages/resume/ResumeEditor'
export { default as TailorComposerPage } from '@/features/ats/tailor/TailorComposer'
export { default as VersionHistoryPage } from '@/pages/resume/VersionHistory'
