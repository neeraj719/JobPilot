import { Bell, Bot, LayoutGrid, Link2, Mail, ShieldCheck, ShieldPlus, SlidersHorizontal, UserCog, Users } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import * as React from 'react'
import { useSearchParams } from 'react-router-dom'

import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { toast } from '@/components/ui/toaster'
import { useAuth } from '@/hooks/useAuth'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { cn } from '@/lib/utils'
import { AccountRolesCard } from '@/features/settings/components/AccountRolesCard'
import { AiProvidersLinkCard } from '@/features/ai-providers/components/AiProvidersLinkCard'
import { AiSettingsCard } from '@/features/settings/components/AiSettingsCard'
import { AutomationSettingsForm } from '@/features/settings/components/AutomationSettingsForm'
import { ConnectedAccountsCard } from '@/features/settings/components/ConnectedAccountsCard'
import { LinkedInAccountCard } from '@/features/linkedin/components/LinkedInAccountCard'
import { EmailIntegrationCard } from '@/features/settings/components/EmailIntegrationCard'
import { NotificationSettingsCard } from '@/features/settings/components/NotificationSettingsCard'
import { SecurityCard } from '@/features/settings/components/SecurityCard'
import { SettingsShortcuts } from '@/features/settings/components/SettingsShortcuts'
import { useWorkspaceModules } from '@/features/workspace/api'
import { AdminCatalogCard } from '@/features/workspace/components/AdminCatalogCard'
import { AdminModulesCard } from '@/features/workspace/components/AdminModulesCard'
import { WorkspaceSettingsCard } from '@/features/workspace/components/WorkspaceSettingsCard'

type SettingsSection =
  | 'general'
  | 'workspace'
  | 'roles'
  | 'automation'
  | 'accounts'
  | 'email'
  | 'ai'
  | 'notifications'
  | 'security'
  | 'admin'

interface SectionDef {
  id: SettingsSection
  label: string
  /** One line under the section title. */
  blurb: string
  icon: LucideIcon
  /** Only for a session acting as ADMIN. */
  adminOnly?: boolean
  /** Hidden when this workspace module is not available to the user (its API refuses them). */
  module?: string
}

const SECTIONS: SectionDef[] = [
  { id: 'general', label: 'Your data', blurb: 'Where your profile, resumes and history live.', icon: UserCog },
  { id: 'workspace', label: 'Workspace', blurb: 'Where you land after signing in, and the order of your modules.', icon: LayoutGrid },
  { id: 'roles', label: 'Account roles', blurb: 'The roles this account can act as.', icon: Users },
  { id: 'automation', label: 'Limits & schedule', blurb: 'Daily limits, timing and the safety rails.', icon: SlidersHorizontal, module: 'apply' },
  { id: 'accounts', label: 'Connected accounts', blurb: 'Job platforms JobPilot may read from.', icon: Link2 },
  { id: 'email', label: 'Email integration', blurb: 'Read-only Gmail access for replies to your applications.', icon: Mail },
  { id: 'ai', label: 'AI & browser', blurb: 'The AI model and the browser that fills forms for you.', icon: Bot },
  { id: 'notifications', label: 'Notifications', blurb: 'What JobPilot tells you about, and where.', icon: Bell },
  { id: 'security', label: 'Security', blurb: 'Password, signed-in devices and sessions.', icon: ShieldCheck },
  { id: 'admin', label: 'Admin', blurb: 'Platform modules and per-user access.', icon: ShieldPlus, adminOnly: true },
]

function isSection(sections: SectionDef[], value: string | null): value is SettingsSection {
  return sections.some((section) => section.id === value)
}

/** Friendly copy for the `?error=` codes the Gmail OAuth callback can redirect with. */
const OAUTH_ERRORS: Record<string, string> = {
  access_denied: 'You declined the Google consent screen, so nothing was connected.',
  connection_failed: 'Google did not complete the handshake. Try connecting again.',
  invalid_state: 'That authorization link had already been used. Start the connection again.',
  not_configured: 'Gmail is not configured on this server yet.',
}

