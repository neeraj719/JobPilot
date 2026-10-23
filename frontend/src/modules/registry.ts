/**
 * The client-side module registry.
 *
 * JobPilot is a suite of modules. The **server** (`GET /workspace/modules`) decides which
 * modules a user sees, in which order, and whether each can be opened; **this registry**
 * decides how a module renders: its icon, home route, the path prefixes it owns and its
 * sidebar sections. A module the server does not return is never rendered, and its routes
 * send the user to the launcher (`ModuleRoute`).
 *
 * URLs never move: `/jobs`, `/applications/:id`, `/resume/my/:id/edit`… are exactly the
 * routes they always were (notifications in the database link to them). The active module
 * is derived from the current path through `prefixes`.
 */
import {
  BarChart3,
  Bot,
  Briefcase,
  Building2,
  CalendarClock,
  FileText,
  LayoutDashboard,
  LayoutGrid,
  LineChart,
  ListChecks,
  Mail,
  Send,
  Settings,
  UserRound,
  type LucideIcon,
} from 'lucide-react'

import { RESUME_NAV_CHILDREN, type NavItem, type NavSection } from '@/components/layout/navigation'

export interface ModuleDefinition {
  code: string
  /** Fallback name; the server's `name` wins when it is known. */
  name: string
  icon: LucideIcon
  homePath: string
  /** Path prefixes this module owns (`/applications` owns `/applications/:id`). */
  prefixes: string[]
  /** Sidebar sections; empty for a module with no pages yet. */
  navSections: NavSection[]
  /** Fallback accent token (`primary` | `info` | `warning` | `success`). */
  accent: string
  /** Fetches the module's page bundle ahead of navigation (hover / focus on a card). */
  preload?: () => Promise<unknown>
}

function resumeItem(to: string): NavItem {
  const item = RESUME_NAV_CHILDREN.find((child) => child.to === to)
  if (!item) throw new Error(`Unknown resume destination ${to}`)
  return item
}

/** Resume Studio: the seven Resume pages, unchanged, grouped by what you are doing. */
const RESUME_SECTIONS: NavSection[] = [
  { title: 'Build', items: ['/resume', '/resume/my', '/resume/new'].map(resumeItem) },
  { title: 'Optimise', items: ['/resume/ats', '/resume/targets', '/resume/history'].map(resumeItem) },
  { title: 'Settings', items: ['/resume/ai-settings'].map(resumeItem) },
]

/** Job Apply: everything that finds, prepares, sends and tracks applications. */
const APPLY_SECTIONS: NavSection[] = [
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
    title: 'Automation',
    items: [
      { label: 'Automation', to: '/automation', icon: Bot, description: 'Daily run and safety rails' },
      { label: 'Emails', to: '/emails', icon: Mail, description: 'Replies detected in Gmail' },
    ],
  },
]

export const MODULE_REGISTRY: ModuleDefinition[] = [
  {
    code: 'resume',
    name: 'Resume Studio',
    icon: FileText,
    homePath: '/resume',
    prefixes: ['/resume'],
    navSections: RESUME_SECTIONS,
    accent: 'primary',
    preload: () => import('@/modules/resume/pages'),
  },
  {
    code: 'apply',
    name: 'Job Apply',
    icon: Briefcase,
    homePath: '/dashboard',
    prefixes: ['/dashboard', '/analytics', '/jobs', '/queue', '/applications', '/interviews', '/companies', '/automation', '/emails'],
    navSections: APPLY_SECTIONS,
    accent: 'info',
    preload: () => import('@/modules/apply/pages'),
  },
  {
    // Shown on the launcher as "coming soon"; no routes yet.
    code: 'insights',
    name: 'Career Insights',
    icon: LineChart,
    homePath: '/insights',
    prefixes: [],
    navSections: [],
    accent: 'warning',
  },
]

/** Pages that belong to no module: reachable from the account menu in every module. */
export const ACCOUNT_NAV_ITEMS: NavItem[] = [
  { label: 'Profile', to: '/profile', icon: UserRound, description: 'Facts used to answer forms' },
  { label: 'Settings', to: '/settings', icon: Settings, description: 'Account and integrations' },
]

/** The launcher's paths. */
export const LAUNCHER_PATHS = ['/', '/home'] as const

export function isLauncherPath(pathname: string): boolean {
  return (LAUNCHER_PATHS as readonly string[]).includes(pathname)
}

function ownsPath(prefix: string, pathname: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`)
}

export function getModuleDefinition(code: string | null | undefined): ModuleDefinition | undefined {
  if (!code) return undefined
  return MODULE_REGISTRY.find((module) => module.code === code)
}

/** The module that owns `pathname` (longest prefix wins), if any. */
export function findModuleForPath(pathname: string): ModuleDefinition | undefined {
  let best: { module: ModuleDefinition; length: number } | undefined
  for (const module of MODULE_REGISTRY) {
    for (const prefix of module.prefixes) {
      if (ownsPath(prefix, pathname) && (!best || prefix.length > best.length)) best = { module, length: prefix.length }
    }
  }
  return best?.module
}

/** Every destination of a module, children before their parent (see `navigation.ts`). */
export function moduleNavItems(module: ModuleDefinition): NavItem[] {
  return module.navSections.flatMap((section) => section.items.flatMap((item) => [...(item.children ?? []), item]))
}

/** Longest-prefix match among `items`, so `/applications/:id` resolves to Applications. */
export function findNavItemIn(items: NavItem[], pathname: string): NavItem | undefined {
  return [...items].sort((a, b) => b.to.length - a.to.length).find((item) => ownsPath(item.to, pathname))
}

export function findAccountItem(pathname: string): NavItem | undefined {
  return findNavItemIn(ACCOUNT_NAV_ITEMS, pathname)
}

/* ------------------------------------------------------------------ */
/* Rendering helpers                                                   */
/* ------------------------------------------------------------------ */

const SERVER_ICONS: Record<string, LucideIcon> = {
  FileText,
  Briefcase,
  LineChart,
  LayoutGrid,
}

/** The registry's icon for a known module, else the server's lucide name, else a grid. */
export function moduleIcon(code: string, serverIcon?: string | null): LucideIcon {
  return getModuleDefinition(code)?.icon ?? (serverIcon ? SERVER_ICONS[serverIcon] : undefined) ?? LayoutGrid
}

export interface AccentClasses {
  /** Tinted tile behind the icon. */
  soft: string
  /** Solid fill (selected / active). */
  solid: string
  /** Thin top border on launcher cards. */
  bar: string
}

/** Static class strings per accent token (Tailwind only ships classes it can see). */
const ACCENTS: Record<string, AccentClasses> = {
  primary: { soft: 'bg-primary/10 text-primary', solid: 'bg-primary text-primary-foreground', bar: 'bg-primary' },
  info: { soft: 'bg-info/10 text-info', solid: 'bg-info text-info-foreground', bar: 'bg-info' },
  warning: { soft: 'bg-warning/10 text-warning', solid: 'bg-warning text-warning-foreground', bar: 'bg-warning' },
  success: { soft: 'bg-success/10 text-success', solid: 'bg-success text-success-foreground', bar: 'bg-success' },
}

export function accentClasses(token: string | null | undefined): AccentClasses {
  return ACCENTS[token ?? ''] ?? ACCENTS.primary
}
