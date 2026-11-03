import { ensureCsrfToken, ensureDevSession } from '../../../auth/ensureDevSession'

export interface ContentFilterItem {
  id?: number
  code: string
  name: string
  enabled: boolean
  keywords: string[]
  exceptions: string[]
  refusal_text: string
  sort_order: number
  updated_at?: string
  updated_by?: string
}

export interface ContentFilterCatalog {
  items: ContentFilterItem[]
}

export type ContentFilterPayload = {
  items: Array<Pick<
    ContentFilterItem,
    'code' | 'name' | 'enabled' | 'keywords' | 'exceptions' | 'refusal_text' | 'sort_order'
  >>
}

interface ApiErrorPayload {
  error?: string
  details?: Record<string, string[]>
}

export class ContentFiltersApiError extends Error {
  readonly details: Record<string, string[]>

  constructor(
    message: string,
    details: Record<string, string[]> = {},
  ) {
    super(message)
    this.details = details
  }
}

async function parseResponse(response: Response): Promise<ContentFilterCatalog> {
  const text = await response.text()
  let body: ContentFilterCatalog | ApiErrorPayload | null = null
  try {
    body = text ? (JSON.parse(text) as ContentFilterCatalog | ApiErrorPayload) : null
  } catch {
    if (
      response.status === 403
      && /csrf|CSRF verification failed/i.test(text)
    ) {
      throw new ContentFiltersApiError('csrf_failed')
    }
    throw new ContentFiltersApiError(
      response.status === 401
        ? 'authentication_required'
        : `Request failed with status ${response.status}`,
    )
  }
  if (!response.ok) {
    const error = (body ?? {}) as ApiErrorPayload
    throw new ContentFiltersApiError(
      error.error
      ?? (response.status === 401
        ? 'authentication_required'
        : response.status === 403
          ? 'permission_denied'
          : `Request failed with status ${response.status}`),
      error.details ?? {},
    )
  }
  if (body == null || !('items' in body)) {
    throw new ContentFiltersApiError('empty_response')
  }
  return body
}

async function authedFetch(
  input: string,
  init: RequestInit & { csrf?: boolean } = {},
): Promise<Response> {
  const { csrf = false, headers: initHeaders, ...rest } = init
  await ensureDevSession()
  const headers = new Headers(initHeaders)
  if (csrf) {
    const token = await ensureCsrfToken()
    if (!token) {
      throw new ContentFiltersApiError('csrf_failed')
    }
    headers.set('X-CSRFToken', token)
  }
  return fetch(input, {
    ...rest,
    credentials: 'include',
    headers,
  })
}

export async function loadContentFilters(): Promise<ContentFilterCatalog> {
  const response = await authedFetch('/api/admin/assistant/content-filters/', {
    method: 'GET',
  })
  return parseResponse(response)
}

export async function saveContentFilters(
  payload: ContentFilterPayload,
): Promise<ContentFilterCatalog> {
  const response = await authedFetch('/api/admin/assistant/content-filters/', {
    method: 'PUT',
    csrf: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseResponse(response)
}
