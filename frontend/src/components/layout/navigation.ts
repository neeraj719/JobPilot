import { BrainCircuit, Crosshair, FilePlus2, Files, Gauge, History, ScanSearch, type LucideIcon } from 'lucide-react'

/*
 * Navigation primitives. The sidebar *data* lives in the module registry
 * (`src/modules/registry.ts`): each workspace module owns its sections, and the sidebar
 * renders only the active module's.
 */

export interface NavItem {
  label: string
  /** Shorter label used in the collapsed rail tooltip. */
  to: string
  icon: LucideIcon
  /** Matched with `startsWith` so `/applications/:id` still highlights Applications. */
  matchPrefix?: boolean
  description?: string
  /**
   * Sub-destinations rendered as a collapsible group under the item. The parent `to` is the
   * group's landing page; a child may reuse it (shown as the group's first entry).
   */
  children?: NavItem[]
}

export interface NavSection {
  title: string
  items: NavItem[]
}

/** The Resume destinations (`notes/resume-studio-plan.md`); the `resume` module's sections. */
export const RESUME_NAV_CHILDREN: NavItem[] = [
  { label: 'Resume Dashboard', to: '/resume', icon: Gauge, description: 'Your resumes, analyses and targets at a glance' },
  { label: 'My Resumes', to: '/resume/my', icon: Files, matchPrefix: true, description: 'Every resume, its versions and parsed data' },
  { label: 'Create Resume', to: '/resume/new', icon: FilePlus2, description: 'Build from scratch or import' },
  { label: 'ATS Optimizer', to: '/resume/ats', icon: ScanSearch, matchPrefix: true, description: 'Score a resume against a job description' },
  { label: 'Job-Specific Resumes', to: '/resume/targets', icon: Crosshair, matchPrefix: true, description: 'Tailored versions per company and role' },
  { label: 'AI Model Settings', to: '/resume/ai-settings', icon: BrainCircuit, description: 'Your AI provider, keys and models' },
  { label: 'Version History', to: '/resume/history', icon: History, description: 'Compare and restore versions' },
]

export function isNavItemActive(item: NavItem, pathname: string): boolean {
  if (pathname === item.to) return true
  return Boolean(item.matchPrefix) && pathname.startsWith(`${item.to}/`)
}

/** True when the pathname is anywhere inside a group (the parent or any child). */
export function isNavGroupActive(item: NavItem, pathname: string): boolean {
  if (isNavItemActive(item, pathname)) return true
  return (item.children ?? []).some((child) => isNavItemActive(child, pathname))
}

/**
 * The child that owns `pathname`, by longest prefix, so `/resume/my/:id/edit` highlights
 * "My Resumes" and not the group's landing page, which every child path also starts with.
 */
export function activeNavChild(item: NavItem, pathname: string): NavItem | undefined {
  return [...(item.children ?? [])]
    .sort((a, b) => b.to.length - a.to.length)
    .find((child) => isNavItemActive(child, pathname))
}
