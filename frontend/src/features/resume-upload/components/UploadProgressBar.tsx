import { Progress } from '@/components/ui/progress'

import type { UploadProgress } from '../types'

/** Real upload progress (XHR `upload.onprogress`), then "reading" while the server parses. */
export function UploadProgressBar({ progress, fileName }: { progress: UploadProgress; fileName?: string }) {
  const percent = progress.percent ?? 0
  const reading = progress.phase === 'reading'
  const label = reading ? 'Uploaded — reading your resume…' : `Uploading${fileName ? ` ${fileName}` : ''}`
  return (
    <div className="space-y-2" data-upload-progress>
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="min-w-0 truncate font-medium" aria-live="polite">
          {label}
        </span>
        <span className="shrink-0 tabular-nums text-muted-foreground">{percent}%</span>
      </div>
      <Progress
        value={percent}
        aria-label={reading ? 'Upload complete, reading the resume' : 'Upload progress'}
        aria-valuetext={reading ? 'Upload complete, reading the resume' : `${percent}% uploaded`}
        indicatorClassName="bg-gradient-brand"
        className="h-2.5"
      />
      {reading ? <p className="text-xs text-muted-foreground">Reading the text so scoring and tailoring work. This takes a few seconds.</p> : null}
    </div>
  )
}
