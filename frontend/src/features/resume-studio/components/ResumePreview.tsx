import * as React from 'react'

import { cn } from '@/lib/utils'

import { buildLayout, contactLine } from '../layout'
import type { ResumeTemplate, StudioResume } from '../types'

/** A4 at 96 dpi. The page is drawn at this size and scaled, so zoom never re-flows text. */
export const PAGE_WIDTH_PX = 794
export const PAGE_HEIGHT_PX = 1123

export interface ResumePreviewProps {
  data: Partial<StudioResume>
  template: ResumeTemplate
  /** 1 = 100 %. */
  scale?: number
  className?: string
  /** Hide page-break guides (thumbnails). */
  bare?: boolean
}

/**
 * Print-like preview drawn from the template *definition* — the same layout rules the
 * PDF/DOCX exporters follow (`layout.ts` mirrors `render.build_layout`). Always paper
 * white with dark ink, in both themes, because that is what gets exported.
 */
export function ResumePreview({ data, template, scale = 1, className, bare = false }: ResumePreviewProps) {
  const layout = React.useMemo(() => buildLayout(data, template), [data, template])
  const pageRef = React.useRef<HTMLDivElement>(null)
  const [height, setHeight] = React.useState(PAGE_HEIGHT_PX)

  React.useLayoutEffect(() => {
    const node = pageRef.current
    if (!node) return
    const update = () => setHeight(Math.max(PAGE_HEIGHT_PX, node.scrollHeight))
    update()
    const observer = new ResizeObserver(update)
    observer.observe(node)
    return () => observer.disconnect()
  }, [layout])

  const { sizes, spacing } = template
  const pt = (value: number) => `${value}pt`
  const align = template.header_layout === 'centered' ? 'center' : 'left'
  const headingColor = template.heading_style === 'accent-rule' ? template.accent : '#000000'
  const ruleColor = template.heading_style === 'accent-rule' ? template.accent : '#9ca3af'
  const pages = Math.ceil(height / PAGE_HEIGHT_PX)
  const contacts = contactLine(layout, template)

  return (
    <div
      className={cn('relative mx-auto', className)}
      style={{ width: PAGE_WIDTH_PX * scale, height: height * scale }}
    >
      <div
        ref={pageRef}
        aria-label="Resume preview"
        role="document"
        className="absolute left-0 top-0 origin-top-left bg-white text-black shadow-md ring-1 ring-black/5"
        style={{
          width: PAGE_WIDTH_PX,
          minHeight: PAGE_HEIGHT_PX,
          transform: `scale(${scale})`,
          padding: `${spacing.margin_in}in`,
          fontFamily: template.fonts.css,
          fontSize: pt(sizes.body),
          lineHeight: spacing.line_height,
          // Page-break guides: a faint dashed line where each A4 page ends.
          backgroundImage: bare
            ? undefined
            : `repeating-linear-gradient(to bottom, transparent 0, transparent ${PAGE_HEIGHT_PX - 1}px, #e5e7eb ${PAGE_HEIGHT_PX - 1}px, #e5e7eb ${PAGE_HEIGHT_PX}px)`,
        }}
      >
        <header style={{ textAlign: align }}>
          <div style={{ fontFamily: template.heading_fonts.css, fontSize: pt(sizes.name), fontWeight: 700, lineHeight: 1.2 }}>
            {layout.name}
          </div>
          {layout.headline && template.header_layout !== 'two-line' ? (
            <div style={{ fontSize: pt(sizes.headline), lineHeight: 1.3 }}>{layout.headline}</div>
          ) : null}
          {contacts ? <div style={{ fontSize: pt(sizes.small), marginTop: 2, wordBreak: 'break-word' }}>{contacts}</div> : null}
        </header>

        {layout.sections.map((section) => (
          <section key={section.key} aria-label={section.label}>
            <h2
              style={{
                fontFamily: template.heading_fonts.css,
                fontSize: pt(sizes.heading),
                fontWeight: 700,
                color: headingColor,
                marginTop: pt(spacing.section_before),
                marginBottom: pt(template.heading_style === 'bold' ? spacing.section_after : 1),
                paddingBottom: template.heading_style === 'bold' ? 0 : 1,
                borderBottom: template.heading_style === 'bold' ? undefined : `0.6pt solid ${ruleColor}`,
                textTransform: template.heading_style === 'caps-rule' ? 'uppercase' : undefined,
                letterSpacing: template.heading_style === 'caps-rule' ? '0.04em' : undefined,
              }}
            >
              {section.label}
            </h2>
            <div style={{ marginTop: template.heading_style === 'bold' ? 0 : pt(spacing.section_after) }}>
              {section.paragraph ? <p>{section.paragraph}</p> : null}
              {section.inline ? <p>{section.inline}</p> : null}
              {section.bullets.length ? <BulletList items={section.bullets} template={template} /> : null}
              {section.entries.map((entry, index) => (
                <div key={index} style={{ marginTop: index ? pt(spacing.entry_gap) : 0, breakInside: 'avoid' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                    <span>
                      <strong>{entry.title}</strong>
                      {entry.detail ? <span>{` | ${entry.detail}`}</span> : null}
                    </span>
                    {entry.dates ? <span style={{ whiteSpace: 'nowrap' }}>{entry.dates}</span> : null}
                  </div>
                  {entry.meta ? <div style={{ fontSize: pt(sizes.small), fontStyle: 'italic' }}>{entry.meta}</div> : null}
                  {entry.bullets.length ? <BulletList items={entry.bullets} template={template} /> : null}
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
      {!bare && pages > 1 ? (
        <p className="pointer-events-none absolute -bottom-6 right-0 text-xs text-muted-foreground">{pages} pages</p>
      ) : null}
    </div>
  )
}

function BulletList({ items, template }: { items: string[]; template: ResumeTemplate }) {
  return (
    <ul style={{ margin: 0, paddingLeft: `${template.spacing.bullet_indent}pt`, listStyleType: 'disc' }}>
      {items.map((item, index) => (
        <li key={index} style={{ paddingLeft: 2 }}>
          {item}
        </li>
      ))}
    </ul>
  )
}
