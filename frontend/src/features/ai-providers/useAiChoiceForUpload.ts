import { useAiChoice } from '@/features/ai-providers/useAiChoice'

/**
 * Model choice for "upload my original resume" (the parse may call the AI model).
 *
 * For `features/resume-upload/UploadResumeSheet.tsx` (owned by the resume-upload stream):
 *
 *     const parseChoice = useAiChoiceForUpload()
 *     ...
 *     const resume = await parseChoice.runWithModel((ai) => upload.mutateAsync({ ...input, ai }))
 *     if (!resume) return // the user cancelled the "Which model?" dialog
 *
 * With one usable model (or "always use my routing") it runs at once with `ai` undefined.
 */
export function useAiChoiceForUpload() {
  return useAiChoice('parse_resume', { context: 'The text read from your resume file' })
}
