import { Input } from '@/components/ui/input'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import type { FieldType } from '@/types/api'

export interface AnswerFieldProps {
  id: string
  fieldType: FieldType
  options: string[]
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  placeholder?: string
  'aria-label'?: string
}

const YES_NO = ['Yes', 'No']

const INPUT_TYPES: Partial<Record<FieldType, string>> = {
  EMAIL: 'email',
  PHONE: 'tel',
  NUMBER: 'number',
  DATE: 'date',
  URL: 'url',
}

/**
 * One editable answer control, picked from the field type the ATS reported.
 * Everything round-trips as a string because that is what the API stores.
 */
export function AnswerField({
  id,
  fieldType,
  options,
  value,
  onChange,
  disabled = false,
  placeholder,
  'aria-label': ariaLabel,
}: AnswerFieldProps) {
  const cleanOptions = (options ?? []).map((option) => String(option)).filter(Boolean)

  if (fieldType === 'TEXTAREA') {
    return (
      <Textarea
        id={id}
        rows={4}
        value={value}
        disabled={disabled}
        placeholder={placeholder ?? 'Your answer'}
        aria-label={ariaLabel}
        onChange={(event) => onChange(event.target.value)}
      />
    )
  }

  if (cleanOptions.length > 0 && (fieldType === 'SELECT' || fieldType === 'RADIO' || fieldType === 'CHECKBOX')) {
    if (fieldType === 'RADIO' || cleanOptions.length <= 3) {
      return (
        <RadioGroup
          value={value}
          onValueChange={onChange}
          disabled={disabled}
          aria-label={ariaLabel}
          className="flex flex-wrap gap-4"
        >
          {cleanOptions.map((option) => (
            <div key={option} className="flex items-center gap-2">
              <RadioGroupItem value={option} id={`${id}-${option}`} />
              <Label htmlFor={`${id}-${option}`} className="font-normal">
                {option}
              </Label>
            </div>
          ))}
        </RadioGroup>
      )
    }
    return (
      <Select value={value || undefined} onValueChange={onChange} disabled={disabled}>
        <SelectTrigger id={id} aria-label={ariaLabel}>
          <SelectValue placeholder="Choose an answer" />
        </SelectTrigger>
        <SelectContent>
          {cleanOptions.map((option) => (
            <SelectItem key={option} value={option}>
              {option}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    )
  }

  // A checkbox with no options is a yes/no question.
  if (fieldType === 'CHECKBOX') {
    return (
      <RadioGroup
        value={value}
        onValueChange={onChange}
        disabled={disabled}
        aria-label={ariaLabel}
        className="flex gap-4"
      >
        {YES_NO.map((option) => (
          <div key={option} className="flex items-center gap-2">
            <RadioGroupItem value={option} id={`${id}-${option}`} />
            <Label htmlFor={`${id}-${option}`} className="font-normal">
              {option}
            </Label>
          </div>
        ))}
      </RadioGroup>
    )
  }

  return (
    <Input
      id={id}
      type={INPUT_TYPES[fieldType] ?? 'text'}
      value={value}
      disabled={disabled}
      placeholder={placeholder ?? 'Your answer'}
      aria-label={ariaLabel}
      onChange={(event) => onChange(event.target.value)}
    />
  )
}
