import { ensureCsrfToken, ensureDevSession, readCsrfToken } from '../../../auth/ensureDevSession'

export type CcChannel = 'telephony' | 'online_chat'

export interface CcAnalyticsFilters {
  date_from?: string
  date_to?: string
  channel?: CcChannel | '' | string
  report?: string
  messenger?: string
  topic?: string
  status?: string
  department?: string
  group_by?: string
  scope?: 'chat' | 'sufler' | string
}

export interface CcAnalyticsSummary {
  sessions: number
  recognized_pct: number
  avg_confidence: number
  useful_pct: number
  incorrect_llm: number
  hint_latency_p95_ms: number
}

export interface CcAnalyticsRow {
  date: string
  channel: CcChannel
  operator: string
  sessions: number
  recognized_pct: number
  avg_confidence: number
  useful_pct: number
  incomplete_pct: number
  unused_pct: number
  incorrect_llm: number
  hint_latency_p95_ms: number
  aht_sec: number
}

export interface CcUsefulnessRow {
  channel: CcChannel
  label: string
  useful_pct: number
  incomplete_pct: number
  unused_pct: number
  sessions: number
}

export interface AsrQualityPoint {
  date: string
  recognized_pct: number
  avg_confidence: number
  sessions: number
}

export interface CcAnalyticsPayload {
  filters: {
    date_from: string
    date_to: string
    channel: string
  }
  summary: CcAnalyticsSummary
  rows: CcAnalyticsRow[]
  usefulness: CcUsefulnessRow[]
  asr_quality: AsrQualityPoint[]
  stub: boolean
  source: string
}

export interface LiveKpis {
  in_progress: number
  in_queue: number
  avg_wait_sec: number
  operators_online: number
  sla_ok_pct: number
  hint_p95_ms: number
  closed_today?: number
}

export interface LiveDashboard {
  generated_at: string
  stub: boolean
  source: string
  kpis: LiveKpis
  departments: { name: string; active: number; queue: number }[]
  operators: {
    name: string
    status: string
    active_dialogs: number
    channel: string
  }[]
  alerts: { id: string; tone: string; title: string; detail: string; at: string }[]
  llm_feed: {
    id: string
    channel: string
    operator: string
    topic: string
    relevance_pct: number
    feedback: string
    latency_ms: number
    at: string
    query?: string
  }[]
  dialog_feed?: {
    id: string
    ref: string
    channel: string
    messenger: string
    operator: string
    client: string
    topic: string
    status: string
    wait_sec: number | null
    relevance_pct: number | null
    feedback: string
    preview: string
    at: string
  }[]
  chat: {
    waiting: number
    active: number
    closed_today: number
    operators_from_chat: { name: string; active_dialogs: number }[]
  }
}

export interface CatalogReportMeta {
  id: string
  fr: string
  label: string
  default_view: string
  group?: string
  description?: string
}

export interface CatalogPayload {
  filters: Record<string, string>
  catalog: CatalogReportMeta[]
  report: CatalogReportMeta
  rows: Record<string, unknown>[]
  columns?: { key: string; label: string }[]
  title?: string
  chart: { label: string; value: number }[]
  summary: Record<string, unknown>
  stub: boolean
  source: string
  alerts: { id: string; title: string; detail: string; enabled: boolean }[]
}

export interface BuilderTemplatesPayload {
  templates: {
    id: string
    name: string
    metrics: string[]
    filters: Record<string, string>
    view_mode: string
  }[]
  saved?: SavedReportTemplate[]
  metric_catalog: { id: string; label: string }[]
  stub: boolean
}

export interface SavedReportTemplate {
  id: string
  name: string
  metrics: string[]
  view_mode: string
  date_from: string | null
  date_to: string | null
  filters: Record<string, unknown>
  owner_username: string
  created_at: string
  updated_at: string
}

interface ApiErrorPayload {
  error?: string
  details?: Record<string, string[]>
}

export class CcReportsApiError extends Error {
  readonly details: Record<string, string[]>

  constructor(message: string, details: Record<string, string[]> = {}) {
    super(message)
    this.details = details
  }
}

