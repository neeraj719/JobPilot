import { Settings } from 'lucide-react'
import * as React from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { CompanyDirectory } from '@/features/companies/components/CompanyDirectory'
import { PriorityBoard } from '@/features/companies/components/PriorityBoard'

type CompaniesTab = 'priorities' | 'directory'

function isTab(value: string | null): value is CompaniesTab {
  return value === 'priorities' || value === 'directory'
}

export default function CompaniesPage() {
  useDocumentTitle('Companies')

  const [searchParams, setSearchParams] = useSearchParams()
  const tabParam = searchParams.get('tab')
  const activeTab: CompaniesTab = isTab(tabParam) ? tabParam : 'priorities'

  const setTab = React.useCallback(
    (tab: string) => {
      const next = new URLSearchParams(searchParams)
      next.set('tab', tab)
      setSearchParams(next, { replace: true })
    },
    [searchParams, setSearchParams],
  )

  return (
    <PageContainer>
      <PageHeader
        title="Companies"
        description="Decide which employers your queue should reach first — and which ones it should never touch."
        actions={
          <Button variant="outline" asChild>
            <Link to="/settings">
              <Settings aria-hidden />
              Settings
            </Link>
          </Button>
        }
      />

      <Tabs value={activeTab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="priorities">Priorities</TabsTrigger>
          <TabsTrigger value="directory">Directory</TabsTrigger>
        </TabsList>

        <TabsContent value="priorities">
          <PriorityBoard />
        </TabsContent>
        <TabsContent value="directory">
          <CompanyDirectory />
        </TabsContent>
      </Tabs>
    </PageContainer>
  )
}
