import {
  BarChart3,
  Bot,
  BrainCircuit,
  Briefcase,
  Building2,
  CalendarClock,
  Crosshair,
  FilePlus2,
  FileText,
  Files,
  Gauge,
  History,
  LayoutDashboard,
  ListChecks,
  Mail,
  ScanSearch,
  Send,
  Settings,
  UserRound,
  type LucideIcon,
} from 'lucide-react'

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

/** The Resume group: one sidebar entry, seven destinations (`notes/resume-studio-plan.md`). */
export const RESUME_NAV_CHILDREN: NavItem[] = [
  { label: 'Resume Dashboard', to: '/resume', icon: Gauge, description: 'Your resumes, analyses and targets at a glance' },
  { label: 'My Resumes', to: '/resume/my', icon: Files, matchPrefix: true, description: 'Every resume, its versions and parsed data' },
  { label: 'Create Resume', to: '/resume/new', icon: FilePlus2, description: 'Build from scratch or import' },
  { label: 'ATS Optimizer', to: '/resume/ats', icon: ScanSearch, matchPrefix: true, description: 'Score a resume against a job description' },
  { label: 'Job-Specific Resumes', to: '/resume/targets', icon: Crosshair, matchPrefix: true, description: 'Tailored versions per company and role' },
  { label: 'AI Model Settings', to: '/resume/ai-settings', icon: BrainCircuit, description: 'Your AI provider, keys and models' },
  { label: 'Version History', to: '/resume/history', icon: History, description: 'Compare and restore versions' },
]

/** The sidebar destinations, grouped for scanability. */
export const NAV_SECTIONS: NavSection[] = [
  {
    title: 'Overview',
    items: [
      { label: 'Dashboard', to: '/dashboard', icon: LayoutDashboard, description: 'Today at a glance' },
      { label: 'Analytics', to: '/analytics', icon: BarChart3, description: 'Funnel and trends' },
    ],
  },
  {
    title: 'Pipeline',
    items: [
      { label: 'Jobs', to: '/jobs', icon: Briefcase, description: 'Discovered and matched jobs' },
      { label: 'Application Queue', to: '/queue', icon: ListChecks, description: 'Prepared, waiting for you' },
      { label: 'Applications', to: '/applications', icon: Send, matchPrefix: true, description: 'Everything you sent' },
      { label: 'Interviews', to: '/interviews', icon: CalendarClock, description: 'Scheduled rounds and prep' },
      { label: 'Companies', to: '/companies', icon: Building2, description: 'Priorities and avoid list' },
    ],
  },
  {
    title: 'You',
    items: [
      {
        label: 'Resume',
        to: '/resume',
        icon: FileText,
        matchPrefix: true,
        description: 'Build, optimise and tailor your resume',
        children: RESUME_NAV_CHILDREN,
      },
      { label: 'Profile', to: '/profile', icon: UserRound, description: 'Facts used to answer forms' },
    ],
  },
  {
    title: 'System',
    items: [
      { label: 'Automation', to: '/automation', icon: Bot, description: 'Daily run and safety rails' },
      { label: 'Emails', to: '/emails', icon: Mail, description: 'Replies detected in Gmail' },
      { label: 'Settings', to: '/settings', icon: Settings, description: 'Account and integrations' },
    ],
  },
]

/** Every destination, children included (children come before their parent so the exact
 *  landing page of a group resolves to the child label, e.g. "Resume Dashboard"). */
export const NAV_ITEMS: NavItem[] = NAV_SECTIONS.flatMap((section) =>
  section.items.flatMap((item) => [...(item.children ?? []), item]),
)

/** Longest-prefix match so `/applications/:id` resolves to the Applications entry. */
export function findNavItem(pathname: string): NavItem | undefined {
  return [...NAV_ITEMS]
    .sort((a, b) => b.to.length - a.to.length)
    .find((item) => pathname === item.to || pathname.startsWith(`${item.to}/`))
}

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
