/**
 * One scale for every auth form (both modals and the `/login` `/register` pages), sized for the
 * wide dialog (576 px): 48 px fields with 16 px text and 16 px side padding, 14 px semibold
 * labels 8 px above the field, 20 px between fields, a 48 px full-width gradient submit.
 *
 * Short viewports tighten the vertical rhythm so the whole register modal fits without
 * scrolling (`max-h-[92svh]` stays as the last resort): ≤ 900 px tall → 16 px between fields;
 * ≤ 800 px tall → 12 px between fields, 6 px label gap, 44 px fields and submit.
 */
export const AUTH_FORM = 'space-y-5 [@media(min-height:801px)_and_(max-height:900px)]:space-y-4 [@media(max-height:800px)]:space-y-3'
export const AUTH_ITEM = 'space-y-2 [@media(max-height:800px)]:space-y-1.5'
export const AUTH_LABEL = 'text-sm font-semibold'
export const AUTH_INPUT = 'h-12 rounded-xl px-4 text-base [@media(max-height:800px)]:h-11'
export const AUTH_SUBMIT =
  'h-12 w-full rounded-xl text-base hover:-translate-y-0.5 motion-reduce:hover:translate-y-0 dark:shadow-glow [@media(max-height:800px)]:h-11'
/** A two-column row of fields (first + last name) with the same gap as the stack. */
export const AUTH_ROW_GAP = 'gap-5 [@media(min-height:801px)_and_(max-height:900px)]:gap-4 [@media(max-height:800px)]:gap-3'
