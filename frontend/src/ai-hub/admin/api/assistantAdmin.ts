import { ensureCsrfToken, ensureDevSession } from '../../../auth/ensureDevSession'

export type PromptType = 'system' | 'task' | 'scope'
export type PromptStatus = 'draft' | 'published'

export type AssistantKbStatus = 'idle' | 'indexing' | 'ready' | 'error'
export type AssistantDocumentStatus = 'uploaded' | 'indexed' | 'error'

export interface AssistantKbDocument {
  id: number
  filename: string
  content_type: string
  size_bytes: number
  status: AssistantDocumentStatus
  status_message: string
  chunk_count: number
  index_percent?: number
  uploaded_at?: string
  indexed_at?: string | null
  uploaded_by?: string
  url?: string
  permalink?: string
  source_label?: string
  readonly?: boolean
}

export type AssistantKbSource = 'manual' | 'website'

export interface AssistantCrawlJob {
  id: number
  status: 'queued' | 'crawling' | 'indexing' | 'ready' | 'failed' | string
  status_message: string
  pages_ok: number
  pages_4xx: number
  pages_5xx: number
  pages_skipped: number
  started_at: string | null
  finished_at: string | null
  elapsed_seconds: number | null
  created_by: string
  created_at: string
}

export interface AssistantKb {
  id: number
  name: string
  slug: string
  namespace: string
  isolated_from: string
  scope: string
  description: string
  status: AssistantKbStatus | string
  status_message?: string
  document_count: number
  index_percent?: number
  chunk_count?: number
  last_reindexed_at?: string | null
  created_at?: string
  updated_at?: string
  created_by?: string
  source?: AssistantKbSource | string
  source_label?: string
  start_url?: string
  crawl_depth?: number
  max_pages?: number
  ignore_robots?: boolean
  allowed_hosts?: string[]
  latest_job?: AssistantCrawlJob | null
  documents?: AssistantKbDocument[]
}

export interface AssistantPrompt {
  id: number
  name: string
  prompt_type: PromptType
  scope: string
  event_trigger: string
  body: string
  status: PromptStatus
  version: number
  kb_slug: string
  updated_by: string
  created_at: string
  updated_at: string
}

/** Orchestration events for Task skills on Capabilities screen. */
export const TASK_EVENT_TRIGGERS = [
  'Начало сессии',
  'Ответ в чате',
  'Запрос уточнения (QU)',
  'Контекст истории (auto/manual)',
  'Перевод EN→RU',
  'Перевод RU→EN',
  'Начало диалога',
] as const

export interface AssistantCapability {
  id: number
  code: string
  name: string
  description: string
  enabled: boolean
  deep_link: string
  category: string
  sort_order: number
}

export type AssistantSkillScope = 'org' | 'user'

export interface AssistantSkill {
  id: number
  code: string
  scope: AssistantSkillScope
  owner_id: number | null
  name: string
  alias: string
  instruction: string
  needs_attachment: boolean
  enabled: boolean
  department_scope: string
  updated_by: string
  created_at: string
  updated_at: string
}

interface ApiErrorPayload {
  error?: string
  details?: Record<string, string[]>
}

export class AssistantAdminApiError extends Error {
  readonly details: Record<string, string[]>

  constructor(message: string, details: Record<string, string[]> = {}) {
    super(message)
    this.details = details
  }
}

