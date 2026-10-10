import { EMAIL_CLASSIFICATION_LABELS, cn, emailClassificationColor } from '@/lib/utils'
import type { EmailClassification } from '@/types/api'

export interface ClassificationBadgeProps {
  classification: EmailClassification
  confidence?: number | null
  className?: string
  size?: 'sm' | 'md'
}

/** Colour-coded pill for what the classifier decided an email is. */
export function ClassificationBadge({ classification, confidence, className, size = 'md' }: ClassificationBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 whitespace-nowrap rounded-full border font-medium',
        size === 'sm' ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-0.5 text-xs',
        emailClassificationColor(classification),
        className,
      )}
    >
      {EMAIL_CLASSIFICATION_LABELS[classification] ?? classification}
      {confidence !== null && confidence !== undefined ? (
        <span className="opacity-70 tabular-nums">{Math.round(confidence * 100)}%</span>
      ) : null}
    </span>
  )
}
