import * as React from 'react'
import type { FieldValues, UseFormReset } from 'react-hook-form'

/**
 * Re-seed a section form when the server data behind it changes — but only while the user
 * has no unsaved edits, so a background refetch can never wipe what they are typing.
 *
 * After a successful save, call `reset(...)` yourself with the response so the form goes
 * pristine again.
 */
export function useSyncDefaults<T extends FieldValues>(defaults: T, isDirty: boolean, reset: UseFormReset<T>): void {
  const isDirtyRef = React.useRef(isDirty)
  isDirtyRef.current = isDirty

  React.useEffect(() => {
    if (!isDirtyRef.current) reset(defaults)
  }, [defaults, reset])
}
