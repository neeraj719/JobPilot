import { MAX_RESUME_BYTES, formatBytes } from '@/features/resume/api'
import type { ResumeRead } from '@/types/api'

export const RESUME_ACCEPT =
  '.pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document'

export interface FileProblem {
  code: 'type' | 'doc' | 'size' | 'empty' | 'not_pdf' | 'not_docx' | 'encrypted'
  message: string
}

function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.')
  return dot >= 0 ? name.slice(dot + 1).toLowerCase() : ''
}

function startsWith(bytes: Uint8Array, text: string): boolean {
  for (let i = 0; i < text.length; i += 1) if (bytes[i] !== text.charCodeAt(i)) return false
  return true
}

/** True when the bytes contain `/Encrypt` (the PDF trailer's encryption dictionary). */
function hasEncryptDictionary(bytes: Uint8Array): boolean {
  const needle = [0x2f, 0x45, 0x6e, 0x63, 0x72, 0x79, 0x70, 0x74] // "/Encrypt"
  outer: for (let i = 0; i <= bytes.length - needle.length; i += 1) {
    if (bytes[i] !== 0x2f) continue
    for (let j = 1; j < needle.length; j += 1) if (bytes[i + j] !== needle[j]) continue outer
    return true
  }
  return false
}

/**
 * Check a picked/dropped file before anything is sent: type by extension **and** first
 * bytes, size against `MAX_RESUME_BYTES`, and password-protected PDFs (which neither the
 * preview nor applicant tracking systems can read). The server checks again.
 */
export async function checkResumeFile(file: File): Promise<FileProblem | null> {
  const ext = extensionOf(file.name)
  if (ext === 'doc') {
    return { code: 'doc', message: 'Old Word .doc files are not supported. In Word choose Save as → .docx (or PDF) and upload that.' }
  }
  if (ext !== 'pdf' && ext !== 'docx') {
    return { code: 'type', message: `“${file.name}” is not a PDF or DOCX. Upload your resume as a PDF or Word (.docx) file.` }
  }
  if (file.size === 0) return { code: 'empty', message: 'That file is empty.' }
  if (file.size > MAX_RESUME_BYTES) {
    return {
      code: 'size',
      message: `That file is ${formatBytes(file.size)}; the limit is ${formatBytes(MAX_RESUME_BYTES)}. Export a smaller copy (fewer images) and try again.`,
    }
  }
  let bytes: Uint8Array
  try {
    bytes = new Uint8Array(await file.arrayBuffer())
  } catch {
    return null // unreadable here; the server decides
  }
  if (ext === 'pdf') {
    if (!startsWith(bytes, '%PDF')) return { code: 'not_pdf', message: 'That file is named .pdf but is not a PDF.' }
    if (hasEncryptDictionary(bytes)) {
      return {
        code: 'encrypted',
        message:
          'This PDF is password-protected or encrypted, so we cannot preview it and applicant tracking systems often cannot read it. Open it, choose Print → Save as PDF, and upload the new copy.',
      }
    }
  }
  if (ext === 'docx' && !startsWith(bytes, 'PK')) {
    return { code: 'not_docx', message: 'That file is named .docx but is not a Word document.' }
  }
  return null
}

/** `Backend CV.pdf` -> `Backend CV`. */
export function nameFromFile(file: File | null): string {
  if (!file) return ''
  const base = file.name.replace(/\.[^.]+$/, '')
  return base.replace(/[_]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 255)
}

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`
}

/** The parse result in one line: "We read 4 roles, 2 degrees, 18 skills". */
export function parseSummary(resume: Pick<ResumeRead, 'parse_status' | 'parsed_data'>): { ok: boolean; text: string } {
  const data = (resume.parsed_data ?? {}) as { experience?: unknown[]; education?: unknown[]; skills?: unknown[] }
  const bits: string[] = []
  if (data.experience?.length) bits.push(plural(data.experience.length, 'role', 'roles'))
  if (data.education?.length) bits.push(plural(data.education.length, 'degree', 'degrees'))
  if (data.skills?.length) bits.push(plural(data.skills.length, 'skill', 'skills'))
  if (resume.parse_status !== 'PARSED' || bits.length === 0) {
    return { ok: false, text: 'We could not read everything — you can still use the file.' }
  }
  return { ok: true, text: `We read ${bits.join(', ')}.` }
}
