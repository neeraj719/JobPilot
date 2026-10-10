import { Plus, Rocket } from 'lucide-react'
import * as React from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { toast } from '@/components/ui/toaster'
import { errorMessage } from '@/lib/api'
import { SOURCE_LABELS } from '@/lib/utils'
import { useCreateCompany, useQuickStartSuggestions, useUpsertCompanyPreference } from '@/features/companies/api'
import type { CompanySuggestion } from '@/types/api'

/** Tags worth showing on a suggestion chip (the ranking tags plus "india"). */
const SHOWN_TAGS = new Set(['FAANG', 'unicorn', 'india'])

/**
 * "Quick start": shown while the user's list has fewer than 3 companies with a career
 * board. Lists popular companies from the bundled known-board list; "Add to my list"
 * puts one on the list at P2 (adding the company first when the registry does not have
 * its board yet), so the next discovery run reads real openings from it.
 */
export function QuickStartPanel() {
  const suggestions = useQuickStartSuggestions(20)
  const create = useCreateCompany()
  const upsert = useUpsertCompanyPreference()
  const [addingName, setAddingName] = React.useState<string | null>(null)
  const [added, setAdded] = React.useState<Set<string>>(() => new Set())

  const data = suggestions.data
  if (!data || !data.show_quick_start || data.items.length === 0) return null

  const items = data.items.filter((item) => !added.has(item.name))

  async function addToList(item: CompanySuggestion) {
    setAddingName(item.name)
    try {
      if (!item.board_configured) {
        await create.mutateAsync({
          name: item.name,
          website: item.domain ? `https://${item.domain}` : null,
          auto_detect: true,
        })
      }
      await upsert.mutateAsync({ company_name: item.name, priority: 'P2' })
      setAdded((current) => new Set(current).add(item.name))
      toast.success(`${item.name} added to your list (P2)`)
    } catch (error) {
      toast.error(`Could not add ${item.name}`, { description: errorMessage(error) })
    } finally {
      setAddingName(null)
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <Rocket className="size-4 text-primary" aria-hidden />
          Quick start
        </CardTitle>
        <CardDescription>
          Add a few companies whose public career boards JobPilot already knows — their real openings show up on the
          next discovery run. {data.board_companies > 0 ? `${data.board_companies} of 3 added so far.` : null}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {items.map((item) => (
            <li key={item.name} className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{item.name}</p>
                <div className="mt-0.5 flex flex-wrap gap-1">
                  <Badge variant="muted">{SOURCE_LABELS[item.ats_type]}</Badge>
                  {item.tags
                    .filter((tag) => SHOWN_TAGS.has(tag))
                    .map((tag) => (
                      <Badge key={tag} variant="outline">
                        {tag === 'india' ? 'India' : tag}
                      </Badge>
                    ))}
                </div>
              </div>
              <Button
                size="sm"
                variant="outline"
                className="shrink-0"
                loading={addingName === item.name}
                disabled={addingName !== null && addingName !== item.name}
                onClick={() => void addToList(item)}
                aria-label={`Add ${item.name} to my list`}
              >
                {addingName === item.name ? null : <Plus aria-hidden />}
                Add to my list
              </Button>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
