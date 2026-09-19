import { ImageOff } from 'lucide-react'
import * as React from 'react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useScreenshot } from '@/features/applications/api'
import { humanizeEnum } from '@/lib/utils'
import type { ApplicationDetail, UUID } from '@/types/api'

/** `C:\…\screenshots\<id>\after_fill.png` -> `after_fill`. Also accepts a bare name. */
function toScreenshotName(value: unknown): string | null {
  if (typeof value !== 'string' || !value.trim()) return null
  const base = value.split(/[\\/]/).pop() ?? value
  const name = base.replace(/\.png$/i, '').trim()
  return /^[A-Za-z0-9._-]+$/.test(name) ? name : null
}

/** Every screenshot name this application recorded, in capture order, deduplicated. */
export function collectScreenshotNames(application: ApplicationDetail): string[] {
  const snapshot = (application.form_snapshot ?? {}) as Record<string, unknown>
  const candidates: unknown[] = [snapshot.screenshot_path, snapshot.submit_screenshot_path]
  if (Array.isArray(snapshot.screenshots)) candidates.push(...snapshot.screenshots)
  for (const event of application.events ?? []) {
    const meta = event.meta ?? {}
    candidates.push(meta.screenshot_path, meta.submit_screenshot_path, meta.screenshot)
  }
  const names: string[] = []
  for (const candidate of candidates) {
    const name = toScreenshotName(candidate)
    if (name && !names.includes(name)) names.push(name)
  }
  return names
}

function ScreenshotImage({ applicationId, name }: { applicationId: UUID; name: string }) {
  const { data: blob, isLoading, isError } = useScreenshot(applicationId, name)
  const [url, setUrl] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (!blob) {
      setUrl(null)
      return
    }
    const objectUrl = URL.createObjectURL(blob)
    setUrl(objectUrl)
    return () => URL.revokeObjectURL(objectUrl)
  }, [blob])

  return (
    <figure className="space-y-2">
      <div className="overflow-hidden rounded-lg border border-border bg-muted/40">
        {isLoading ? (
          <Skeleton className="aspect-video w-full" />
        ) : isError || !url ? (
          <div className="flex aspect-video w-full flex-col items-center justify-center gap-1 text-muted-foreground">
            <ImageOff className="size-5" aria-hidden />
            <span className="text-xs">Screenshot unavailable</span>
          </div>
        ) : (
          <a href={url} target="_blank" rel="noreferrer noopener">
            <img src={url} alt={`Automation screenshot: ${humanizeEnum(name)}`} className="w-full" loading="lazy" />
          </a>
        )}
      </div>
      <figcaption className="text-xs text-muted-foreground">{humanizeEnum(name)}</figcaption>
    </figure>
  )
}

export interface ScreenshotGalleryProps {
  applicationId: UUID
  names: string[]
}

/** Automation screenshots, fetched as blobs because the endpoint needs the auth header. */
export function ScreenshotGallery({ applicationId, names }: ScreenshotGalleryProps) {
  if (names.length === 0) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Automation screenshots</CardTitle>
        <CardDescription>What the browser saw while filling this application.</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 sm:grid-cols-2">
          {names.map((name) => (
            <ScreenshotImage key={name} applicationId={applicationId} name={name} />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
