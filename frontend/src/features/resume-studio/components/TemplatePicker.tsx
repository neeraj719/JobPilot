import { Check } from 'lucide-react'

import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

import type { ResumeTemplate, StudioResume } from '../types'
import { ResumePreview } from './ResumePreview'

/** Placeholder content for the thumbnails (never saved). */
export const SAMPLE_PREVIEW: StudioResume = {
  name: 'Alex Morgan',
  headline: 'Software Engineer',
  email: 'alex@example.com',
  phone: '+1 555 0100',
  location: 'Remote',
  summary: 'Software engineer who builds reliable web products end to end.',
  skills: ['TypeScript', 'React', 'Node.js', 'PostgreSQL', 'Docker'],
  experience: [
    {
      company: 'Example Co',
      title: 'Software Engineer',
      start: '2022-01',
      end: 'Present',
      description: 'Built the customer dashboard\nDesigned the billing API',
      technologies: [],
    },
  ],
  projects: [],
  education: [{ institution: 'State University', degree: 'B.S.', field: 'Computer Science', start: '2017', end: '2021' }],
  certifications: [],
  achievements: [],
  languages: [],
  section_order: [],
  links: {},
}

export interface TemplatePickerProps {
  templates: ResumeTemplate[] | undefined
  value: string
  onChange: (id: string) => void
  loading?: boolean
  /** Thumbnails show this data instead of the sample. */
  data?: Partial<StudioResume>
  className?: string
}

/** Radio group of templates with live mini previews. */
export function TemplatePicker({ templates, value, onChange, loading, data, className }: TemplatePickerProps) {
  if (loading || !templates) {
    return (
      <div className={cn('grid gap-3 sm:grid-cols-3', className)}>
        {Array.from({ length: 3 }, (_, i) => (
          <Skeleton key={i} className="h-56" />
        ))}
      </div>
    )
  }
  return (
    <div role="radiogroup" aria-label="Template" className={cn('grid gap-3 sm:grid-cols-3', className)}>
      {templates.map((tpl) => {
        const selected = tpl.id === value
        return (
          <button
            key={tpl.id}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(tpl.id)}
            className={cn(
              'group flex flex-col overflow-hidden rounded-lg border bg-card text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              selected ? 'border-primary ring-1 ring-primary/40' : 'border-border hover:border-primary/40',
            )}
          >
            <div className="relative h-40 overflow-hidden bg-muted/60 px-3 pt-3" aria-hidden>
              <ResumePreview data={data && data.name ? data : SAMPLE_PREVIEW} template={tpl} scale={0.27} bare />
              {selected ? (
                <span className="absolute right-2 top-2 flex size-6 items-center justify-center rounded-full bg-primary text-primary-foreground">
                  <Check className="size-4" />
                </span>
              ) : null}
            </div>
            <div className="space-y-0.5 p-3">
              <p className="text-sm font-semibold">{tpl.name}</p>
              <p className="line-clamp-2 text-xs text-muted-foreground">{tpl.description}</p>
            </div>
          </button>
        )
      })}
    </div>
  )
}