async function parseJson<T>(response: Response): Promise<T> {
  const text = await response.text()
  let body: T | ApiErrorPayload | null = null
  try {
    body = text ? (JSON.parse(text) as T | ApiErrorPayload) : null
  } catch {
    if (
      response.status === 403
      && /csrf|CSRF verification failed/i.test(text)
    ) {
      throw new AssistantAdminApiError('csrf_failed')
    }
    throw new AssistantAdminApiError(
      response.status === 401
        ? 'authentication_required'
        : response.status === 403
          ? 'permission_denied'
          : `Неверный ответ API (HTTP ${response.status}): ${text.trim().slice(0, 80) || 'пусто'}`,
    )
  }
  if (!response.ok) {
    const error = (body ?? {}) as ApiErrorPayload
    if (error.error) {
      throw new AssistantAdminApiError(error.error, error.details || {})
    }
    if (response.status === 401) {
      throw new AssistantAdminApiError('authentication_required')
    }
    if (response.status === 403) {
      throw new AssistantAdminApiError('permission_denied')
    }
    throw new AssistantAdminApiError(`HTTP ${response.status}`)
  }
  if (body == null) {
    throw new AssistantAdminApiError('empty_response')
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
        throw new AssistantAdminApiError('csrf_failed')
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

export async function listAssistantKbs(): Promise<AssistantKb[]> {
  const response = await authedFetch('/api/admin/assistant/kb/', {
    method: 'GET',
  })
  const body = await parseJson<{ items: AssistantKb[] }>(response)
  return body.items
}

export async function createAssistantKb(payload: {
  name: string
  slug?: string
  scope?: string
  description?: string
  source?: AssistantKbSource
  start_url?: string
  depth?: number
  max_pages?: number
  ignore_robots?: boolean
  allowed_hosts?: string[]
}): Promise<AssistantKb> {
  const response = await authedFetch('/api/admin/assistant/kb/', {
    method: 'POST',
    csrf: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseJson(response)
}

export async function getAssistantKb(id: number): Promise<AssistantKb> {
  const response = await authedFetch(`/api/admin/assistant/kb/${id}/`, {
    method: 'GET',
  })
  return parseJson(response)
}

export async function deleteAssistantKb(id: number): Promise<void> {
  const response = await authedFetch(`/api/admin/assistant/kb/${id}/`, {
    method: 'DELETE',
    csrf: true,
  })
  await parseJson<{ ok: boolean }>(response)
}

export async function uploadAssistantKbDocument(
  kbId: number,
  file: File,
  options: { reindex?: boolean } = {},
): Promise<{ knowledge_base: AssistantKb; document: AssistantKbDocument }> {
  const form = new FormData()
  form.append('file', file)
  // Default false: batch upload then one reindex (avoids N full CPU embeds).
  form.append('reindex', options.reindex ? '1' : '0')
  const response = await authedFetch(`/api/admin/assistant/kb/${kbId}/upload/`, {
    method: 'POST',
    csrf: true,
    body: form,
  })
  return parseJson(response)
}

export async function deleteAssistantKbDocument(
  kbId: number,
  documentId: number,
): Promise<AssistantKb> {
  const response = await authedFetch(
    `/api/admin/assistant/kb/${kbId}/documents/${documentId}/`,
    {
      method: 'DELETE',
      csrf: true,
    },
  )
  return parseJson(response)
}

export async function startAssistantKbCrawl(
  kbId: number,
  payload: {
    start_url?: string
    depth?: number
    max_pages?: number
    ignore_robots?: boolean
    allowed_hosts?: string[]
  } = {},
): Promise<{ knowledge_base: AssistantKb; job: AssistantCrawlJob }> {
  const response = await authedFetch(`/api/admin/assistant/kb/${kbId}/crawl/`, {
    method: 'POST',
    csrf: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseJson(response)
}

export async function getAssistantKbCrawl(
  kbId: number,
): Promise<{ knowledge_base: AssistantKb; job: AssistantCrawlJob | null }> {
  const response = await authedFetch(`/api/admin/assistant/kb/${kbId}/crawl/`, {
    method: 'GET',
  })
  return parseJson(response)
}

export async function reindexAssistantKb(kbId: number): Promise<AssistantKb> {
  const response = await authedFetch(`/api/admin/assistant/kb/${kbId}/reindex/`, {
    method: 'POST',
    csrf: true,
  })
  return parseJson(response)
}

export async function listAssistantPrompts(): Promise<AssistantPrompt[]> {
  const response = await authedFetch('/api/admin/assistant/prompts/', {
    method: 'GET',
  })
  const body = await parseJson<{ items: AssistantPrompt[] }>(response)
  return body.items
}

export async function createAssistantPrompt(payload: {
  name: string
  body: string
  prompt_type?: PromptType
  scope?: string
  event_trigger?: string
  kb_slug?: string
}): Promise<AssistantPrompt> {
  const response = await authedFetch('/api/admin/assistant/prompts/', {
    method: 'POST',
    csrf: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseJson(response)
}

export async function updateAssistantPrompt(
  id: number,
  payload: Partial<{
    name: string
    body: string
    prompt_type: PromptType
    scope: string
    event_trigger: string
    kb_slug: string
    status: PromptStatus
  }>,
): Promise<AssistantPrompt> {
  const response = await authedFetch(`/api/admin/assistant/prompts/${id}/`, {
    method: 'PUT',
    csrf: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseJson(response)
}

export async function deleteAssistantPrompt(id: number): Promise<void> {
  const response = await authedFetch(`/api/admin/assistant/prompts/${id}/`, {
    method: 'DELETE',
    csrf: true,
  })
  await parseJson<{ ok: boolean }>(response)
}

export async function listAssistantCapabilities(): Promise<AssistantCapability[]> {
  const response = await authedFetch('/api/admin/assistant/capabilities/', {
    method: 'GET',
  })
  const body = await parseJson<{ items: AssistantCapability[] }>(response)
  return body.items
}

export type DocTemplateFormat = 'docx' | 'pdf' | 'xlsx' | 'pptx' | 'bpmn' | 'txt' | 'mmd'

export interface DocTemplateField {
  id: string
  label: string
  required?: boolean
}

export interface AssistantDocTemplate {
  id: number
  name: string
  category: string
  output_format: DocTemplateFormat
  format_label: string
  body: string
  fields: DocTemplateField[]
  active: boolean
  updated_by: string
  created_at: string
  updated_at: string
}

export async function listAssistantDocTemplates(): Promise<AssistantDocTemplate[]> {
  const response = await authedFetch('/api/admin/assistant/doc-templates/', {
    method: 'GET',
  })
  const body = await parseJson<{ items: AssistantDocTemplate[] }>(response)
  return body.items
}

export async function createAssistantDocTemplate(payload: {
  name: string
  category?: string
  output_format?: DocTemplateFormat
  body: string
  fields?: DocTemplateField[]
  active?: boolean
}): Promise<AssistantDocTemplate> {
  const response = await authedFetch('/api/admin/assistant/doc-templates/', {
    method: 'POST',
    csrf: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseJson(response)
}

export async function updateAssistantDocTemplate(
  id: number,
  payload: Partial<{
    name: string
    category: string
    output_format: DocTemplateFormat
    body: string
    fields: DocTemplateField[]
    active: boolean
  }>,
): Promise<AssistantDocTemplate> {
  const response = await authedFetch(`/api/admin/assistant/doc-templates/${id}/`, {
    method: 'PUT',
    csrf: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseJson(response)
}

export async function deleteAssistantDocTemplate(id: number): Promise<void> {
  const response = await authedFetch(`/api/admin/assistant/doc-templates/${id}/`, {
    method: 'DELETE',
    csrf: true,
  })
  await parseJson<{ ok: boolean }>(response)
}

export async function listAssistantSkills(): Promise<AssistantSkill[]> {
  const response = await authedFetch('/api/admin/assistant/skills/', {
    method: 'GET',
  })
  const body = await parseJson<{ items: AssistantSkill[] }>(response)
  return body.items
}

export async function createAssistantSkill(payload: {
  name: string
  alias: string
  instruction: string
  needs_attachment?: boolean
  enabled?: boolean
  department_scope?: string
  code?: string
}): Promise<AssistantSkill> {
  const response = await authedFetch('/api/admin/assistant/skills/', {
    method: 'POST',
    csrf: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseJson(response)
}

export async function updateAssistantSkill(
  id: number,
  payload: Partial<{
    name: string
    alias: string
    instruction: string
    needs_attachment: boolean
    enabled: boolean
    department_scope: string
  }>,
): Promise<AssistantSkill> {
  const response = await authedFetch(`/api/admin/assistant/skills/${id}/`, {
    method: 'PATCH',
    csrf: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseJson(response)
}

export async function deleteAssistantSkill(id: number): Promise<void> {
  const response = await authedFetch(`/api/admin/assistant/skills/${id}/`, {
    method: 'DELETE',
    csrf: true,
  })
  await parseJson<{ ok: boolean }>(response)
}

export interface RpaScenario {
  id: number
  name: string
  code: string
  description: string
  active: boolean
}

export async function listRpaScenarios(): Promise<RpaScenario[]> {
  const response = await authedFetch('/api/admin/assistant/rpa/scenarios/', {
    method: 'GET',
  })
  const body = await parseJson<{ items: RpaScenario[] }>(response)
  if (!Array.isArray(body.items)) {
    throw new Error('Белый список пришёл в неожиданном виде')
  }
  return body.items
}

export async function createRpaScenario(payload: {
  name: string
  code: string
  description?: string
  active?: boolean
}): Promise<RpaScenario> {
  const response = await authedFetch('/api/admin/assistant/rpa/scenarios/', {
    method: 'POST',
    csrf: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseJson(response)
}

export async function updateRpaScenario(
  id: number,
  payload: Partial<Pick<RpaScenario, 'name' | 'code' | 'description' | 'active'>>,
): Promise<RpaScenario> {
  const response = await authedFetch(`/api/admin/assistant/rpa/scenarios/${id}/`, {
    method: 'PATCH',
    csrf: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseJson(response)
}

export interface SqlAccess {
  id: number
  name: string
  object_name: string
  description: string
  active: boolean
}

export async function listSqlAccess(): Promise<SqlAccess[]> {
  const response = await authedFetch('/api/admin/assistant/sql/access/', {
    method: 'GET',
  })
  const body = await parseJson<{ items: SqlAccess[] }>(response)
  if (!Array.isArray(body.items)) {
    throw new Error('Список доступов пришёл в неожиданном виде')
  }
  return body.items
}

export async function createSqlAccess(payload: {
  name: string
  object_name: string
  description?: string
  active?: boolean
}): Promise<SqlAccess> {
  const response = await authedFetch('/api/admin/assistant/sql/access/', {
    method: 'POST',
    csrf: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseJson(response)
}

export async function updateSqlAccess(
  id: number,
  payload: Partial<Pick<SqlAccess, 'name' | 'object_name' | 'description' | 'active'>>,
): Promise<SqlAccess> {
  const response = await authedFetch(`/api/admin/assistant/sql/access/${id}/`, {
    method: 'PATCH',
    csrf: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseJson(response)
}

export async function deleteSqlAccess(id: number): Promise<void> {
  const response = await authedFetch(`/api/admin/assistant/sql/access/${id}/`, {
    method: 'DELETE',
    csrf: true,
  })
  await parseJson<{ ok: boolean }>(response)
}

export async function deleteRpaScenario(id: number): Promise<void> {
  const response = await authedFetch(`/api/admin/assistant/rpa/scenarios/${id}/`, {
    method: 'DELETE',
    csrf: true,
  })
  await parseJson<{ ok: boolean }>(response)
}

export async function setCapabilityEnabled(
  code: string,
  enabled: boolean,
): Promise<AssistantCapability> {
  const response = await authedFetch(
    `/api/admin/assistant/capabilities/${code}/`,
    {
      method: 'PATCH',
      csrf: true,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    },
  )
  return parseJson(response)
}
