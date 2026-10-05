import { ensureCsrfToken, ensureDevSession } from '../../../auth/ensureDevSession'

export type KnowledgeBaseStatus = 'idle' | 'indexing' | 'ready' | 'error'
export type DocumentStatus = 'uploaded' | 'indexed' | 'error'
export type KnowledgeBaseSource = 'manual' | 'suz_bitrix'
export type WebhookStatus = 'OK' | 'ERROR' | 'IDLE'

export interface KnowledgeBaseDocument {
  id: number
  filename: string
  content_type: string
  size_bytes: number
  status: DocumentStatus
  status_message: string
  chunk_count: number
  index_percent: number
  source: KnowledgeBaseSource
  source_label: string
  readonly?: boolean
  uploaded_at: string
  indexed_at: string | null
  uploaded_by: string
  permalink?: string
}

export interface KnowledgeBase {
  id: number
  name: string
  slug: string
  scope: string
  description: string
  source: KnowledgeBaseSource
  source_label: string
  status: KnowledgeBaseStatus
  status_message: string
  document_count: number
  chunk_count: number
  index_percent: number
  webhook_status: WebhookStatus
  webhook_label: string
  readonly?: boolean
  last_reindexed_at: string | null
  created_at: string
  updated_at: string
  created_by: string
  documents?: KnowledgeBaseDocument[]
}

interface ApiErrorPayload {
  error?: string
  details?: Record<string, string[]>
}

export class KnowledgeBaseApiError extends Error {
  readonly details: Record<string, string[]>

  constructor(
    message: string,
    details: Record<string, string[]> = {},
  ) {
    super(message)
    this.details = details
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  let body: T | ApiErrorPayload | null = null
  const text = await response.text()
  try {
    body = text ? (JSON.parse(text) as T | ApiErrorPayload) : null
  } catch {
    body = null
  }
  if (!response.ok) {
    const error = (body ?? {}) as ApiErrorPayload
    if (error.error) {
      throw new KnowledgeBaseApiError(error.error, error.details ?? {})
    }
    // Django CSRF failure is HTML 403 — not the same as missing session.
    if (
      response.status === 403
      && /csrf|CSRF verification failed/i.test(text)
    ) {
      throw new KnowledgeBaseApiError('csrf_failed')
    }
    if (response.status === 401) {
      throw new KnowledgeBaseApiError('authentication_required')
    }
    if (response.status === 403) {
      throw new KnowledgeBaseApiError('permission_denied')
    }
    throw new KnowledgeBaseApiError(`http_${response.status}`)
  }
  if (body == null) {
    throw new KnowledgeBaseApiError('empty_response')
  }
  return body as T
}

async function authedFetch(
  input: string,
  init: RequestInit & { csrf?: boolean } = {},
): Promise<Response> {
  const { csrf = false, headers: initHeaders, ...rest } = init
  const send = async () => {
    await ensureDevSession()
    const headers = new Headers(initHeaders)
    if (csrf) {
      const token = await ensureCsrfToken()
      if (!token) {
        throw new KnowledgeBaseApiError('csrf_failed')
      }
      headers.set('X-CSRFToken', token)
    }
    return fetch(input, {
      ...rest,
      credentials: 'include',
      headers,
    })
  }
  let response = await send()
  if (response.status === 401 || response.status === 403) {
    const { resetDevSessionCache } = await import('../../../auth/ensureDevSession')
    resetDevSessionCache()
    await ensureDevSession(true)
    response = await send()
  }
  return response
}

export async function listKnowledgeBases(): Promise<KnowledgeBase[]> {
  const response = await authedFetch('/api/admin/kb/', { method: 'GET' })
  const body = await parseResponse<{ items: KnowledgeBase[] }>(response)
  return body.items
}

export async function getKnowledgeBase(id: number): Promise<KnowledgeBase> {
  const response = await authedFetch(`/api/admin/kb/${id}/`, { method: 'GET' })
  return parseResponse<KnowledgeBase>(response)
}

export async function createKnowledgeBase(payload: {
  name: string
  scope?: string
  description?: string
}): Promise<KnowledgeBase> {
  const response = await authedFetch('/api/admin/kb/', {
    method: 'POST',
    csrf: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseResponse<KnowledgeBase>(response)
}

export async function deleteKnowledgeBase(id: number): Promise<void> {
  const response = await authedFetch(`/api/admin/kb/${id}/`, {
    method: 'DELETE',
    csrf: true,
  })
  await parseResponse<{ ok: boolean }>(response)
}

export async function uploadKnowledgeDocument(
  kbId: number,
  file: File,
): Promise<{ knowledge_base: KnowledgeBase; document: KnowledgeBaseDocument }> {
  const form = new FormData()
  form.append('file', file)
  const response = await authedFetch(`/api/admin/kb/${kbId}/upload/`, {
    method: 'POST',
    csrf: true,
    body: form,
  })
  return parseResponse(response)
}

export async function deleteKnowledgeDocument(
  kbId: number,
  documentId: number,
): Promise<KnowledgeBase> {
  const response = await authedFetch(
    `/api/admin/kb/${kbId}/documents/${documentId}/`,
    {
      method: 'DELETE',
      csrf: true,
    },
  )
  return parseResponse<KnowledgeBase>(response)
}

export async function reindexKnowledgeBase(
  kbId: number,
): Promise<KnowledgeBase> {
  const response = await authedFetch(`/api/admin/kb/${kbId}/reindex/`, {
    method: 'POST',
    csrf: true,
  })
  return parseResponse<KnowledgeBase>(response)
}
