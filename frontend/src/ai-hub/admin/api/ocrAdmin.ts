import { ensureCsrfToken, ensureDevSession, isAuthErrorMessage } from '../../../auth/ensureDevSession'

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

async function ocrFetch(input: string, init: RequestInit = {}): Promise<Response> {
  await ensureDevSession()
  const headers = new Headers(init.headers)
  if ((init.method || 'GET').toUpperCase() !== 'GET') {
    const token = await ensureCsrfToken() || csrfToken()
    if (token) headers.set('X-CSRFToken', token)
  }
  const response = await fetch(input, {
    ...init,
    credentials: 'include',
    headers,
  })
  if (response.ok || !isAuthErrorMessage(`HTTP ${response.status}`)) {
    return response
  }
  await ensureDevSession()
  const retryHeaders = new Headers(init.headers)
  if ((init.method || 'GET').toUpperCase() !== 'GET') {
    const token = await ensureCsrfToken(true) || csrfToken()
    if (token) retryHeaders.set('X-CSRFToken', token)
  }
  return fetch(input, {
    ...init,
    credentials: 'include',
    headers: retryHeaders,
  })
}

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as {
      details?: { request?: string[] }
      error?: string
    }
    return payload.details?.request?.[0] || payload.error || `HTTP ${response.status}`
  } catch {
    return `HTTP ${response.status}`
  }
}

export interface OcrTemplateSample {
  id: number
  filename: string
  content_type?: string
  ocr_text?: string
  expected_fields?: Record<string, unknown>
  notes?: string
  created_by?: string
  created_at?: string | null
}

export interface OcrTemplate {
  id: number
  doc_type: string
  title: string
  description?: string
  template_version: number
  status: 'draft' | 'published' | 'archived' | string
  required_fields: string[]
  field_schema: Record<string, unknown>
  confidence_min: number
  sample_prompt?: string
  owner?: string
  published_at?: string | null
  updated_at?: string | null
  sample_count?: number
  samples?: OcrTemplateSample[]
}

export interface OcrDocType {
  doc_type: string
  title: string
  template_version?: string | number
  required_fields?: string[]
  confidence_min?: number
  status?: string
  field_schema?: Record<string, unknown>
}

export async function listOcrDocTypes(): Promise<OcrDocType[]> {
  const response = await ocrFetch('/api/v1/ocr/doc-types/')
  if (!response.ok) throw new Error(await parseError(response))
  const payload = (await response.json()) as { items?: OcrDocType[] }
  return payload.items ?? []
}

export async function listOcrTemplates(): Promise<OcrTemplate[]> {
  const response = await fetch('/api/v1/ocr/templates/?seed=1', {
    credentials: 'include',
  })
  if (!response.ok) throw new Error(await parseError(response))
  const payload = (await response.json()) as { items?: OcrTemplate[] }
  return payload.items ?? []
}

export async function saveOcrTemplate(
  input: Partial<OcrTemplate> & { doc_type: string; publish?: boolean },
): Promise<OcrTemplate> {
  const response = await fetch('/api/v1/ocr/templates/', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
    },
    body: JSON.stringify(input),
  })
  if (!response.ok) throw new Error(await parseError(response))
  return (await response.json()) as OcrTemplate
}

export async function updateOcrTemplate(
  docType: string,
  input: Partial<OcrTemplate> & { publish?: boolean; bump_version?: boolean },
): Promise<OcrTemplate> {
  const response = await fetch(`/api/v1/ocr/templates/${encodeURIComponent(docType)}/`, {
    method: 'PUT',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
    },
    body: JSON.stringify(input),
  })
  if (!response.ok) throw new Error(await parseError(response))
  return (await response.json()) as OcrTemplate
}

export async function uploadTemplateSample(
  docType: string,
  file: File,
  expectedFields?: Record<string, unknown>,
  notes = '',
): Promise<Record<string, unknown>> {
  const body = new FormData()
  body.append('file', file, file.name)
  if (expectedFields) {
    body.append('expected_fields', JSON.stringify(expectedFields))
  }
  if (notes) body.append('notes', notes)
  const response = await fetch(
    `/api/v1/ocr/templates/${encodeURIComponent(docType)}/samples/`,
    {
      method: 'POST',
      credentials: 'include',
      headers: { 'X-CSRFToken': csrfToken() },
      body,
    },
  )
  if (!response.ok) throw new Error(await parseError(response))
  return (await response.json()) as Record<string, unknown>
}

