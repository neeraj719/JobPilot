import { Briefcase, ClipboardPaste, Crosshair, FileUp, Link2, Search } from 'lucide-react'
import * as React from 'react'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/api'
import { useJobs } from '@/features/jobs/api'
import { useFetchJd, useParseJd, useTargets, useUploadJd } from '@/features/ats/api'
import { JD_SOURCE_LABELS } from '@/features/ats/labels'
import type { JdInput, JdParseResult } from '@/features/ats/types'
import { StructuredJdView } from '@/features/ats/components/StructuredJdView'

export type JdTab = 'paste' | 'upload' | 'url' | 'target' | 'job'

export interface JdInputPanelProps {
  initialTarget?: string | null
  onChange: (jd: JdInput | null) => void
}

const MIN_CHARS = 120

function Preview({ result }: { result: JdParseResult }) {
  return (
    <div className="space-y-3 rounded-lg border border-border p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{result.title ?? 'Untitled role'}</span>
        {result.company ? <span className="text-muted-foreground">· {result.company}</span> : null}
        <Badge variant="outline">{JD_SOURCE_LABELS[result.source]}</Badge>
        <Badge variant={result.confidence === 'high' ? 'success' : result.confidence === 'medium' ? 'secondary' : 'warning'}>
          {result.confidence} confidence
        </Badge>
      </div>
      {result.warnings.map((warning) => (
        <p key={warning} className="text-xs text-warning">
          {warning}
        </p>
      ))}
      <StructuredJdView structured={result.structured} />
      <details className="text-sm">
        <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-muted-foreground">Text that will be analysed</summary>
        <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap rounded-md bg-muted/50 p-3 font-sans text-xs">{result.text}</pre>
      </details>
    </div>
  )
}

