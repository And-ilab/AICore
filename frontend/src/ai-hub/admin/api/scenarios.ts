import { ensureCsrfToken, ensureDevSession } from '../../../auth/ensureDevSession'

export type ScenarioStatus = 'draft' | 'production'
export type ScenarioChannel = 'both' | 'telephony' | 'online_chat'
export type ScenarioNodeType = 'start' | 'clarify' | 'answer' | 'branch' | 'escalate' | 'end'

export interface ScenarioEdge {
  to: string
  label: string
  reply?: string
  keywords: string[]
  is_fallback?: boolean
}

export interface ScenarioNode {
  id: string
  type: ScenarioNodeType | string
  label: string
  hint_text: string
  clarify_text: string
  examples: string[]
  intent_id: string
  edges: ScenarioEdge[]
  position?: { x: number; y: number }
}

export interface ScenarioGraph {
  nodes: ScenarioNode[]
}

export interface ScenarioListItem {
  code: string
  title: string
  root_question: string
  status: ScenarioStatus
  channels: ScenarioChannel | string
  version_number: number
  is_published: boolean
  updated_at: string
  updated_by: string
}

export interface ScenarioDetail extends ScenarioListItem {
  graph: ScenarioGraph
  system_prompt: string
}

export interface ScenarioListResponse {
  items: ScenarioListItem[]
  counts: { total: number; production: number; draft: number }
}

export interface ScenarioTestRun {
  code: string
  title: string
  steps: Array<{
    index: number
    input: string
    node_id: string
    label: string
    hint_text: string
    clarify_text: string
    selected_edge: string
    available_choices: Array<{
      label: string
      reply: string
    }>
    terminal: boolean
    ok: boolean
  }>
  errors: string[]
  path: string[]
  ok: boolean
  version_number: number
  is_published: boolean
}

export interface SuflerScenarioProgress {
  code: string
  title: string
  path: string[]
  node_id: string
  next_clarify: string
}

class ScenariosApiError extends Error {
  readonly details: Record<string, string[]>

  constructor(message: string, details: Record<string, string[]> = {}) {
    super(message)
    this.details = details
  }
}

interface ApiErrorPayload {
  error?: string
  details?: Record<string, string[]>
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
      throw new ScenariosApiError('csrf_failed')
    }
    headers.set('X-CSRFToken', token)
  }
  return fetch(input, {
    ...rest,
    credentials: 'include',
    headers,
  })
}

async function parseJson<T>(response: Response): Promise<T> {
  const text = await response.text()
  let body: T | ApiErrorPayload | null = null
  try {
    body = text ? (JSON.parse(text) as T | ApiErrorPayload) : null
  } catch {
    throw new ScenariosApiError(
      response.status === 401 ? 'authentication_required' : `Request failed with status ${response.status}`,
    )
  }
  if (!response.ok) {
    const error = (body ?? {}) as ApiErrorPayload
    throw new ScenariosApiError(
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
    throw new ScenariosApiError('empty_response')
  }
  return body as T
}

export async function listDialogScenarios(): Promise<ScenarioListResponse> {
  const response = await authedFetch('/api/admin/scenarios/', { method: 'GET' })
  return parseJson<ScenarioListResponse>(response)
}

export async function getDialogScenario(code: string): Promise<ScenarioDetail> {
  const response = await authedFetch(`/api/admin/scenarios/${encodeURIComponent(code)}/`, {
    method: 'GET',
  })
  return parseJson<ScenarioDetail>(response)
}

export async function saveDialogScenario(
  code: string,
  payload: Partial<ScenarioDetail> & { publish?: boolean },
): Promise<ScenarioDetail> {
  const response = await authedFetch(`/api/admin/scenarios/${encodeURIComponent(code)}/`, {
    method: 'PUT',
    csrf: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseJson<ScenarioDetail>(response)
}

export async function createDialogScenario(payload: {
  code: string
  title: string
  root_question?: string
  channels?: string
  graph?: ScenarioGraph
}): Promise<ScenarioDetail> {
  const response = await authedFetch('/api/admin/scenarios/', {
    method: 'POST',
    csrf: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseJson<ScenarioDetail>(response)
}

export async function testDialogScenario(code: string, lines: string[]): Promise<ScenarioTestRun> {
  const response = await authedFetch(
    `/api/admin/scenarios/${encodeURIComponent(code)}/test-run/`,
    {
      method: 'POST',
      csrf: true,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lines }),
    },
  )
  return parseJson<ScenarioTestRun>(response)
}

export { ScenariosApiError }
