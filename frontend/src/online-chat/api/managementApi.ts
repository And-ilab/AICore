const BASE = '/api/v1/online-chat'

export type EntityId = string | number
export type OperatorPresence =
  | 'online'
  | 'busy'
  | 'break'
  | 'training'
  | 'lunch'
  | 'meeting'
  | 'tech_issue'
  | 'offline'

export interface Department {
  id: EntityId
  name: string
  code?: string
  description?: string
  is_active?: boolean
}

export interface ChatOperator {
  id: EntityId
  name: string
  username?: string
  role?: 'operator' | 'supervisor' | 'admin' | string
  department?: EntityId | Department | null
  department_id?: EntityId | null
  department_name?: string
  presence: OperatorPresence
  capacity: number
  active_dialogs?: number
  is_active?: boolean
  auto_assign?: boolean
  photo_url?: string
  skill_tags?: string[]
}

export interface WidgetFormField {
  key: string
  label: string
  required: boolean
  type?: 'text' | 'tel' | 'email'
}

export interface WidgetPlacement {
  id: EntityId
  name: string
  code?: string
  allowed_domains: string[]
  welcome_message: string
  offline_message: string
  department?: EntityId | Department | null
  department_id?: EntityId | null
  require_phone: boolean
  theme_accent: string
  form_fields: WidgetFormField[]
  is_active?: boolean
  counters?: ChannelCounters
}

export interface ChannelCounters {
  waiting?: number
  active?: number
  today?: number
  closed_today?: number
}

export interface ChatChannel {
  id: EntityId
  name: string
  kind?: string
  channel?: string
  endpoint?: string
  account?: string
  is_active: boolean
  configured?: boolean
  health_status?: string
  last_health_check_at?: string | null
  counters?: ChannelCounters
  form_fields?: WidgetFormField[]
  config?: Record<string, unknown>
}

export interface BaseMessage {
  id: EntityId
  message_type?: 'welcome' | 'offline' | 'broadcast' | string
  title: string
  text: string
  channel?: string
  channels: string[]
  send_phase: 'before_bot' | 'after_bot' | 'offline' | 'mid_dialog' | 'hold'
  sort_order: number
  delay_seconds?: number
  placement_id?: EntityId | null
  is_active: boolean
}

export interface RoutingRule {
  id: EntityId
  name: string
  priority: number
  department?: EntityId | Department | null
  department_id?: EntityId | null
  channel?: EntityId | ChatChannel | null
  channel_id?: EntityId | null
  max_load?: number
  is_active: boolean
}

export interface BotConfiguration {
  id: EntityId
  name: string
  department_id?: EntityId | null
  is_active: boolean
  welcome_message?: string
  offline_message?: string
  fallback_message: string
  handoff_message: string
  trigger_responses: Record<string, string>
  max_bot_turns: number
}

export interface DialogTopicNode {
  id: EntityId
  parent_id?: EntityId | null
  label: string
  full_path: string
  sort_order: number
  is_active: boolean
  is_selectable: boolean
  children?: DialogTopicNode[]
}

export interface SupervisorKpis {
  waiting?: number
  waiting_online?: number
  waiting_offline?: number
  active?: number
  online_operators?: number
  average_wait_seconds?: number
  average_wait_online_seconds?: number
  average_wait_offline_seconds?: number
  sla_percent?: number
  closed_today?: number
  [key: string]: string | number | undefined
}

export interface SupervisorOperator extends ChatOperator {
  load?: number
  closed_today?: number
  avg_first_response_seconds?: number | null
  time_in_dialogs_seconds?: number
  avg_dialog_seconds?: number | null
  channels_breakdown?: Record<string, number>
}

export interface SupervisorQueue {
  id?: EntityId
  name: string
  department?: string
  waiting: number
  waiting_online?: number
  waiting_offline?: number
  active?: number
  longest_wait_seconds?: number
}

export interface SupervisorOverview {
  ok: boolean
  kpis: SupervisorKpis
  operators: SupervisorOperator[]
  queues: SupervisorQueue[]
  demo?: boolean
  source?: string
}

export interface AnalyticsResponse {
  ok: boolean
  period: string
  kpis?: Record<string, string | number | null | undefined>
  [key: string]: unknown
}

export interface InternalMessage {
  id: EntityId
  text: string
  sender_id?: EntityId
  sender_name?: string
  recipient_id?: EntityId
  recipient_name?: string
  sender?: string
  recipient?: string
  dialog_id?: EntityId | null
  read_at?: string | null
  created_at?: string
}

export interface InternalMessagesResponse {
  ok: boolean
  items: InternalMessage[]
  count: number
  unread_count?: number
  operator_id?: string | null
}

export interface SeedRequest {
  operators: number
  clients: number
  messages_per_dialog: number
  auto_assign: boolean
  reset: boolean
}

export interface SeedResult {
  ok: boolean
  summary?: Record<string, string | number | boolean>
  operators?: ChatOperator[]
  operator_names?: string[]
  clients?: Array<{ id?: EntityId; name?: string }>
  client_ids?: EntityId[]
  [key: string]: unknown
}

