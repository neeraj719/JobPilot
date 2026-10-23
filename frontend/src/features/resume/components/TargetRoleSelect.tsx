import * as React from 'react'

import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { useJobPreferences } from '@/features/profile/api'

/** Common roles offered after the user's own preferred titles. */
export const COMMON_TARGET_ROLES: readonly string[] = [
  'Software Engineer',
  'Senior Software Engineer',
  'Full Stack Engineer',
  'Frontend Engineer',
  'Backend Engineer',
  'React Developer',
  'Node.js Developer',
  'Python Developer',
  'Java Developer',
  'Mobile Developer',
  'DevOps Engineer',
  'Site Reliability Engineer',
  'Cloud Engineer',
  'Data Engineer',
  'Data Analyst',
  'Data Scientist',
  'Machine Learning Engineer',
  'AI Engineer',
  'QA Engineer',
  'Product Manager',
  'Engineering Manager',
]

const NONE = '__none__'
const OTHER = '__other__'

export interface TargetRoleSelectProps {
  value: string | null | undefined
  /** Called with the chosen role, or `null` for "No target role". */
  onChange: (role: string | null) => void
  id?: string
  disabled?: boolean
  size?: 'sm' | 'default'
  className?: string
  /** Show a "No target role" option (useful when editing an existing resume). */
  allowNone?: boolean
}

/**
 * Target role picker: the user's own preferred titles first, then common roles, plus
 * "Other…" for a custom title typed in place.
 */
export function TargetRoleSelect({
  value,
  onChange,
  id,
  disabled,
  size = 'default',
  className,
  allowNone = false,
}: TargetRoleSelectProps) {
  const preferences = useJobPreferences()
  const preferred = React.useMemo(() => {
    const titles = (preferences.data?.desired_titles ?? []).map((title) => String(title).trim()).filter(Boolean)
    return Array.from(new Set(titles))
  }, [preferences.data])

  const known = React.useMemo(() => {
    const all = new Set<string>([...preferred, ...COMMON_TARGET_ROLES].map((role) => role.toLowerCase()))
    return all
  }, [preferred])
  const common = COMMON_TARGET_ROLES.filter((role) => !preferred.some((title) => title.toLowerCase() === role.toLowerCase()))

  const current = (value ?? '').trim()
  const isCustom = current !== '' && !known.has(current.toLowerCase())
  const [typing, setTyping] = React.useState(false)
  const [draft, setDraft] = React.useState(current)
  React.useEffect(() => setDraft(current), [current])

  const selectValue = typing ? OTHER : current === '' ? (allowNone ? NONE : '') : current

  const commitDraft = () => {
    const next = draft.trim()
    setTyping(false)
    if (next !== current) onChange(next || null)
  }

  const triggerClass = cn(size === 'sm' ? 'h-8 text-xs' : 'h-9', className)

  if (typing) {
    return (
      <Input
        id={id}
        autoFocus
        value={draft}
        disabled={disabled}
        placeholder="Type a role, then press Enter"
        className={triggerClass}
        onClick={(event) => event.stopPropagation()}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commitDraft}
        onKeyDown={(event) => {
          event.stopPropagation()
          if (event.key === 'Enter') commitDraft()
          if (event.key === 'Escape') {
            setDraft(current)
            setTyping(false)
          }
        }}
        aria-label="Custom target role"
      />
    )
  }

  return (
    <Select
      value={selectValue}
      disabled={disabled}
      onValueChange={(next) => {
        if (next === OTHER) {
          setDraft(isCustom ? current : '')
          setTyping(true)
        } else if (next === NONE) {
          onChange(null)
        } else if (next !== current) {
          onChange(next)
        }
      }}
    >
      <SelectTrigger id={id} className={triggerClass} onClick={(event) => event.stopPropagation()} aria-label="Target role">
        <SelectValue placeholder="Choose a target role" />
      </SelectTrigger>
      <SelectContent onClick={(event) => event.stopPropagation()}>
        {allowNone ? (
          <>
            <SelectItem value={NONE}>No target role</SelectItem>
            <SelectSeparator />
          </>
        ) : null}
        {isCustom ? (
          <SelectGroup>
            <SelectLabel>Current</SelectLabel>
            <SelectItem value={current}>{current}</SelectItem>
          </SelectGroup>
        ) : null}
        {preferred.length > 0 ? (
          <SelectGroup>
            <SelectLabel>Your preferred roles</SelectLabel>
            {preferred.map((role) => (
              <SelectItem key={`pref-${role}`} value={role}>
                {role}
              </SelectItem>
            ))}
          </SelectGroup>
        ) : null}
        <SelectGroup>
          <SelectLabel>Common roles</SelectLabel>
          {common.map((role) => (
            <SelectItem key={role} value={role}>
              {role}
            </SelectItem>
          ))}
        </SelectGroup>
        <SelectSeparator />
        <SelectItem value={OTHER}>Other…</SelectItem>
      </SelectContent>
    </Select>
  )
}