export async function listOcrJobs(limit = 40): Promise<Array<Record<string, unknown>>> {
  const response = await ocrFetch(`/api/v1/ocr/jobs/?limit=${limit}`)
  if (!response.ok) throw new Error(await parseError(response))
  const payload = (await response.json()) as { items?: Array<Record<string, unknown>> }
  return payload.items ?? []
}

export async function uploadOcrDocument(
  file: File,
  documentType = '',
  sync = true,
  userTemplateId?: number,
): Promise<Record<string, unknown>> {
  const body = new FormData()
  body.append('file', file, file.name)
  if (userTemplateId) {
    body.append('user_template_id', String(userTemplateId))
  } else if (documentType) {
    body.append('document_type', documentType)
  }
  if (sync) body.append('sync', '1')
  const response = await ocrFetch('/api/v1/ocr/documents/', {
    method: 'POST',
    body,
  })
  if (!response.ok) throw new Error(await parseError(response))
  return (await response.json()) as Record<string, unknown>
}

export interface OcrUserTemplateField {
  key: string
  label: string
  type?: string
  pattern?: string
}

export interface OcrUserTemplate {
  id: number
  name: string
  fields: OcrUserTemplateField[]
  source_job_id?: string
  source_file?: string
  created_at?: string | null
  updated_at?: string | null
}

export async function listMyOcrTemplates(): Promise<OcrUserTemplate[]> {
  const response = await ocrFetch('/api/v1/ocr/my-templates/')
  if (!response.ok) throw new Error(await parseError(response))
  const payload = (await response.json()) as { items?: OcrUserTemplate[] }
  return payload.items ?? []
}

export async function createMyOcrTemplate(
  jobId: string,
  name: string,
): Promise<OcrUserTemplate> {
  const response = await ocrFetch('/api/v1/ocr/my-templates/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_id: jobId, name }),
  })
  if (!response.ok) throw new Error(await parseError(response))
  return (await response.json()) as OcrUserTemplate
}

export async function renameMyOcrTemplate(
  templateId: number,
  name: string,
): Promise<OcrUserTemplate> {
  return updateMyOcrTemplate(templateId, { name })
}

export async function updateMyOcrTemplate(
  templateId: number,
  input: { name?: string; fields?: OcrUserTemplateField[] },
): Promise<OcrUserTemplate> {
  const response = await ocrFetch(`/api/v1/ocr/my-templates/${templateId}/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!response.ok) throw new Error(await parseError(response))
  return (await response.json()) as OcrUserTemplate
}

export async function deleteMyOcrTemplate(templateId: number): Promise<void> {
  const response = await ocrFetch(`/api/v1/ocr/my-templates/${templateId}/`, {
    method: 'DELETE',
  })
  if (!response.ok) throw new Error(await parseError(response))
}

export async function fetchOcrResult(jobId: string): Promise<Record<string, unknown>> {
  const response = await ocrFetch(`/api/v1/ocr/jobs/${encodeURIComponent(jobId)}/result/`)
  if (!response.ok) throw new Error(await parseError(response))
  return (await response.json()) as Record<string, unknown>
}

export function ocrJobOriginalUrl(jobId: string): string {
  return `/api/v1/ocr/jobs/${encodeURIComponent(jobId)}/original/`
}

export async function approveOcrJob(
  jobId: string,
  documentType: string,
  fields: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const response = await ocrFetch(`/api/v1/ocr/jobs/${encodeURIComponent(jobId)}/approve/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ document_type: documentType, fields }),
  })
  if (!response.ok && response.status !== 422) {
    throw new Error(await parseError(response))
  }
  return (await response.json()) as Record<string, unknown>
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function filenameFromDisposition(header: string | null, fallback: string) {
  const value = header || ''
  const utfMatch = value.match(/filename\*=UTF-8''([^;]+)/i)
  const asciiMatch = value.match(/filename="([^"]+)"/i)
  return decodeURIComponent(utfMatch?.[1] || asciiMatch?.[1] || fallback)
}

function fieldPlain(raw: unknown): string {
  if (raw == null) return ''
  if (typeof raw === 'object' && raw !== null && 'value' in raw) {
    const value = (raw as { value?: unknown }).value
    return value == null ? '' : String(value)
  }
  return String(raw)
}

function encodeUtf8(text: string): Uint8Array {
  return new TextEncoder().encode(text)
}

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff
  for (const byte of bytes) {
    crc ^= byte
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0)
    }
  }
  return (crc ^ 0xffffffff) >>> 0
}

function u16(value: number): Uint8Array {
  return new Uint8Array([value & 0xff, (value >>> 8) & 0xff])
}