type JsonObject = Record<string, unknown>

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}/${path}`, {
    credentials: 'include',
    ...init,
    headers: init?.body
      ? { 'Content-Type': 'application/json', ...init.headers }
      : init?.headers,
  })
  const body = (await response.json().catch(() => ({}))) as JsonObject
  if (!response.ok) {
    const detail = body.detail ?? body.error ?? body.message
    throw new Error(typeof detail === 'string' ? detail : `HTTP ${response.status}`)
  }
  return body as T
}

function listFrom<T>(body: unknown): T[] {
  if (Array.isArray(body)) return body as T[]
  const object = body as JsonObject
  const list = object.items ?? object.results
  return Array.isArray(list) ? list as T[] : []
}

function itemFrom<T>(body: unknown, key: string): T {
  const object = body as JsonObject
  return (object[key] ?? object.item ?? object) as T
}

const json = (value: unknown): RequestInit => ({ body: JSON.stringify(value) })

function resourceApi<T>(resource: string, singular: string, canDelete: boolean) {
  return {
    async list(): Promise<T[]> {
      return listFrom<T>(await request<unknown>(`${resource}/`))
    },
    async create(payload: Partial<T>): Promise<T> {
      return itemFrom<T>(
        await request<unknown>(`${resource}/`, { method: 'POST', ...json(payload) }),
        singular,
      )
    },
    async update(id: EntityId, payload: Partial<T>): Promise<T> {
      return itemFrom<T>(
        await request<unknown>(`${resource}/${id}/`, { method: 'PATCH', ...json(payload) }),
        singular,
      )
    },
    async remove(id: EntityId): Promise<void> {
      if (!canDelete) throw new Error('Удаление для этого ресурса не поддерживается')
      await request<unknown>(`${resource}/${id}/`, { method: 'DELETE' })
    },
  }
}

export const departmentsApi = resourceApi<Department>('departments', 'department', true)
export const operatorsApi = {
  ...resourceApi<ChatOperator>('operators', 'operator', false),
  async me(displayName?: string): Promise<ChatOperator> {
    const query = displayName ? `?display_name=${encodeURIComponent(displayName)}` : ''
    return itemFrom<ChatOperator>(await request<unknown>(`operators/me/${query}`), 'operator')
  },
  async updateMyPhoto(photoUrl: string, displayName?: string): Promise<ChatOperator> {
    return itemFrom<ChatOperator>(
      await request<unknown>('operators/me/photo/', {
        method: 'PATCH',
        ...json({ photo_url: photoUrl, display_name: displayName || '' }),
      }),
      'operator',
    )
  },
  async setPresence(id: EntityId, presence: OperatorPresence): Promise<ChatOperator> {
    return itemFrom<ChatOperator>(
      await request<unknown>(`operators/${id}/presence/`, {
        method: 'POST',
        ...json({ presence }),
      }),
      'operator',
    )
  },
}
export const placementsApi = resourceApi<WidgetPlacement>('placements', 'placement', true)
export const channelsApi = {
  ...resourceApi<ChatChannel>('channels', 'channel', false),
  async checkHealth(id: EntityId): Promise<ChatChannel> {
    return itemFrom<ChatChannel>(
      await request<unknown>(`channels/${id}/health/`, { method: 'POST' }),
      'channel',
    )
  },
}
export const routingRulesApi = resourceApi<RoutingRule>('routing-rules', 'routing_rule', true)
export const botsApi = resourceApi<BotConfiguration>('bots', 'bot', true)
export const baseMessagesApi = resourceApi<BaseMessage>('base-messages', 'base_message', true)
export const dialogTopicsApi = {
  async list(activeOnly = false): Promise<DialogTopicNode[]> {
    const query = activeOnly ? '?active=1' : '?active=0'
    return listFrom<DialogTopicNode>(await request<unknown>(`dialog-topics/${query}`))
  },
  async create(payload: Partial<DialogTopicNode> & { parent_id?: EntityId | null }): Promise<DialogTopicNode> {
    return itemFrom<DialogTopicNode>(
      await request<unknown>('dialog-topics/', { method: 'POST', ...json(payload) }),
      'dialog_topic',
    )
  },
  async update(id: EntityId, payload: Partial<DialogTopicNode> & { parent_id?: EntityId | null }): Promise<DialogTopicNode> {
    return itemFrom<DialogTopicNode>(
      await request<unknown>(`dialog-topics/${id}/`, { method: 'PATCH', ...json(payload) }),
      'dialog_topic',
    )
  },
  async remove(id: EntityId): Promise<void> {
    await request<unknown>(`dialog-topics/${id}/`, { method: 'DELETE' })
  },
  async reorder(payload: { id: EntityId; parent_id?: EntityId | null; sort_order?: number }): Promise<void> {
    await request<unknown>('dialog-topics/reorder/', { method: 'POST', ...json(payload) })
  },
}

export async function getSupervisorOverview(): Promise<SupervisorOverview> {
  return request<SupervisorOverview>('supervisor/overview/')
}

export async function getAnalytics(
  period: 'day' | 'week' | 'month' | 'custom' = 'week',
  range?: { date_from?: string; date_to?: string },
): Promise<AnalyticsResponse> {
  const params = new URLSearchParams()
  if (period !== 'custom') params.set('period', period)
  if (range?.date_from) params.set('date_from', range.date_from)
  if (range?.date_to) params.set('date_to', range.date_to)
  return request<AnalyticsResponse>(`analytics/?${params.toString()}`)
}

export async function getAdPendingOperators(): Promise<{
  ok: boolean
  items: {
    external_id: string
    display_name: string
    email: string
    ad_role: string
    detected_at: string
    needs: string[]
  }[]
  count: number
}> {
  return request('ad/pending-operators/')
}

export async function listInternalMessages(params?: {
  operatorId?: EntityId
  operatorName?: string
  peerId?: EntityId
}): Promise<InternalMessagesResponse> {
  const query = new URLSearchParams()
  if (params?.operatorId) query.set('operator_id', String(params.operatorId))
  if (params?.operatorName) query.set('operator_name', params.operatorName)
  if (params?.peerId) query.set('peer_id', String(params.peerId))
  const suffix = query.toString() ? `?${query.toString()}` : ''
  return request<InternalMessagesResponse>(`internal-messages/${suffix}`)
}

export async function sendInternalMessage(payload: {
  text: string
  sender_id?: EntityId
  sender_name?: string
  recipient_id?: EntityId
  recipient_name?: string
  dialog_id?: EntityId
}): Promise<InternalMessage> {
  return itemFrom<InternalMessage>(
    await request<unknown>('internal-messages/', { method: 'POST', ...json(payload) }),
    'message',
  )
}

export async function markInternalMessagesRead(payload: {
  operator_id?: EntityId
  operator_name?: string
  peer_id?: EntityId
}): Promise<{ ok: boolean; updated: number; unread_count: number }> {
  return request<{ ok: boolean; updated: number; unread_count: number }>(
    'internal-messages/read/',
    { method: 'POST', ...json(payload) },
  )
}

export async function getInternalUnreadCount(operatorName: string): Promise<{
  unread_count: number
  operator_id: string | null
}> {
  const body = await listInternalMessages({ operatorName })
  return {
    unread_count: body.unread_count ?? 0,
    operator_id: body.operator_id ?? null,
  }
}

export async function getSlaSettings(): Promise<{ first_response_seconds: number; updated_at?: string }> {
  const body = await request<{ ok: boolean; settings: { first_response_seconds: number; updated_at?: string } }>(
    'sla-settings/',
  )
  return body.settings
}

export async function updateSlaSettings(
  firstResponseSeconds: number,
): Promise<{ first_response_seconds: number; updated_at?: string }> {
  const body = await request<{ ok: boolean; settings: { first_response_seconds: number; updated_at?: string } }>(
    'sla-settings/',
    { method: 'PATCH', ...json({ first_response_seconds: firstResponseSeconds }) },
  )
  return body.settings
}

export type WorkDayOverride = {
  is_workday: boolean
  start_time?: string
  end_time?: string
}

export type WorkScheduleSettings = {
  enabled: boolean
  start_time: string
  end_time: string
  workdays: number[]
  holidays: string[]
  day_overrides: Record<string, WorkDayOverride>
  manual_override: 'auto' | 'open' | 'closed'
  is_open: boolean
  updated_at?: string
}

export async function getWorkScheduleSettings(): Promise<WorkScheduleSettings> {
  const body = await request<{ ok: boolean; settings: WorkScheduleSettings }>('work-schedule/')
  return body.settings
}

export async function updateWorkScheduleSettings(
  payload: Partial<WorkScheduleSettings>,
): Promise<WorkScheduleSettings> {
  const body = await request<{ ok: boolean; settings: WorkScheduleSettings }>(
    'work-schedule/',
    { method: 'PATCH', ...json(payload) },
  )
  return body.settings
}

export async function getWorkScheduleStatus(): Promise<{
  is_open: boolean
  enabled: boolean
  manual_override: string
  start_time: string
  end_time: string
}> {
  const body = await request<{
    ok: boolean
    is_open: boolean
    enabled: boolean
    manual_override: string
    start_time: string
    end_time: string
  }>('work-schedule/status/')
  return body
}

export async function controlWorkDay(
  action: 'start' | 'stop' | 'auto',
): Promise<{ is_open: boolean; assigned: number }> {
  const body = await request<{ ok: boolean; is_open: boolean; assigned: number }>(
    'work-schedule/control/',
    { method: 'POST', ...json({ action }) },
  )
  return { is_open: body.is_open, assigned: body.assigned ?? 0 }
}

export async function runRouting(): Promise<JsonObject> {
  return request<JsonObject>('routing/run/', { method: 'POST' })
}

export async function seedSimulation(payload: SeedRequest): Promise<SeedResult> {
  return request<SeedResult>('dev/seed/', { method: 'POST', ...json(payload) })
}

export async function resetSimulation(): Promise<{ ok: boolean; [key: string]: unknown }> {
  return request<{ ok: boolean; [key: string]: unknown }>('dev/reset/', { method: 'POST' })
}
