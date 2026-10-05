import { ensureCsrfToken, ensureDevSession } from '../../../auth/ensureDevSession'

export type SuflerPolicyMode = 'consultation' | 'service'

export interface SuflerPolicyData {
  telephony_min_relevance_percent: number
  clarify_min_relevance_percent: number
  max_hints: number
  default_mode: SuflerPolicyMode
  updated_at: string
  updated_by: string
  model_params_path: string
  chat_templates_path: string
}

export type SuflerPolicyPayload = Pick<
  SuflerPolicyData,
  | 'telephony_min_relevance_percent'
  | 'clarify_min_relevance_percent'
  | 'max_hints'
  | 'default_mode'
>

interface ApiErrorPayload {
  error?: string
  details?: Record<string, string[]>
}

export class SuflerPoliciesApiError extends Error {
  readonly details: Record<string, string[]>

  constructor(
    message: string,
    details: Record<string, string[]> = {},
  ) {
    super(message)
    this.details = details
  }
}

async function parseResponse(response: Response): Promise<SuflerPolicyData> {
  const text = await response.text()
  let body: SuflerPolicyData | ApiErrorPayload | null = null
  try {
    body = text ? (JSON.parse(text) as SuflerPolicyData | ApiErrorPayload) : null
  } catch {
    if (
      response.status === 403
      && /csrf|CSRF verification failed/i.test(text)
    ) {
      throw new SuflerPoliciesApiError('csrf_failed')
    }
    throw new SuflerPoliciesApiError(
      response.status === 401
        ? 'authentication_required'
        : `Request failed with status ${response.status}`,
    )
  }
  if (!response.ok) {
    const error = (body ?? {}) as ApiErrorPayload
    throw new SuflerPoliciesApiError(
      error.error
      ?? (response.status === 401
        ? 'authentication_required'
        : response.status === 403
          ? 'permission_denied'
          : `Request failed with status ${response.status}`),
      error.details ?? {},
    )
  }
  if (body == null) {
    throw new SuflerPoliciesApiError('empty_response')
  }
  return body as SuflerPolicyData
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
      throw new SuflerPoliciesApiError('csrf_failed')
    }
    headers.set('X-CSRFToken', token)
  }
  return fetch(input, {
    ...rest,
    credentials: 'include',
    headers,
  })
}

export async function loadSuflerPolicies(): Promise<SuflerPolicyData> {
  const response = await authedFetch('/api/admin/sufler/policies/', { method: 'GET' })
  return parseResponse(response)
}

export async function saveSuflerPolicies(
  payload: SuflerPolicyPayload,
): Promise<SuflerPolicyData> {
  const response = await authedFetch('/api/admin/sufler/policies/', {
    method: 'PUT',
    csrf: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseResponse(response)
}
