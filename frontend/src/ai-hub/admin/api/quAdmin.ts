export interface QuExample {
  id: number
  question: string
  article_id: number | null
  article_title: string
  intent_id: string
  synonyms: string
  locale: string
  status: 'active' | 'pending_review' | 'rejected'
  is_active: boolean
  source: 'manual' | 'dialog' | 'asr_qa' | string
  source_feedback_id: string
  original_hint: string
  relevance_percent: number | null
  operator_name: string
  channel: string
  admin_comment: string
  created_by: string
  reviewed_by: string
  reviewed_at: string
  created_at: string
  updated_at: string
}

export interface QuExampleList {
  items: QuExample[]
  counts: {
    active: number
    pending_review: number
    rejected: number
  }
}

export interface QuDocumentOption {
  article_id: number
  title: string
  kb_name: string
}

export interface QuPolicy {
  mode: 'suggest' | 'auto_with_confirmation' | 'auto'
  updated_at: string
  updated_by: string
}

interface ApiErrorPayload {
  error?: string
  details?: Record<string, string[]>
}

export class QuAdminApiError extends Error {
  readonly details: Record<string, string[]>

  constructor(message: string, details: Record<string, string[]> = {}) {
    super(message)
    this.details = details
  }
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

async function parseJson<T>(response: Response): Promise<T> {
  const body = await response.json() as T | ApiErrorPayload
  if (!response.ok) {
    const error = body as ApiErrorPayload
    const detail = error.details?.request?.[0]
    throw new QuAdminApiError(
      detail || error.error || `HTTP ${response.status}`,
      error.details || {},
    )
  }
  return body as T
}

async function authedFetch(input: string, init?: RequestInit): Promise<Response> {
  const { ensureDevSession } = await import('../../../auth/ensureDevSession')
  await ensureDevSession()
  return fetch(input, { credentials: 'include', ...init })
}

function jsonHeaders(): HeadersInit {
  return {
    'Content-Type': 'application/json',
    'X-CSRFToken': csrfToken(),
  }
}

export async function listQuExamples(status = ''): Promise<QuExampleList> {
  const query = status ? `?status=${encodeURIComponent(status)}` : ''
  const response = await authedFetch(`/api/admin/qu/examples/${query}`)
  return parseJson(response)
}

export async function createQuExample(payload: Record<string, unknown>): Promise<QuExample> {
  const response = await authedFetch('/api/admin/qu/examples/', {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(payload),
  })
  return parseJson(response)
}

export async function updateQuExample(
  exampleId: number,
  payload: Record<string, unknown>,
): Promise<QuExample> {
  const response = await authedFetch(`/api/admin/qu/examples/${exampleId}/`, {
    method: 'PATCH',
    headers: jsonHeaders(),
    body: JSON.stringify(payload),
  })
  return parseJson(response)
}

export async function deleteQuExample(exampleId: number): Promise<void> {
  const response = await authedFetch(`/api/admin/qu/examples/${exampleId}/`, {
    method: 'DELETE',
    headers: jsonHeaders(),
  })
  await parseJson(response)
}

export async function reviewQuExample(
  exampleId: number,
  payload: Record<string, unknown>,
): Promise<QuExample> {
  const response = await authedFetch(`/api/admin/qu/examples/${exampleId}/review/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(payload),
  })
  return parseJson(response)
}

export async function listQuDocuments(): Promise<QuDocumentOption[]> {
  const response = await authedFetch('/api/admin/qu/documents/')
  const body = await parseJson<{ items: QuDocumentOption[] }>(response)
  return body.items
}

export async function fetchQuPolicy(): Promise<QuPolicy> {
  const response = await authedFetch('/api/admin/qu/policy/')
  return parseJson(response)
}

export async function updateQuPolicy(mode: QuPolicy['mode']): Promise<QuPolicy> {
  const response = await authedFetch('/api/admin/qu/policy/', {
    method: 'PUT',
    headers: jsonHeaders(),
    body: JSON.stringify({ mode }),
  })
  return parseJson(response)
}
