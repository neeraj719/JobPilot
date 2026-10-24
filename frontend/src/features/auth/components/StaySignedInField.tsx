import type { Control, FieldValues, Path } from 'react-hook-form'

import { Checkbox } from '@/components/ui/checkbox'
import { FormControl, FormDescription, FormField, FormItem, FormLabel } from '@/components/ui/form'

/** "Stay signed in on this device" — shared by the sign-in and sign-up forms. */
export function StaySignedInField<T extends FieldValues & { remember_me: boolean }>({ control }: { control: Control<T> }) {
  return (
    <FormField
      control={control}
      name={'remember_me' as Path<T>}
      render={({ field }) => (
        <FormItem className="flex items-start gap-2 space-y-0">
          <FormControl>
            <Checkbox checked={field.value} onCheckedChange={(value) => field.onChange(value === true)} className="mt-0.5" />
          </FormControl>
          <div className="space-y-0.5">
            <FormLabel className="text-sm font-normal">Stay signed in on this device</FormLabel>
            <FormDescription className="text-xs [@media(max-height:800px)]:hidden">Keeps you signed in for 14 days. Only use on a device you own.</FormDescription>
          </div>
        </FormItem>
      )}
    />
  )
}
