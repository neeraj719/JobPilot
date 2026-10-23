import { z } from 'zod'

/** Settings › Workspace: where `/home` sends you after sign-in, and launcher tips. */
export const workspacePreferencesSchema = z.object({
  landing: z.enum(['LAUNCHER', 'LAST_MODULE']),
  show_tips: z.boolean(),
})

export type WorkspacePreferencesValues = z.infer<typeof workspacePreferencesSchema>

/** Settings › Admin: find an account by its exact email. */
export const adminUserLookupSchema = z.object({
  email: z.string().trim().min(1, 'Enter an email address').email('Enter a valid email address').max(255),
})

export type AdminUserLookupValues = z.infer<typeof adminUserLookupSchema>
