import { ensureCsrfToken, ensureDevSession } from '../../../auth/ensureDevSession'

export type LlmConfigProfile = 'assistant_bank' | 'sufler_cc'
export type LlmConfigLayerStatus = 'ok' | 'attention' | 'not_configured' | 'not_run'

export interface LlmConfigLayer {
  id: string
  index: number
  title: string
  status: LlmConfigLayerStatus
  summary: string
  href: string
}

export interface LlmConfigDashboard {
  profile: LlmConfigProfile
  layers: LlmConfigLayer[]
}

export interface LlmConfigCheckResult extends LlmConfigDashboard {
  passed: boolean
  answer: string | null
  model: string | null
}

export class LlmConfigApiError extends Error {
  readonly code: string
  readonly requestId: string

  constructor(message: string, code = '', requestId = '') {
    super(message)
    this.code = code
    this.requestId = requestId
  }
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
      throw new LlmConfigApiError('Не удалось подтвердить сессию.', 'csrf_failed')
    }
    headers.set('X-CSRFToken', token)
  }
  return fetch(input, {
    ...rest,
    credentials: 'include',
    headers,
  })
}

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text) as unknown
  } catch {
    return null
  }
}

function errorFrom(response: Response, body: unknown): LlmConfigApiError {
  const payload = body && typeof body === 'object' ? body as {
    error?: string
    message?: string
    request_id?: string
  } : {}
  const message = typeof payload.message === 'string' && payload.message.trim()
    ? payload.message
    : 'Не удалось выполнить запрос. Попробуйте ещё раз.'
  return new LlmConfigApiError(
    message,
    typeof payload.error === 'string' ? payload.error : `http_${response.status}`,
    typeof payload.request_id === 'string' ? payload.request_id : '',
  )
}

export async function loadLlmConfig(profile: LlmConfigProfile): Promise<LlmConfigDashboard> {
  const response = await authedFetch(`/api/admin/llm-config/?profile=${profile}`)
  const body = await readJson(response)
  if (!response.ok) throw errorFrom(response, body)
  return body as LlmConfigDashboard
}

export async function checkLlmConfig(profile: LlmConfigProfile): Promise<LlmConfigCheckResult> {
  const response = await authedFetch(`/api/admin/llm-config/check/?profile=${profile}`, {
    method: 'POST',
    csrf: true,
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  })
  const body = await readJson(response)
  if (!response.ok) throw errorFrom(response, body)
  return body as LlmConfigCheckResult
}
