import { Check } from 'lucide-react'

import { SkeletonLine, SkeletonRegion } from '@/components/common/skeletons'
import { Skeleton } from '@/components/ui/skeleton'
import { tiltHandlers } from '@/lib/tilt'
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
      <SkeletonRegion label="Loading templates" className={cn('grid gap-3 sm:grid-cols-3', className)}>
        {Array.from({ length: 3 }, (_, i) => (
          <div key={i} className="flex flex-col overflow-hidden rounded-lg border border-border bg-card" aria-hidden>
            <div className="h-40 overflow-hidden bg-muted/60 px-3 pt-3">
              {/* The 0.27-scale page preview (794 px × 0.27). */}
              <Skeleton className="h-full w-[214px] max-w-full rounded-b-none rounded-t-sm" />
            </div>
            <div className="space-y-0.5 p-3">
              <SkeletonLine size="sm" className="w-24" />
              <SkeletonLine size="xs" className="w-full" />
              <SkeletonLine size="xs" className="w-2/3" />
            </div>
          </div>
        ))}
      </SkeletonRegion>
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
            {...tiltHandlers(true, { x: 5, y: 7, lift: 2 })}
            className={cn(
              // v2: CSS 3D tilt on hover; the selected template gets the gradient edge.
              'tilt group flex flex-col overflow-hidden rounded-xl text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              selected ? 'border-gradient shadow-glow' : 'border border-border bg-card hover:border-primary/40 hover:shadow-md',
            )}
          >
            <div className="relative h-40 overflow-hidden bg-muted/60 px-3 pt-3" aria-hidden>
              <ResumePreview data={data && data.name ? data : SAMPLE_PREVIEW} template={tpl} scale={0.27} bare />
              {selected ? (
                <span className="absolute right-2 top-2 flex size-6 items-center justify-center rounded-full bg-gradient-brand text-gradient-foreground shadow-sm">
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