export default function SettingsPage() {
  useDocumentTitle('Settings')

  const { isAdmin } = useAuth()
  const modules = useWorkspaceModules()
  const sections = SECTIONS.filter((section) => {
    if (section.adminOnly && !isAdmin) return false
    // Until the module list loads (or if it fails) keep the section; its API still guards itself.
    if (section.module && modules.data) {
      return modules.data.some((module) => module.code === section.module && module.available)
    }
    return true
  })
  const [searchParams, setSearchParams] = useSearchParams()
  const sectionParam = searchParams.get('section')
  const activeSection: SettingsSection = isSection(sections, sectionParam) ? sectionParam : 'general'
  const activeMeta = sections.find((section) => section.id === activeSection)

  const setSection = React.useCallback(
    (section: string) => {
      const next = new URLSearchParams(searchParams)
      next.set('section', section)
      setSearchParams(next, { replace: true })
    },
    [searchParams, setSearchParams],
  )

  // The Gmail OAuth callback can land here with ?connected=1 or ?error=…
  const connected = searchParams.get('connected')
  const oauthError = searchParams.get('error')
  React.useEffect(() => {
    if (!connected && !oauthError) return
    if (connected) {
      toast.success('Gmail connected', { description: 'Read-only access granted. Run a sync to pull recent mail.' })
    } else if (oauthError) {
      toast.error('Gmail could not be connected', {
        description: OAUTH_ERRORS[oauthError] ?? `Google returned “${oauthError}”.`,
      })
    }
    const next = new URLSearchParams(searchParams)
    next.delete('connected')
    next.delete('error')
    next.set('section', 'email')
    setSearchParams(next, { replace: true })
  }, [connected, oauthError, searchParams, setSearchParams])

  return (
    <PageContainer>
      <PageHeader
        title="Settings"
        description="Account, connected platforms, automation limits and the safety rails that keep a human in the loop."
      />

      <div className="grid gap-6 lg:grid-cols-[14rem_minmax(0,1fr)]">
        <nav aria-label="Settings sections" className="min-w-0 lg:sticky lg:top-20 lg:self-start">
          {/* Mobile / tablet: a scrollable row of pills (the row scrolls, never the page). */}
          <ul className="scrollbar-none -mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:-mx-6 sm:px-6 lg:hidden">
            {sections.map((section) => {
              const Icon = section.icon
              const active = section.id === activeSection
              return (
                <li key={section.id} className="shrink-0">
                  <button
                    type="button"
                    onClick={() => setSection(section.id)}
                    aria-current={active ? 'page' : undefined}
                    className={cn(
                      'flex h-9 items-center gap-2 whitespace-nowrap rounded-full px-3.5 text-sm font-medium transition-[background-color,color,box-shadow]',
                      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
                      active
                        ? 'bg-gradient-brand text-gradient-foreground shadow-glow'
                        : 'border border-border bg-card text-muted-foreground hover:text-foreground',
                    )}
                  >
                    <Icon className="size-4 shrink-0" aria-hidden />
                    {section.label}
                  </button>
                </li>
              )
            })}
          </ul>

          {/* Desktop: a pill rail in its own card. */}
          <ul className="hidden space-y-1 rounded-2xl border border-border bg-card p-2 shadow-xs dark:shadow-highlight lg:block">
            {sections.map((section) => {
              const Icon = section.icon
              const active = section.id === activeSection
              return (
                <li key={section.id}>
                  <button
                    type="button"
                    onClick={() => setSection(section.id)}
                    aria-current={active ? 'page' : undefined}
                    className={cn(
                      'flex w-full items-center gap-2.5 rounded-full px-3 py-2 text-sm font-medium transition-[background-color,color,box-shadow]',
                      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card',
                      active
                        ? 'bg-gradient-brand text-gradient-foreground shadow-glow'
                        : 'text-muted-foreground hover:bg-accent hover:text-foreground',
                    )}
                  >
                    <Icon className="size-4 shrink-0" aria-hidden />
                    <span className="truncate">{section.label}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        </nav>

        <div className="min-w-0 space-y-6">
          {activeMeta ? (
            // Section header band: icon chip on the soft brand gradient + title + one line.
            <div className="border-gradient-soft flex items-center gap-4 rounded-2xl p-4 sm:p-5">
              <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-gradient-brand text-gradient-foreground shadow-glow">
                <activeMeta.icon className="size-5" aria-hidden />
              </span>
              <div className="min-w-0">
                <h2 className="font-display text-xl font-semibold tracking-tight">{activeMeta.label}</h2>
                <p className="text-sm text-muted-foreground">{activeMeta.blurb}</p>
              </div>
            </div>
          ) : null}
          {activeSection === 'general' ? <SettingsShortcuts /> : null}
          {activeSection === 'workspace' ? <WorkspaceSettingsCard /> : null}
          {activeSection === 'admin' ? (
            <div className="space-y-6">
              <AdminCatalogCard />
              <AdminModulesCard />
            </div>
          ) : null}
          {activeSection === 'roles' ? <AccountRolesCard /> : null}
          {activeSection === 'automation' ? <AutomationSettingsForm /> : null}
          {activeSection === 'accounts' ? (
            <>
              <LinkedInAccountCard />
              <ConnectedAccountsCard />
            </>
          ) : null}
          {activeSection === 'email' ? <EmailIntegrationCard /> : null}
          {activeSection === 'ai' ? (
            <>
              <AiProvidersLinkCard />
              <AiSettingsCard />
            </>
          ) : null}
          {activeSection === 'notifications' ? <NotificationSettingsCard /> : null}
          {activeSection === 'security' ? <SecurityCard /> : null}
        </div>
      </div>
    </PageContainer>
  )
}
