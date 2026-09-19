import { AlertTriangle, CheckCircle2, CircleDashed, HelpCircle, Loader2, PauseCircle } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import { automationStateColor, cn, humanizeEnum } from '@/lib/utils'
import type { ApplicationRead, AutomationState, PauseReason } from '@/types/api'

export interface AutomationSummary {
  label: string
  /** One sentence explaining what the user should do next (or what happened). */
  detail: string
  icon: LucideIcon
  className: string
  spinning: boolean
  /** True when the automation is waiting on the human. */
  needsUser: boolean
}

/** Human-readable reason a run paused — never suggests working around a security step. */
export const PAUSE_REASON_LABELS: Record<PauseReason, string> = {
  CAPTCHA: 'A CAPTCHA must be solved by you',
  OTP: 'A one-time code was sent to you',
  TWO_FACTOR: 'Two-factor authentication is required',
  LOGIN_REQUIRED: 'The site needs you to sign in',
  ACCOUNT_REGISTRATION_REQUIRED: 'The site needs an account you have to create',
  UNKNOWN_QUESTION: 'The form asks something we cannot answer for you',
  LEGAL_DECLARATION: 'A legal declaration needs your confirmation',
  WORK_AUTHORIZATION: 'A work-authorization question needs your answer',
  DEMOGRAPHIC_QUESTION: 'A voluntary demographic question needs your choice',
  USER_REVIEW: 'Filled in and waiting for your review',
  WEBSITE_CHANGED: 'The application page changed since we last saw it',
  OTHER: 'Automation paused and needs you',
}

/** Pause reasons that mean "a human must complete a security step on the site itself". */
export const MANUAL_STEP_REASONS: readonly PauseReason[] = [
  'CAPTCHA',
  'OTP',
  'TWO_FACTOR',
  'LOGIN_REQUIRED',
  'ACCOUNT_REGISTRATION_REQUIRED',
]

export function isManualStepPause(reason: PauseReason | null | undefined): boolean {
  return Boolean(reason && MANUAL_STEP_REASONS.includes(reason))
}

/**
 * Collapse `automation_state` + `pause_reason` + `ready` into the single status the
 * queue table and the Approval Center header both show.
 */
export function automationSummary(
  application: Pick<ApplicationRead, 'automation_state' | 'pause_reason' | 'pause_message' | 'last_error' | 'status'> & {
    ready?: boolean
  },
): AutomationSummary {
  const state: AutomationState = application.automation_state
  const className = automationStateColor(state)

  switch (state) {
    case 'RUNNING':
    case 'RETRYING':
      return {
        label: state === 'RETRYING' ? 'Retrying' : 'In progress',
        detail: 'The browser is filling the application form right now.',
        icon: Loader2,
        className,
        spinning: true,
        needsUser: false,
      }
    case 'PAUSED':
      return {
        label: application.pause_reason === 'USER_REVIEW' ? 'Ready for your review' : 'Paused',
        detail:
          application.pause_message ||
          (application.pause_reason ? PAUSE_REASON_LABELS[application.pause_reason] : 'Automation is paused.'),
        icon: PauseCircle,
        className,
        spinning: false,
        needsUser: true,
      }
    case 'REQUIRES_USER':
      return {
        label: 'Needs your input',
        detail:
          application.pause_message ||
          (application.pause_reason ? PAUSE_REASON_LABELS[application.pause_reason] : 'An answer is missing.'),
        icon: HelpCircle,
        className,
        spinning: false,
        needsUser: true,
      }
    case 'FAILED':
      return {
        label: 'Failed',
        detail: application.last_error || 'The last automation run failed.',
        icon: AlertTriangle,
        className,
        spinning: false,
        needsUser: true,
      }
    case 'SUCCESS':
      return {
        label: 'Submitted',
        detail: 'The application was submitted successfully.',
        icon: CheckCircle2,
        className,
        spinning: false,
        needsUser: false,
      }
    default:
      return {
        label: application.ready ? 'Ready' : 'Not started',
        detail: application.ready
          ? 'Every required answer is prepared — start the application when you are ready.'
          : 'Answers have not been prepared yet. Start the application to generate them.',
        icon: CircleDashed,
        className,
        spinning: false,
        needsUser: false,
      }
  }
}

export interface AutomationBadgeProps {
  application: Parameters<typeof automationSummary>[0]
  className?: string
  /** Show the explanation next to the pill (used in the detail header). */
  showDetail?: boolean
}

export function AutomationBadge({ application, className, showDetail = false }: AutomationBadgeProps) {
  const summary = automationSummary(application)
  const Icon = summary.icon

  return (
    <span className={cn('inline-flex items-center gap-2', className)}>
      <span
        className={cn(
          'inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium',
          summary.className,
        )}
        title={summary.detail}
      >
        <Icon className={cn('size-3', summary.spinning && 'animate-spin')} aria-hidden />
        {summary.label}
      </span>
      {showDetail ? <span className="text-xs text-muted-foreground">{summary.detail}</span> : null}
    </span>
  )
}

/** `USER_REVIEW` -> `User review`, for the rare reason with no hand-written label. */
export function pauseReasonLabel(reason: PauseReason | null | undefined): string {
  if (!reason) return ''
  return PAUSE_REASON_LABELS[reason] ?? humanizeEnum(reason)
}
