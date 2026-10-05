export interface OcrFieldValue {
  value?: string | number | boolean | null
  confidence?: number
  source?: string
}

export interface ChatOcrPayload {
  job_id: string
  document_id: string
  document_type?: string | null
  fields: Record<string, OcrFieldValue | string | number | boolean | null>
  validation_status?: string | null
  pages?: Array<{ page?: number; text?: string; confidence?: number }>
}

export interface ChatMediaPayload {
  kind: 'audio' | 'video' | string
  engine?: string
  compressed?: boolean
}

export interface ChatAttachmentPayload {
  name: string
  type: string
  text: string
  content_type?: string
  size_bytes?: number
  ocr?: ChatOcrPayload
  media?: ChatMediaPayload
}

const MEDIA_EXTENSIONS = new Set([
  '.wav',
  '.mp3',
  '.m4a',
  '.aac',
  '.ogg',
  '.oga',
  '.flac',
  '.wma',
  '.mp4',
  '.mov',
  '.mkv',
  '.webm',
  '.avi',
  '.m4v',
])

export function isMediaFileName(name: string): boolean {
  return MEDIA_EXTENSIONS.has(extensionOf(name))
}

export function downloadTranscript(name: string, text: string) {
  const stem = name.replace(/\.[^.]+$/u, '') || 'transcript'
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${stem}.transcript.txt`
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

const OCR_EXTENSIONS = new Set([
  '.pdf',
  '.jpg',
  '.jpeg',
  '.png',
  '.tiff',
  '.tif',
])

function extensionOf(name: string): string {
  const idx = name.lastIndexOf('.')
  return idx >= 0 ? name.slice(idx).toLowerCase() : ''
}

export type ExtractChatAttachmentOptions = {
  /** Force OCR pipeline (images + PDF), even when auto would extract text only. */
  forceOcr?: boolean
  /** Hint for field extractor / classifier (e.g. passport). */
  documentType?: string
}

export async function extractChatAttachment(
  file: File,
  options: ExtractChatAttachmentOptions = {},
): Promise<ChatAttachmentPayload> {
  const ext = extensionOf(file.name)
  const forceOcr = Boolean(options.forceOcr)
  const useOcr =
    forceOcr
    || (OCR_EXTENSIONS.has(ext) && ext !== '.pdf')
    || (ext === '.pdf' && /passport|паспорт|scan|скан/i.test(file.name))

  const endpoint = useOcr
    ? '/api/v1/assistant/attachments/ocr'
    : '/api/v1/assistant/attachments/extract'

  const body = new FormData()
  body.append('file', file, file.name)
  if (useOcr) {
    body.append('mode', 'ocr')
    const hinted =
      options.documentType?.trim()
      || (/passport|паспорт/i.test(file.name) ? 'passport' : '')
    if (hinted) {
      body.append('document_type', hinted)
    }
  }

  const response = await fetch(endpoint, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'X-CSRFToken': csrfToken(),
    },
    body,
  })
  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const payload = (await response.json()) as {
        details?: { file?: string[] }
        error?: string
      }
      detail = payload.details?.file?.[0] || payload.error || detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return (await response.json()) as ChatAttachmentPayload
}

export function fieldConfidencePercent(
  field: OcrFieldValue | string | number | boolean | null | undefined,
): number | null {
  if (field && typeof field === 'object' && 'confidence' in field) {
    const conf = field.confidence
    if (typeof conf === 'number' && Number.isFinite(conf)) {
      return Math.round(conf * 100)
    }
  }
  return null
}

export function fieldDisplayValue(
  field: OcrFieldValue | string | number | boolean | null | undefined,
): string {
  if (field == null) return ''
  if (typeof field === 'object' && 'value' in field) {
    return field.value == null ? '' : String(field.value)
  }
  return String(field)
}
