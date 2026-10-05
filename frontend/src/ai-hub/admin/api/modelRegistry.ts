import { ensureCsrfToken, ensureDevSession } from '../../../auth/ensureDevSession'

export type ModelParamsProfile = 'assistant_bank' | 'sufler_cc'
export type ModelParamsPreset = 'short' | 'standard' | 'long'

export interface ModelParamsData {
  profile: ModelParamsProfile
  slot: string
  generation: {
    temperature: number
    top_p: number
    max_tokens: number
    response_chars_max: number
    preset: ModelParamsPreset
  }
  rag: {
    chunk_size_tokens: number
    chunk_overlap_tokens: number
    context_inclusion: number
    deterministic_answer: number
  }
  read_only: {
    dev_model: string | null
    prod_candidate: string | null
    status: string
    context_window?: string
    llm_model_label?: string
  }
  presets?: Record<
    ModelParamsPreset,
    { label: string; values: Partial<ModelParamsData['generation']> }
  >
  platform_defaults?: {
    temperature: number
    top_p: number
    max_tokens: number
    response_chars_max: number
    preset: ModelParamsPreset
    chunk_size_tokens: number
    chunk_overlap_tokens: number
    context_inclusion_threshold: number
    deterministic_answer_threshold: number
  }
  constraints: {
    temperature: { min: number; max: number; step: number }
    top_p: { min: number; max: number; step: number }
    max_tokens: { min: number; max: number }
    response_chars_max: { min: number; max: number }
  }
  revision: number
  updated_at: string
  updated_by: string
}

export interface ModelParamsPayload {
  generation: ModelParamsData['generation']
  rag: ModelParamsData['rag']
}

interface ApiErrorPayload {
  error?: string
  details?: Record<string, string[]>
}

export class ModelParamsApiError extends Error {
  readonly details: Record<string, string[]>

  constructor(
    message: string,
    details: Record<string, string[]> = {},
  ) {
    super(message)
    this.details = details
  }
}

async function parseResponse(response: Response): Promise<ModelParamsData> {
  const text = await response.text()
  let body: ModelParamsData | ApiErrorPayload | null = null
  try {
    body = text ? (JSON.parse(text) as ModelParamsData | ApiErrorPayload) : null
  } catch {
    if (
      response.status === 403
      && /csrf|CSRF verification failed/i.test(text)
    ) {
      throw new ModelParamsApiError('csrf_failed')
    }
    throw new ModelParamsApiError(
      response.status === 401
        ? 'authentication_required'
        : `Request failed with status ${response.status}`,
    )
  }
  if (!response.ok) {
    const error = (body ?? {}) as ApiErrorPayload
    throw new ModelParamsApiError(
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
    throw new ModelParamsApiError('empty_response')
  }
  const data = body as ModelParamsData
  if (!data.generation.preset) {
    data.generation.preset = 'standard'
  }
  return data
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
      throw new ModelParamsApiError('csrf_failed')
    }
    headers.set('X-CSRFToken', token)
  }
  return fetch(input, {
    ...rest,
    credentials: 'include',
    headers,
  })
}

export async function loadModelParams(
  profile: ModelParamsProfile,
): Promise<ModelParamsData> {
  const response = await authedFetch(
    `/api/admin/model-registry/model-params/?profile=${profile}`,
    { method: 'GET' },
  )
  return parseResponse(response)
}

export async function saveModelParams(
  profile: ModelParamsProfile,
  payload: ModelParamsPayload,
): Promise<ModelParamsData> {
  const response = await authedFetch(
    `/api/admin/model-registry/model-params/?profile=${profile}`,
    {
      method: 'PUT',
      csrf: true,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  )
  return parseResponse(response)
}