/** Step 2 of the optimizer: where the job description comes from. */
export function JdInputPanel({ initialTarget, onChange }: JdInputPanelProps) {
  const [tab, setTab] = React.useState<JdTab>(initialTarget ? 'target' : 'paste')
  const [text, setText] = React.useState('')
  const [company, setCompany] = React.useState('')
  const [title, setTitle] = React.useState('')
  const [url, setUrl] = React.useState('')
  const [useAi, setUseAi] = React.useState(false)
  const [targetId, setTargetId] = React.useState<string>(initialTarget ?? '')
  const [jobId, setJobId] = React.useState('')
  const [parsed, setParsed] = React.useState<JdParseResult | null>(null)
  const [error, setError] = React.useState<string | null>(null)

  const parse = useParseJd()
  const upload = useUploadJd()
  const fetchJd = useFetchJd()
  const targets = useTargets({ page_size: 100 })
  const jobs = useJobs({ page_size: 50 })

  // Report the current choice upwards.
  React.useEffect(() => {
    if (tab === 'paste') {
      if (text.trim().length < MIN_CHARS) return onChange(null)
      const structured = parsed && parsed.source === 'PASTED' && parsed.text.length > 0 ? parsed.structured : undefined
      return onChange({ text, company: company || null, title: title || null, source: 'PASTED', structured })
    }
    if (tab === 'upload' || tab === 'url') {
      if (!parsed || (tab === 'upload' ? parsed.source !== 'UPLOADED' : parsed.source === 'UPLOADED' || parsed.source === 'PASTED')) return onChange(null)
      return onChange({
        text: parsed.text,
        company: parsed.company,
        title: parsed.title,
        url: parsed.url,
        source: parsed.source,
        structured: parsed.structured,
      })
    }
    if (tab === 'target') return onChange(targetId ? { job_target_id: targetId } : null)
    return onChange(jobId ? { job_id: jobId } : null)
    // onChange is stable enough for this panel; re-run on the inputs only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, text, company, title, parsed, targetId, jobId])

  const run = async (action: () => Promise<JdParseResult>) => {
    setError(null)
    try {
      setParsed(await action())
    } catch (err) {
      setParsed(null)
      setError(errorMessage(err))
    }
  }

  const busy = parse.isPending || upload.isPending || fetchJd.isPending
  const savedTargets = (targets.data?.items ?? []).filter((t) => t.latest_snapshot_id)

  return (
    <div className="space-y-4">
      <Tabs value={tab} onValueChange={(value) => { setTab(value as JdTab); setParsed(null); setError(null) }}>
        <TabsList className="flex h-auto flex-wrap justify-start">
          <TabsTrigger value="paste"><ClipboardPaste aria-hidden />Paste</TabsTrigger>
          <TabsTrigger value="upload"><FileUp aria-hidden />Upload</TabsTrigger>
          <TabsTrigger value="url"><Link2 aria-hidden />URL</TabsTrigger>
          <TabsTrigger value="target"><Crosshair aria-hidden />Saved target</TabsTrigger>
          <TabsTrigger value="job"><Briefcase aria-hidden />Discovered job</TabsTrigger>
        </TabsList>

        <TabsContent value="paste" className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="jd-company">Company (optional)</Label>
              <Input id="jd-company" value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Acme" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="jd-title">Job title (optional)</Label>
              <Input id="jd-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Read from the posting when empty" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="jd-text">Job description</Label>
            <Textarea
              id="jd-text"
              value={text}
              onChange={(e) => { setText(e.target.value); setParsed(null) }}
              rows={10}
              placeholder="Paste the whole posting: responsibilities, requirements, nice-to-haves."
            />
            <p className="text-xs text-muted-foreground">
              {text.trim().length < MIN_CHARS ? `At least ${MIN_CHARS} characters (${text.trim().length} so far).` : `${text.length.toLocaleString()} characters.`} The text is treated as data only; instructions inside it are ignored.
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            disabled={text.trim().length < MIN_CHARS || busy}
            loading={parse.isPending}
            onClick={() => void run(() => parse.mutateAsync({ text, company: company || undefined, title: title || undefined, use_ai: useAi }))}
          >
            <Search aria-hidden />
            Preview requirements
          </Button>
        </TabsContent>

        <TabsContent value="upload" className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="jd-file">PDF, DOCX or TXT (max 5 MB)</Label>
            <Input
              id="jd-file"
              type="file"
              accept=".pdf,.docx,.txt,application/pdf,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              disabled={busy}
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) void run(() => upload.mutateAsync({ file, useAi }))
              }}
            />
          </div>
        </TabsContent>

        <TabsContent value="url" className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="jd-url">Job posting URL</Label>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input id="jd-url" type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://job-boards.greenhouse.io/company/jobs/123" />
              <Button disabled={!url.trim() || busy} loading={fetchJd.isPending} onClick={() => void run(() => fetchJd.mutateAsync({ url: url.trim(), use_ai: useAi }))}>
                Fetch
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Greenhouse, Lever, Ashby and SmartRecruiters postings are read from their public APIs. Other pages are fetched once;
              if nothing readable comes back, paste the text instead.
            </p>
          </div>
        </TabsContent>

        <TabsContent value="target" className="space-y-2">
          <Label>Saved job target</Label>
          <Select value={targetId} onValueChange={setTargetId}>
            <SelectTrigger aria-label="Saved job target">
              <SelectValue placeholder={savedTargets.length ? 'Choose a target' : 'No targets with a job description yet'} />
            </SelectTrigger>
            <SelectContent>
              {savedTargets.map((target) => (
                <SelectItem key={target.id} value={target.id}>
                  {target.role_title} · {target.company_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </TabsContent>

        <TabsContent value="job" className="space-y-2">
          <Label>Job discovered by JobPilot</Label>
          <Select value={jobId} onValueChange={setJobId}>
            <SelectTrigger aria-label="Discovered job">
              <SelectValue placeholder={jobs.data?.items.length ? 'Choose a job' : 'No discovered jobs yet'} />
            </SelectTrigger>
            <SelectContent>
              {(jobs.data?.items ?? []).map((job) => (
                <SelectItem key={job.id} value={job.id}>
                  {job.title} · {job.company.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </TabsContent>
      </Tabs>

      {tab === 'paste' || tab === 'upload' || tab === 'url' ? (
        <label className="flex items-center gap-2 text-sm">
          <Switch checked={useAi} onCheckedChange={setUseAi} aria-label="Refine requirements with AI" />
          Refine the requirements with your AI model
          <span className="text-xs text-muted-foreground">(slower; it can only re-classify what the posting says)</span>
        </label>
      ) : null}

      {busy ? <p className="text-sm text-muted-foreground" role="status">Reading the job description…</p> : null}
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {parsed ? <Preview result={parsed} /> : null}
    </div>
  )
}
