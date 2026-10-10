import { FileSignature, RotateCcw, Save, Sparkles } from 'lucide-react'
import * as React from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { formatDateTime } from '@/lib/utils'
import type { ApplicationDetail } from '@/types/api'

export interface CoverLetterTabProps {
  application: ApplicationDetail
  onGenerate: () => Promise<string | null | undefined> | void
  onSave: (content: string) => Promise<void> | void
  generating?: boolean
  saving?: boolean
}

/** Generate, edit and save the cover letter attached to this application. */
export function CoverLetterTab({
  application,
  onGenerate,
  onSave,
  generating = false,
  saving = false,
}: CoverLetterTabProps) {
  const stored = application.cover_letter ?? ''
  const [draft, setDraft] = React.useState(stored)

  React.useEffect(() => {
    setDraft(stored)
  }, [stored])

  const document = (application.documents ?? []).find((item) => item.document_type === 'COVER_LETTER')
  const dirty = draft !== stored
  const hasLetter = stored.trim().length > 0

  async function handleGenerate() {
    const generated = await onGenerate()
    if (typeof generated === 'string') setDraft(generated)
  }

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 space-y-0">
        <div className="space-y-1">
          <CardTitle className="text-base">Cover letter</CardTitle>
          <CardDescription>
            {document
              ? `Saved as ${document.filename} · ${formatDateTime(document.created_at)}`
              : 'Attached to this application when the form asks for one.'}
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void handleGenerate()} loading={generating}>
            <Sparkles />
            {hasLetter ? 'Regenerate' : 'Generate'}
          </Button>
          {dirty ? (
            <Button variant="ghost" size="sm" onClick={() => setDraft(stored)} disabled={saving}>
              <RotateCcw />
              Revert
            </Button>
          ) : null}
          <Button size="sm" onClick={() => void onSave(draft)} loading={saving} disabled={!dirty || draft.trim().length === 0}>
            <Save />
            Save
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        <Textarea
          rows={18}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Write a cover letter, or let JobPilot draft one from the job description and your resume."
          aria-label="Cover letter"
          className="font-normal leading-relaxed"
        />
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <FileSignature className="size-3.5" aria-hidden />
          {draft.trim().length === 0
            ? 'No cover letter yet.'
            : `${draft.trim().split(/\s+/).length} words${dirty ? ' · unsaved changes' : ''}`}
        </p>
      </CardContent>
    </Card>
  )
}