function toQuery(
  filters: CcAnalyticsFilters,
  extra: Record<string, string> = {},
): string {
  const params = new URLSearchParams()
  if (filters.date_from) params.set('date_from', filters.date_from)
  if (filters.date_to) params.set('date_to', filters.date_to)
  if (filters.channel) params.set('channel', filters.channel)
  if (filters.report) params.set('report', filters.report)
  if (filters.messenger) params.set('messenger', filters.messenger)
  if (filters.topic) params.set('topic', filters.topic)
  if (filters.status) params.set('status', filters.status)
  if (filters.department) params.set('department', filters.department)
  if (filters.group_by) params.set('group_by', filters.group_by)
  if (filters.scope) params.set('scope', filters.scope)
  for (const [key, value] of Object.entries(extra)) {
    if (value) params.set(key, value)
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

async function parseJson<T>(response: Response): Promise<T> {
  const text = await response.text()
  const trimmed = text.trim()
  if (!trimmed || trimmed.startsWith('<')) {
    throw new CcReportsApiError(
      response.ok
        ? 'Сервер вернул не JSON-ответ'
        : `Ошибка сервера (HTTP ${response.status})`,
    )
  }
  let body: T | ApiErrorPayload
  try {
    body = JSON.parse(trimmed) as T | ApiErrorPayload
  } catch {
    throw new CcReportsApiError(`Не удалось разобрать ответ (HTTP ${response.status})`)
  }
  if (!response.ok) {
    const error = body as ApiErrorPayload
    const raw = error.error || `Ошибка сервера (HTTP ${response.status})`
    const localized = raw
      .replace(/\bchat-period\b/gi, 'Обращения за период')
      .replace(/\bchat-sla\b/gi, 'SLA и время ожидания')
      .replace(/\bchat-operators\b/gi, 'Нагрузка операторов')
      .replace(/\bchat-ratings\b/gi, 'Оценки клиентов')
      .replace(/\bchat-topics\b/gi, 'Тематики закрытия')
      .replace(/\bchat-offline\b/gi, 'Необработанные и отказные обращения')
      .replace(/\bchat_history\b/gi, 'Реестр диалогов')
      .replace(/\busefulness\b/gi, 'Полезность подсказок суфлёра')
      .replace(/\brelevance\b/gi, 'Релевантность ответов')
      .replace(/\bperformance\b/gi, 'Производительность')
      .replace(/\brepeats\b/gi, 'Повторные обращения')
      .replace(/\bexecutive\b/gi, 'Сводка для руководства')
    throw new CcReportsApiError(localized, error.details || {})
  }
  return body as T
}

async function authedFetch(input: string, init?: RequestInit): Promise<Response> {
  await ensureDevSession()
  const headers = new Headers(init?.headers || {})
  const method = (init?.method || 'GET').toUpperCase()
  if (method !== 'GET' && method !== 'HEAD') {
    const csrf = readCsrfToken() || (await ensureCsrfToken(true))
    if (csrf) headers.set('X-CSRFToken', csrf)
  }
  return fetch(input, { credentials: 'include', ...init, headers })
}

export async function fetchCcAnalytics(
  filters: CcAnalyticsFilters = {},
): Promise<CcAnalyticsPayload> {
  const response = await authedFetch(`/api/reports/cc/analytics/${toQuery(filters)}`)
  return parseJson(response)
}

export async function fetchCcLive(): Promise<LiveDashboard> {
  const response = await authedFetch('/api/reports/cc/live/')
  return parseJson(response)
}

export async function fetchCcCatalog(
  filters: CcAnalyticsFilters = {},
): Promise<CatalogPayload> {
  const response = await authedFetch(`/api/reports/cc/catalog/${toQuery(filters)}`)
  return parseJson(response)
}

export async function fetchBuilderTemplates(): Promise<BuilderTemplatesPayload> {
  const response = await authedFetch('/api/reports/cc/builder/')
  return parseJson(response)
}

export async function saveBuilderTemplate(body: {
  name: string
  metrics: string[]
  view_mode?: string
  date_from?: string
  date_to?: string
  filters?: Record<string, unknown>
}): Promise<{ saved: SavedReportTemplate }> {
  const response = await authedFetch('/api/reports/cc/builder/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson(response)
}

export async function previewBuilder(body: {
  name?: string
  metrics?: string[]
  view_mode?: string
  date_from?: string
  date_to?: string
}): Promise<{
  name: string
  view_mode: string
  rows: { metric: string; value: number; unit: string }[]
  chart: { label: string; value: number }[]
  stub: boolean
  message: string
}> {
  const response = await authedFetch('/api/reports/cc/builder/preview/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson(response)
}

export async function downloadCcExport(
  filters: CcAnalyticsFilters,
  format: 'csv' | 'xlsx' | 'pdf',
): Promise<{ blob: Blob; filename: string }> {
  const response = await authedFetch(
    `/api/reports/cc/export/${toQuery(filters, { format })}`,
  )
  if (!response.ok) {
    try {
      await parseJson(response)
    } catch (error) {
      if (error instanceof CcReportsApiError) throw error
    }
    throw new CcReportsApiError(`HTTP ${response.status}`)
  }
  const disposition = response.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename="([^"]+)"/)
  const filename = match?.[1] || `cc-analytics.${format}`
  const blob = await response.blob()
  return { blob, filename }
}

export function triggerBrowserDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
