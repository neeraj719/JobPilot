import { Building2, ChevronRight, FileText, SlidersHorizontal, UserRound } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

interface Shortcut {
  to: string
  icon: LucideIcon
  title: string
  description: string
}

const SHORTCUTS: Shortcut[] = [
  {
    to: '/profile?tab=personal',
    icon: UserRound,
    title: 'Profile',
    description: 'Contact details, work history, skills and eligibility facts.',
  },
  {
    to: '/resume',
    icon: FileText,
    title: 'Resume',
    description: 'Upload resumes and review what the parser extracted.',
  },
  {
    to: '/profile?tab=preferences',
    icon: SlidersHorizontal,
    title: 'Job preferences',
    description: 'Titles, salary, locations, work modes and the minimum match score.',
  },
  {
    to: '/companies?tab=priorities',
    icon: Building2,
    title: 'Company preferences',
    description: 'Your P1/P2/P3 list and the companies to avoid entirely.',
  },
]

/** The settings that live on their own pages, linked from here so Settings stays one door. */
export function SettingsShortcuts() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Your data</CardTitle>
        <CardDescription>These settings have a page of their own.</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="divide-y divide-border rounded-lg border border-border">
          {SHORTCUTS.map((shortcut) => (
            <li key={shortcut.to}>
              <Link
                to={shortcut.to}
                className="flex items-center gap-3 p-3 transition-colors hover:bg-muted/50 focus-visible:bg-muted/50 focus-visible:outline-none"
              >
                <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-muted">
                  <shortcut.icon className="size-4" aria-hidden />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium">{shortcut.title}</span>
                  <span className="block text-xs text-muted-foreground">{shortcut.description}</span>
                </span>
                <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
