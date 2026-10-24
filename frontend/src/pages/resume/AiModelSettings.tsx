import { BrainCircuit } from 'lucide-react'

import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useAiProviders, useAiSettings } from '@/features/ai-providers/api'
import { AiModelSettingsSkeleton } from '@/features/ai-providers/components/AiProvidersSkeleton'
import { ModelPromptCard } from '@/features/ai-providers/components/ModelPromptCard'
import { ProviderCard } from '@/features/ai-providers/components/ProviderCard'
import { ReauthDialog, useReauthGate } from '@/features/ai-providers/components/ReauthGate'
import { RoutingCard } from '@/features/ai-providers/components/RoutingCard'
import { SetupSummary } from '@/features/ai-providers/components/SetupSummary'
import { UsageCard } from '@/features/ai-providers/components/UsageCard'

/**
 * `/resume/ai-settings` — bring-your-own AI provider (ai-providers stream).
 *
 * Loading this page calls no hosted provider: model lists come from the registry and a
 * recent cached live list, and only the local Ollama server is probed. Hosted providers are
 * contacted only when the user tests a key or refreshes a model list.
 */
export default function AiModelSettingsPage() {
  useDocumentTitle('AI Model Settings')
  const catalog = useAiProviders()
  const settings = useAiSettings()
  const reauth = useReauthGate()

  const loading = catalog.isLoading || settings.isLoading
  const error = catalog.error ?? settings.error

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Resume"
        title="AI Model Settings"
        description="Choose which AI model writes, analyses and reviews your resumes — the free local model, or your own OpenAI, Gemini or Claude API key."
      />
      {loading ? (
        <AiModelSettingsSkeleton />
      ) : error ? (
        <ErrorState
          error={error}
          onRetry={() => {
            void catalog.refetch()
            void settings.refetch()
          }}
        />
      ) : !catalog.data || !settings.data ? (
        <EmptyState icon={BrainCircuit} title="No AI providers available" description="The server did not return any provider." />
      ) : (
        <div className="space-y-8">
          <SetupSummary settings={settings.data} catalog={catalog.data} />

          <section aria-labelledby="ai-providers-heading" className="space-y-3">
            <div>
              <h2 id="ai-providers-heading" className="text-lg font-semibold">Providers</h2>
              <p className="text-sm text-muted-foreground">
                Add a key, test it, then pick its models below. Nothing is sent to a hosted provider until you test or select it.
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {catalog.data.providers.map((provider) => (
                <ProviderCard key={provider.id} provider={provider} runSensitive={reauth.run} />
              ))}
            </div>
          </section>

          <ModelPromptCard settings={settings.data} />
          <RoutingCard settings={settings.data} providers={catalog.data.providers} />
          <UsageCard />
        </div>
      )}
      <ReauthDialog action={reauth.pending} onClose={reauth.close} />
    </PageContainer>
  )
}
