/** Small presentation helpers shared by the Approval Center panels. */

/**
 * ATS forms often bake the required marker into the label itself
 * (`"Notice Period *"`). We render our own red asterisk, so strip theirs.
 */
export function questionLabel(text: string | null | undefined, fallback = 'Question'): string {
  if (!text) return fallback
  return text.replace(/[\s*:]+$/, '').trim() || fallback
}
