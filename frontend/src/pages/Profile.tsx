import { FileText } from 'lucide-react'
import * as React from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { ErrorState } from '@/components/common/ErrorState'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useJobPreferences, useProfile } from '@/features/profile/api'
import { EligibilitySection } from '@/features/profile/components/EligibilitySection'
import { JobPreferencesSection } from '@/features/profile/components/JobPreferencesSection'
import { PersonalSection } from '@/features/profile/components/PersonalSection'
import { ProfessionalSection } from '@/features/profile/components/ProfessionalSection'
import { ProfileCompleteness } from '@/features/profile/components/ProfileCompleteness'
import { StandingAnswersCard } from '@/features/profile/components/StandingAnswersCard'
import { useResumes } from '@/features/resume/api'
import type { ProfileTab } from '@/features/profile/schema'
import type { ParsedResume } from '@/types/api'
import { ProfileBodySkeleton } from '@/features/profile/components/ProfileSkeletons'

const TABS: { value: ProfileTab; label: string }[] = [
  { value: 'personal', label: 'Personal' },
  { value: 'professional', label: 'Professional' },
  { value: 'eligibility', label: 'Eligibility' },
  { value: 'preferences', label: 'Job preferences' },
]

function isProfileTab(value: string | null): value is ProfileTab {
  return TABS.some((tab) => tab.value === value)
}

/** `parsed_data` is `{}` until a resume has been parsed — narrow it before use. */
function parsedOrNull(data: unknown): ParsedResume | null {
  if (!data || typeof data !== 'object') return null
  const candidate = data as ParsedResume
  const hasContent =
    Boolean(candidate.name || candidate.email || candidate.summary) ||
    (candidate.skills?.length ?? 0) > 0 ||
    (candidate.experience?.length ?? 0) > 0
  return hasContent ? candidate : null
}

export default function ProfilePage() {
  useDocumentTitle('Profile')

  const [searchParams, setSearchParams] = useSearchParams()
  const tabParam = searchParams.get('tab')
  const activeTab: ProfileTab = isProfileTab(tabParam) ? tabParam : 'personal'

  const profileQuery = useProfile()
  const preferencesQuery = useJobPreferences()
  const resumesQuery = useResumes()

  const defaultResume = React.useMemo(() => {
    const resumes = resumesQuery.data ?? []
    return resumes.find((resume) => resume.is_default) ?? resumes[0] ?? null
  }, [resumesQuery.data])

  const resumeData = React.useMemo(() => parsedOrNull(defaultResume?.parsed_data), [defaultResume])

  const setTab = React.useCallback(
    (tab: string) => {
      const next = new URLSearchParams(searchParams)
      next.set('tab', tab)
      setSearchParams(next, { replace: true })
    },
    [searchParams, setSearchParams],
  )

  const isLoading = profileQuery.isLoading || preferencesQuery.isLoading
  const error = profileQuery.error ?? preferencesQuery.error

  return (
    <PageContainer>
      <PageHeader
        title="Profile"
        description="The facts used to answer application forms. Nothing here is ever invented by AI — a missing answer pauses the automation instead."
        actions={
          <Button variant="outline" asChild>
            <Link to="/resume">
              <FileText aria-hidden />
              Manage resumes
            </Link>
          </Button>
        }
      />

      {error ? (
        <ErrorState
          error={error}
          title="Could not load your profile"
          onRetry={() => {
            void profileQuery.refetch()
            void preferencesQuery.refetch()
          }}
        />
      ) : isLoading || !profileQuery.data || !preferencesQuery.data ? (
        <>
          <ProfileCompleteness completeness={0} missingFields={[]} loading onJumpTo={setTab} />
          <ProfileBodySkeleton />
        </>
      ) : (
        <>
          <ProfileCompleteness
            completeness={profileQuery.data.completeness}
            missingFields={profileQuery.data.missing_fields}
            onJumpTo={setTab}
          />

          <Tabs value={activeTab} onValueChange={setTab}>
            <TabsList className="flex h-auto w-full flex-wrap justify-start sm:w-auto">
              {TABS.map((tab) => (
                <TabsTrigger key={tab.value} value={tab.value}>
                  {tab.label}
                </TabsTrigger>
              ))}
            </TabsList>

            <TabsContent value="personal">
              <PersonalSection profile={profileQuery.data} resumeData={resumeData} />
            </TabsContent>
            <TabsContent value="professional">
              <ProfessionalSection profile={profileQuery.data} resumeData={resumeData} />
            </TabsContent>
            <TabsContent value="eligibility">
              <EligibilitySection profile={profileQuery.data} />
            </TabsContent>
            <TabsContent value="preferences">
              <JobPreferencesSection preferences={preferencesQuery.data} profile={profileQuery.data} />
            </TabsContent>
          </Tabs>

          <StandingAnswersCard />
        </>
      )}
    </PageContainer>
  )
}
