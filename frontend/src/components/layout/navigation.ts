import {
  BarChart3,
  Bot,
  Briefcase,
  Building2,
  CalendarClock,
  FileText,
  LayoutDashboard,
  ListChecks,
  Mail,
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
}

export interface NavSection {
  title: string
  items: NavItem[]
}

/** The 12 sidebar destinations, grouped for scanability. */
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
      { label: 'Resume', to: '/resume', icon: FileText, description: 'Versions and parsed data' },
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

export const NAV_ITEMS: NavItem[] = NAV_SECTIONS.flatMap((section) => section.items)

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
