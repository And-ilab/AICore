export type RecognitionStatus = 'recognized' | 'unrecognized' | 'partial'
export type AsrChannel = 'telephony' | 'online_chat'

export interface AsrUtterance {
  id: number
  turn_index: number
  speaker: 'operator' | 'client'
  text: string
  confidence: number
  start_ms: number
  end_ms: number
  is_unrecognized: boolean
  low_confidence: boolean
  training_candidate: boolean
  exemplar_candidate: boolean
  annotated_by: string
  annotated_at: string | null
}

export interface AsrSessionSummary {
  id: number
  session_id: string
  channel: AsrChannel
  operator_id: string
  operator_name: string
  started_at: string
  ended_at: string
  duration_sec: number
  avg_confidence: number
  min_confidence: number
  recognition_status: RecognitionStatus
  audio_url: string
  has_training_candidate: boolean
  expires_at: string
  low_confidence_threshold: number
}

export interface AsrSessionDetail extends AsrSessionSummary {
  utterances: AsrUtterance[]
}

export interface AsrCatalogueStats {
  total: number
  recognized: number
  unrecognized: number
  partial: number
  training_candidates: number
  low_confidence: number
}

export interface AsrSessionFilters {
  channel?: AsrChannel | ''
  operator?: string
  recognition_status?: RecognitionStatus | ''
  low_confidence_only?: boolean
  date_from?: string
  date_to?: string
}

interface ApiErrorPayload {
  error?: string
  details?: Record<string, string[]>
}

export class AsrQaApiError extends Error {
  readonly details: Record<string, string[]>

  constructor(
    message: string,
    details: Record<string, string[]> = {},
  ) {
    super(message)
    this.details = details
  }
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

async function parseResponse<T>(response: Response): Promise<T> {
  const body = await response.json() as T | ApiErrorPayload
  if (!response.ok) {
    const error = body as ApiErrorPayload
    throw new AsrQaApiError(
      error.error || `HTTP ${response.status}`,
      error.details || {},
    )
  }
  return body as T
}

function toQuery(filters: AsrSessionFilters): string {
  const params = new URLSearchParams()
  if (filters.channel) params.set('channel', filters.channel)
  if (filters.operator) params.set('operator', filters.operator)
  if (filters.recognition_status) {
    params.set('recognition_status', filters.recognition_status)
  }
  if (filters.low_confidence_only) params.set('low_confidence_only', 'true')
  if (filters.date_from) params.set('date_from', filters.date_from)
  if (filters.date_to) params.set('date_to', filters.date_to)
  const query = params.toString()
  return query ? `?${query}` : ''
}

async function authedFetch(input: string, init?: RequestInit): Promise<Response> {
  const { ensureDevSession } = await import('../../../auth/ensureDevSession')
  await ensureDevSession()
  return fetch(input, { credentials: 'include', ...init })
}

export async function listAsrSessions(filters: AsrSessionFilters = {}): Promise<{
  items: AsrSessionSummary[]
  stats: AsrCatalogueStats
}> {
  const response = await authedFetch(`/api/reports/asr/sessions/${toQuery(filters)}`)
  return parseResponse(response)
}

export async function getAsrSession(sessionId: number): Promise<AsrSessionDetail> {
  const response = await authedFetch(`/api/reports/asr/sessions/${sessionId}/`)
  return parseResponse(response)
}

export async function setTrainingCandidate(
  sessionId: number,
  utteranceId: number,
  trainingCandidate: boolean,
): Promise<{ utterance: AsrUtterance; session: AsrSessionSummary }> {
  const response = await authedFetch(
    `/api/reports/asr/sessions/${sessionId}/utterances/${utteranceId}/`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
      },
      body: JSON.stringify({ training_candidate: trainingCandidate }),
    },
  )
  return parseResponse(response)
}

export async function seedAsrDemo(force = true): Promise<{
  items: AsrSessionSummary[]
  stats: AsrCatalogueStats
}> {
  const response = await authedFetch('/api/reports/asr/seed-demo/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
    },
    body: JSON.stringify({ force }),
  })
  return parseResponse(response)
}
