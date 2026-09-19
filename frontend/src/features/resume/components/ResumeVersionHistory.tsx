import { History } from 'lucide-react'

import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { LoadingState } from '@/components/common/LoadingState'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatDateTime, formatRelative } from '@/lib/utils'
import { useResumeVersions } from '@/features/resume/api'
import type { ParsedResume } from '@/types/api'

export interface ResumeVersionHistoryProps {
  resumeId: string
  currentVersion: number
}

function summarise(parsed: ParsedResume | Record<string, never>): string {
  const data = parsed as Partial<ParsedResume>
  const bits: string[] = []
  if (data.skills?.length) bits.push(`${data.skills.length} skills`)
  if (data.experience?.length) bits.push(`${data.experience.length} roles`)
  if (data.education?.length) bits.push(`${data.education.length} education`)
  if (data.projects?.length) bits.push(`${data.projects.length} projects`)
  return bits.length > 0 ? bits.join(' · ') : 'No structured data'
}

/** Read-only trail of every saved edit to the parsed data. */
export function ResumeVersionHistory({ resumeId, currentVersion }: ResumeVersionHistoryProps) {
  const versions = useResumeVersions(resumeId)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Version history</CardTitle>
        <CardDescription>Every save of the extracted information is kept as a snapshot.</CardDescription>
      </CardHeader>
      <CardContent>
        {versions.isLoading ? (
          <LoadingState variant="list" rows={3} />
        ) : versions.error ? (
          <ErrorState error={versions.error} size="sm" onRetry={() => void versions.refetch()} />
        ) : (versions.data?.length ?? 0) === 0 ? (
          <EmptyState
            size="sm"
            icon={History}
            title="No earlier versions"
            description="Edit the extracted information and the previous snapshot will appear here."
          />
        ) : (
          <ol className="space-y-2">
            {versions.data?.map((version) => (
              <li
                key={version.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border px-3 py-2"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">Version {version.version_number}</span>
                    {version.version_number === currentVersion ? <Badge variant="muted">Current</Badge> : null}
                  </div>
                  <p className="truncate text-xs text-muted-foreground">{version.note || summarise(version.parsed_data)}</p>
                </div>
                <time className="text-xs text-muted-foreground" dateTime={version.created_at} title={formatDateTime(version.created_at)}>
                  {formatRelative(version.created_at)}
                </time>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  )
}
