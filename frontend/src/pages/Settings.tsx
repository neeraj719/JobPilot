import { Bell, Bot, Link2, Mail, ShieldCheck, SlidersHorizontal, UserCog } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import * as React from 'react'
import { useSearchParams } from 'react-router-dom'

import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { toast } from '@/components/ui/toaster'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { cn } from '@/lib/utils'
import { AiSettingsCard } from '@/features/settings/components/AiSettingsCard'
import { AutomationSettingsForm } from '@/features/settings/components/AutomationSettingsForm'
import { ConnectedAccountsCard } from '@/features/settings/components/ConnectedAccountsCard'
import { EmailIntegrationCard } from '@/features/settings/components/EmailIntegrationCard'
import { NotificationSettingsCard } from '@/features/settings/components/NotificationSettingsCard'
import { SecurityCard } from '@/features/settings/components/SecurityCard'
import { SettingsShortcuts } from '@/features/settings/components/SettingsShortcuts'

type SettingsSection = 'general' | 'automation' | 'accounts' | 'email' | 'ai' | 'notifications' | 'security'

const SECTIONS: { id: SettingsSection; label: string; icon: LucideIcon }[] = [
  { id: 'general', label: 'Your data', icon: UserCog },
  { id: 'automation', label: 'Limits & schedule', icon: SlidersHorizontal },
  { id: 'accounts', label: 'Connected accounts', icon: Link2 },
  { id: 'email', label: 'Email integration', icon: Mail },
  { id: 'ai', label: 'AI & browser', icon: Bot },
  { id: 'notifications', label: 'Notifications', icon: Bell },
  { id: 'security', label: 'Security', icon: ShieldCheck },
]

function isSection(value: string | null): value is SettingsSection {
  return SECTIONS.some((section) => section.id === value)
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

  const [searchParams, setSearchParams] = useSearchParams()
  const sectionParam = searchParams.get('section')
  const activeSection: SettingsSection = isSection(sectionParam) ? sectionParam : 'general'

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
        <nav aria-label="Settings sections" className="lg:sticky lg:top-20 lg:self-start">
          <div className="lg:hidden">
            <Select value={activeSection} onValueChange={setSection}>
              <SelectTrigger aria-label="Settings section">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SECTIONS.map((section) => (
                  <SelectItem key={section.id} value={section.id}>
                    {section.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <ul className="hidden space-y-1 lg:block">
            {SECTIONS.map((section) => {
              const Icon = section.icon
              const active = section.id === activeSection
              return (
                <li key={section.id}>
                  <button
                    type="button"
                    onClick={() => setSection(section.id)}
                    aria-current={active ? 'page' : undefined}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors',
                      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                      active
                        ? 'bg-accent font-medium text-accent-foreground'
                        : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground',
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

        <div className="min-w-0">
          {activeSection === 'general' ? <SettingsShortcuts /> : null}
          {activeSection === 'automation' ? <AutomationSettingsForm /> : null}
          {activeSection === 'accounts' ? <ConnectedAccountsCard /> : null}
          {activeSection === 'email' ? <EmailIntegrationCard /> : null}
          {activeSection === 'ai' ? <AiSettingsCard /> : null}
          {activeSection === 'notifications' ? <NotificationSettingsCard /> : null}
          {activeSection === 'security' ? <SecurityCard /> : null}
        </div>
      </div>
    </PageContainer>
  )
}
