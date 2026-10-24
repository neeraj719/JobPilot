import type { ResumeParseStatus } from '@/types/api'

/** `GET /resumes/{id}/file-info` (backend `resumes.router_upload.ResumeFileInfo`). */
export interface ResumeFileInfo {
  resume_id: string
  has_file: boolean
  /** The stored bytes are gone: preview and download will fail. */
  file_missing: boolean
  original_filename: string | null
  mime_type: string | null
  format: 'pdf' | 'docx' | null
  size_bytes: number | null
  page_count: number | null
  /** PDF that needs a password to open. */
  encrypted: boolean
  uploaded_at: string | null
  previous_files: number
  /** A browser can show it inline (an unprotected PDF). */
  previewable: boolean
  parse_status: ResumeParseStatus
  extracted_text: string | null
  text_truncated: boolean
}

/** What happens after the upload: keep the file as the original, or review the extraction in the editor. */
export type AfterUpload = 'original' | 'editor'

export interface UploadProgress {
  /** 0–100 while bytes are going up; `null` before the first progress event. */
  percent: number | null
  /** `uploading` while bytes travel, `reading` once the server has them (extract + parse). */
  phase: 'idle' | 'uploading' | 'reading'
}