function u32(value: number): Uint8Array {
  return new Uint8Array([
    value & 0xff,
    (value >>> 8) & 0xff,
    (value >>> 16) & 0xff,
    (value >>> 24) & 0xff,
  ])
}

function concatBytes(parts: Uint8Array[]): Uint8Array {
  const size = parts.reduce((total, part) => total + part.length, 0)
  const out = new Uint8Array(size)
  let offset = 0
  for (const part of parts) {
    out.set(part, offset)
    offset += part.length
  }
  return out
}

function zipStore(files: Array<{ name: string; data: Uint8Array }>): Uint8Array {
  const locals: Uint8Array[] = []
  const centrals: Uint8Array[] = []
  let offset = 0
  for (const file of files) {
    const nameBytes = encodeUtf8(file.name)
    const crc = crc32(file.data)
    const local = concatBytes([
      u32(0x04034b50),
      u16(20),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(crc),
      u32(file.data.length),
      u32(file.data.length),
      u16(nameBytes.length),
      u16(0),
      nameBytes,
      file.data,
    ])
    locals.push(local)
    centrals.push(concatBytes([
      u32(0x02014b50),
      u16(20),
      u16(20),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(crc),
      u32(file.data.length),
      u32(file.data.length),
      u16(nameBytes.length),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(0),
      u32(offset),
      nameBytes,
    ]))
    offset += local.length
  }
  const central = concatBytes(centrals)
  return concatBytes([
    ...locals,
    central,
    concatBytes([
      u32(0x06054b50),
      u16(0),
      u16(0),
      u16(files.length),
      u16(files.length),
      u32(central.length),
      u32(offset),
      u16(0),
    ]),
  ])
}

function xmlEscape(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export interface OcrExportRow {
  label: string
  value: string
}

export function ocrExportRows(
  fields: Array<{ label?: string; value?: unknown }>,
): OcrExportRow[] {
  return fields
    .map((field) => ({
      label: String(field.label || '').trim(),
      value: fieldPlain(field.value).trim(),
    }))
    .filter((row) => row.label && row.value)
}

/** Minimal DOCX: Russian «ключ: значение» like the review panel. */
export function downloadOcrFieldsDocx(
  rows: OcrExportRow[],
  fileStem = 'ocr-export',
) {
  const lines = ocrExportRows(rows).map((row) => `${row.label}: ${row.value}`)
  const paragraphs = (lines.length ? lines : ['']).map(
    (line) => `<w:p><w:r><w:t xml:space="preserve">${xmlEscape(line)}</w:t></w:r></w:p>`,
  )
  const documentXml = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    + '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    + `<w:body>${paragraphs.join('')}<w:sectPr/></w:body></w:document>`
  )
  const types = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    + '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    + '<Default Extension="xml" ContentType="application/xml"/>'
    + '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    + '</Types>'
  )
  const rels = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    + '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
    + '</Relationships>'
  )
  const bytes = zipStore([
    { name: '[Content_Types].xml', data: encodeUtf8(types) },
    { name: '_rels/.rels', data: encodeUtf8(rels) },
    { name: 'word/document.xml', data: encodeUtf8(documentXml) },
  ])
  triggerDownload(
    new Blob([bytes.slice()], {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    }),
    `${fileStem}.docx`,
  )
}

/** GET/POST /api/v1/ocr/jobs/<id>/export/ — DOCX (default) / JSON / CSV after HITL. */
export async function exportOcrJob(
  jobId: string,
  format: 'json' | 'csv' | 'pdf' | 'docx' = 'docx',
  extras?: { documentType?: string; fields?: Record<string, unknown> },
): Promise<void> {
  const query = `?format=${encodeURIComponent(format)}`
  const hasBody = Boolean(extras?.fields)
  const response = await fetch(
    `/api/v1/ocr/jobs/${encodeURIComponent(jobId)}/export/${query}`,
    {
      method: hasBody ? 'POST' : 'GET',
      credentials: 'include',
      headers: hasBody
        ? {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken(),
          }
        : undefined,
      body: hasBody
        ? JSON.stringify({
            document_type: extras?.documentType,
            fields: extras?.fields,
            format,
            require_valid: false,
          })
        : undefined,
    },
  )
  if (!response.ok) throw new Error(await parseError(response))
  const blob = await response.blob()
  triggerDownload(
    blob,
    filenameFromDisposition(
      response.headers.get('content-disposition'),
      `ocr-export.${format}`,
    ),
  )
}
