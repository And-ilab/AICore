/** HTTP + helpers for Django online_chat API (`/api/v1/online-chat/`). */

export type DialogStatus = 'waiting' | 'active' | 'closed' | 'blocked'

export type DialogSpeaker = 'client' | 'operator' | 'bot' | 'system'

export type ReceiptStatus = 'delivered' | 'read'

export type SlaTone = 'ok' | 'warn' | 'critical'

export type OnlineChatDialog = {
  id: string
  ref_code?: string
  widget_id: string
  placement: string
  channel: string
  status: DialogStatus
  outcome?: string
  routing_reason?: string
  initiated_by?: 'client' | 'operator'
  client_first_name: string
  client_last_name: string
  client_phone: string
  client_external_id?: string
  client_ip?: string
  client_name: string
  client_fields?: { label: string; value: string }[]
  client_online?: boolean
  operator_name: string
  operator_avatar?: string
  department_id?: string | null
  department_name?: string | null
  preview: string
  entry_url?: string
  close_topic: string
  close_topic_id?: string | null
  created_at: string
  updated_at: string
  accepted_at: string | null
  closed_at: string | null
  client_last_seen_at?: string | null
  wait_seconds: number
  /** Absolute ISO timestamp for client-side SLA stopwatch (no drift on refresh). */
  wait_anchor_at?: string | null
  needs_reply?: boolean
  /** Simulator / seed client — sufler must stay disabled. */
  is_test_client?: boolean
  has_feedback?: boolean
  feedback_rating?: number | null
  messages?: OnlineChatMessage[]
}

export type ClientHistoryItem = {
  id: string
  channel: string
  status: string
  outcome?: string
  topic?: string
  operator_name?: string
  preview?: string
  created_at: string
  closed_at?: string | null
  message_count?: number
}

export type ClientHistorySummaryBlock = {
  date_label: string
  topic: string
  essence?: string
  channel?: string
  operator_name?: string
}

export type ClientHistoryResponse = {
  ok: boolean
  items: ClientHistoryItem[]
  count: number
  previous_count?: number
  summary: string
  detailed_summary?: string
  summary_topics?: string[]
  detailed_blocks?: ClientHistorySummaryBlock[]
  is_first?: boolean
  repeat_hint?: string
}

export type AssignmentMode = 'strict_auto' | 'manual_plus_auto'

export type AssignmentSettingsResponse = {
  ok: boolean
  settings: {
    mode: AssignmentMode
    grace_seconds: number
    modes?: { id: AssignmentMode; label: string }[]
  }
}

export type CloseDialogResponse = {
  ok: boolean
  dialog: OnlineChatDialog
  assignment_grace_until?: string
  assignment_grace_seconds?: number
}

export type DialogTopicNode = {
  id: string
  parent_id: string | null
  label: string
  full_path: string
  sort_order: number
  is_active: boolean
  is_selectable: boolean
  children: DialogTopicNode[]
}

export type OnlineChatFeedback = {
  id: string
  dialog_id: string
  rating: number
  comment: string
  created_at: string
}

export type OnlineChatTranscriptEmail = {
  id: string
  dialog_id: string
  email: string
  status: 'pending' | 'sent' | 'failed'
  error_detail: string
  created_at: string
  sent_at: string | null
}

export type OnlineChatMessage = {
  id: string
  dialog_id: string
  speaker: DialogSpeaker
  text: string
  raw_text?: string
  receipt_status?: ReceiptStatus
  reply_to_id?: string | null
  quoted_text?: string
  edited_at?: string | null
  is_deleted?: boolean
  attachment_name?: string
  attachment_key?: string
  attachment_content_type?: string
  attachment_size?: number
  attachment_scan_status?: string
  created_at: string
  is_history?: boolean
}

export type OnlineChatClientBlock = {
  id: string
  phone: string
  phone_normalized: string
  reason: string
  blocked_by: string
  dialog_id: string | null
  is_active: boolean
  created_at: string
  lifted_at: string | null
}

async function parseJson<T>(response: Response): Promise<T> {
  const body = (await response.json()) as T & { detail?: string; error?: string }
  if (!response.ok) {
    throw new Error(body.detail || body.error || `HTTP ${response.status}`)
  }
  return body
}

export function formatWaitMmSs(totalSeconds: number): string {
  const sec = Math.max(0, Math.floor(totalSeconds))
  const mm = String(Math.floor(sec / 60)).padStart(2, '0')
  const ss = String(sec % 60).padStart(2, '0')
  return `${mm}:${ss}`
}

/** SLA tiers: green < 60s, yellow 60–119s, red ≥ 120s. */
export function slaToneFromSeconds(totalSeconds: number): SlaTone {
  if (totalSeconds >= 120) return 'critical'
  if (totalSeconds >= 60) return 'warn'
  return 'ok'
}

export function maskPhone(phone: string): string {
  const digits = phone.replace(/\D/g, '')
  if (digits.length < 4) return phone || '—'
  return `+${digits.slice(0, 3)} ** ***-**-${digits.slice(-2)}`
}

export function dialogRefCode(dialog: Pick<OnlineChatDialog, 'id' | 'ref_code'>): string {
  if (dialog.ref_code) return dialog.ref_code
  return dialog.id.replace(/-/g, '').slice(0, 6).toUpperCase()
}

export async function listDialogs(
  status?: DialogStatus,
  extras?: {
    client_online?: boolean
    initiated_by?: 'client' | 'operator'
    operator_name?: string
    channel?: string
    q?: string
    date_from?: string
    date_to?: string
    has_feedback?: boolean
    outcome?: string
    close_topic?: string
    client_ip?: string
    ratings?: string
  },
): Promise<OnlineChatDialog[]> {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (extras?.client_online === true) params.set('client_online', 'true')
  if (extras?.client_online === false) params.set('client_online', 'false')
  if (extras?.initiated_by) params.set('initiated_by', extras.initiated_by)
  if (extras?.operator_name) params.set('operator_name', extras.operator_name)
  if (extras?.channel) params.set('channel', extras.channel)
  if (extras?.q) params.set('q', extras.q)
  if (extras?.date_from) params.set('date_from', extras.date_from)
  if (extras?.date_to) params.set('date_to', extras.date_to)
  if (extras?.has_feedback === true) params.set('has_feedback', 'true')
  if (extras?.has_feedback === false) params.set('has_feedback', 'false')
  if (extras?.outcome) params.set('outcome', extras.outcome)
  if (extras?.close_topic) params.set('close_topic', extras.close_topic)
  if (extras?.client_ip) params.set('client_ip', extras.client_ip)
  if (extras?.ratings) params.set('ratings', extras.ratings)
  const query = params.toString() ? `?${params.toString()}` : ''
  const response = await fetch(`/api/v1/online-chat/dialogs/${query}`)
  const body = await parseJson<{ ok: boolean; items: OnlineChatDialog[] }>(response)
  return body.items
}

export async function getDialog(
  dialogId: string,
  extras?: { includeHistory?: boolean },
): Promise<OnlineChatDialog> {
  const query = extras?.includeHistory ? '?include_history=1' : ''
  const response = await fetch(`/api/v1/online-chat/dialogs/${dialogId}/${query}`)
  const body = await parseJson<{ ok: boolean; dialog: OnlineChatDialog }>(response)
  return body.dialog
}

export async function acceptDialog(
  dialogId: string,
  operatorName = 'Иванов И.И.',
): Promise<OnlineChatDialog> {
  const response = await fetch(`/api/v1/online-chat/dialogs/${dialogId}/accept/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ operator_name: operatorName }),
  })
  const body = await parseJson<{ ok: boolean; dialog: OnlineChatDialog }>(response)
  return body.dialog
}

export async function transferDialogRemote(
  dialogId: string,
  toOperatorName: string,
  fromOperatorName = '',
): Promise<OnlineChatDialog> {
  const response = await fetch(`/api/v1/online-chat/dialogs/${dialogId}/transfer/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      to_operator_name: toOperatorName,
      from_operator_name: fromOperatorName,
    }),
  })
  const body = await parseJson<{ ok: boolean; dialog: OnlineChatDialog }>(response)
  return body.dialog
}

export async function closeDialogRemote(
  dialogId: string,
  topic: string,
  topicId?: string,
): Promise<CloseDialogResponse> {
  const response = await fetch(`/api/v1/online-chat/dialogs/${dialogId}/close/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic, topic_id: topicId || '' }),
  })
  return parseJson<CloseDialogResponse>(response)
}

export async function fetchDialogTopics(activeOnly = true): Promise<DialogTopicNode[]> {
  const query = activeOnly ? '?active=1' : ''
  const response = await fetch(`/api/v1/online-chat/dialog-topics/${query}`)
  const body = await parseJson<{ ok: boolean; items: DialogTopicNode[] }>(response)
  return body.items || []
}

export async function suggestDialogTopic(articleTitles: string[]): Promise<{
  topic_id: string | null
  topic_path: string
  confidence: number
}> {
  const response = await fetch('/api/v1/online-chat/dialog-topics/suggest/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ article_titles: articleTitles }),
  })
  return parseJson<{
    ok: boolean
    topic_id: string | null
    topic_path: string
    confidence: number
  }>(response)
}

export async function fetchAssignmentSettings(): Promise<AssignmentSettingsResponse['settings']> {
  const response = await fetch('/api/v1/online-chat/assignment-settings/')
  const body = await parseJson<AssignmentSettingsResponse>(response)
  return body.settings
}

export async function updateAssignmentSettings(
  mode: AssignmentMode,
): Promise<AssignmentSettingsResponse['settings']> {
  const response = await fetch('/api/v1/online-chat/assignment-settings/', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode }),
  })
  const body = await parseJson<AssignmentSettingsResponse>(response)
  return body.settings
}

export async function submitSuflerHintFeedback(payload: {
  dialog_id?: string
  operator_name?: string
  query?: string
  hint_rank?: number
  hint_text?: string
  choice: 'used' | 'not_used' | 'partial'
  relevance_percent?: number
  citation_title?: string
  kb_id?: string
  request_id?: string
  source?: string
  call_id?: string
}): Promise<void> {
  const response = await fetch('/api/v1/online-chat/sufler-feedback/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  await parseJson<{ ok: boolean }>(response)
}

export async function reportSuflerOutage(payload: {
  dialog_id?: string
  operator_name?: string
  query?: string
  detail?: string
}): Promise<void> {
  const response = await fetch('/api/v1/online-chat/sufler-outage/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  await parseJson<{ ok: boolean }>(response)
}

export async function submitDialogFeedback(
  dialogId: string,
  rating: number,
  comment = '',
): Promise<OnlineChatFeedback> {
  const response = await fetch(`/api/v1/online-chat/dialogs/${dialogId}/feedback/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rating, comment }),
  })
  const body = await parseJson<{ ok: boolean; feedback: OnlineChatFeedback }>(response)
  return body.feedback
}

export async function sendDialogTranscript(
  dialogId: string,
  email: string,
): Promise<OnlineChatTranscriptEmail> {
  const response = await fetch(
    `/api/v1/online-chat/dialogs/${dialogId}/send-transcript/`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    },
  )
  const body = await parseJson<{
    ok: boolean
    transcript_email: OnlineChatTranscriptEmail
  }>(response)
  return body.transcript_email
}

export async function blockDialogRemote(
  dialogId: string,
  extras?: { blocked_by?: string; reason?: string },
): Promise<OnlineChatDialog> {
  const response = await fetch(`/api/v1/online-chat/dialogs/${dialogId}/block/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(extras || {}),
  })
  const body = await parseJson<{ ok: boolean; dialog: OnlineChatDialog }>(response)
  return body.dialog
}

export async function listClientBlocks(activeOnly = true): Promise<OnlineChatClientBlock[]> {
  const query = activeOnly ? '?active=1' : '?active=0'
  const response = await fetch(`/api/v1/online-chat/blocks/${query}`)
  const body = await parseJson<{ ok: boolean; items: OnlineChatClientBlock[] }>(response)
  return body.items
}

export async function liftClientBlock(
  blockId: string,
  liftedBy = 'admin',
): Promise<OnlineChatClientBlock> {
  const response = await fetch(`/api/v1/online-chat/blocks/${blockId}/lift/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lifted_by: liftedBy }),
  })
  const body = await parseJson<{ ok: boolean; block: OnlineChatClientBlock }>(response)
  return body.block
}

export async function sendOperatorMessage(
  dialogId: string,
  text: string,
  extras?: {
    reply_to_id?: string
    attachment_name?: string
    operator_name?: string
    response_origin?: string
    sufler_suggestion_text?: string
  },
): Promise<OnlineChatMessage> {
  const response = await fetch(`/api/v1/online-chat/dialogs/${dialogId}/messages/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text,
      speaker: 'operator',
      reply_to_id: extras?.reply_to_id,
      attachment_name: extras?.attachment_name,
      operator_name: extras?.operator_name,
      response_origin: extras?.response_origin,
      sufler_suggestion_text: extras?.sufler_suggestion_text,
    }),
  })
  const body = await parseJson<{ ok: boolean; message: OnlineChatMessage }>(response)
  return body.message
}

export async function uploadOperatorAttachment(
  dialogId: string,
  file: File,
  operatorName = '',
  text = '',
): Promise<OnlineChatMessage> {
  const form = new FormData()
  form.append('file', file)
  form.append('speaker', 'operator')
  form.append('operator_name', operatorName)
  if (text.trim()) form.append('text', text.trim())
  const response = await fetch(
    `/api/v1/online-chat/dialogs/${dialogId}/attachments/`,
    { method: 'POST', body: form, credentials: 'include' },
  )
  const body = await parseJson<{ ok: boolean; message: OnlineChatMessage }>(response)
  return body.message
}

export function attachmentDownloadUrl(dialogId: string, messageId: string): string {
  return `/api/v1/online-chat/dialogs/${dialogId}/attachments/${messageId}/`
}

export function canDownloadAttachment(message: Pick<
  OnlineChatMessage,
  'attachment_key' | 'attachment_scan_status' | 'is_deleted' | 'attachment_name'
>): boolean {
  if (message.is_deleted || !message.attachment_name) return false
  if (!message.attachment_key) return false
  const status = message.attachment_scan_status || 'not_required'
  return status === 'clean' || status === 'not_required'
}

/** Fetch attachment with credentials and trigger browser download. */
export async function downloadAttachment(
  dialogId: string,
  messageId: string,
  filename: string,
): Promise<void> {
  const response = await fetch(attachmentDownloadUrl(dialogId, messageId), {
    credentials: 'include',
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({})) as { detail?: string }
    throw new Error(detail.detail || `HTTP ${response.status}`)
  }
  const blob = await response.blob()
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = filename || 'attachment'
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(objectUrl)
}

export async function fetchClientHistory(params: {
  dialogId?: string
  phone?: string
  externalId?: string
}): Promise<ClientHistoryResponse> {
  const query = new URLSearchParams()
  if (params.dialogId) query.set('dialog_id', params.dialogId)
  if (params.phone) query.set('phone', params.phone)
  if (params.externalId) query.set('external_id', params.externalId)
  const response = await fetch(`/api/v1/online-chat/history/?${query.toString()}`, {
    credentials: 'include',
  })
  return parseJson<ClientHistoryResponse>(response)
}

export async function editMessageRemote(
  dialogId: string,
  messageId: string,
  text: string,
): Promise<OnlineChatMessage> {
  const response = await fetch(
    `/api/v1/online-chat/dialogs/${dialogId}/messages/${messageId}/`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    },
  )
  const body = await parseJson<{ ok: boolean; message: OnlineChatMessage }>(response)
  return body.message
}

export async function deleteMessageRemote(
  dialogId: string,
  messageId: string,
): Promise<OnlineChatMessage> {
  const response = await fetch(
    `/api/v1/online-chat/dialogs/${dialogId}/messages/${messageId}/`,
    { method: 'DELETE' },
  )
  const body = await parseJson<{ ok: boolean; message: OnlineChatMessage }>(response)
  return body.message
}

export async function markDialogRead(
  dialogId: string,
  reader: 'client' | 'operator',
): Promise<{ message_ids: string[]; messages: OnlineChatMessage[] }> {
  const response = await fetch(`/api/v1/online-chat/dialogs/${dialogId}/read/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reader }),
  })
  const body = await parseJson<{
    ok: boolean
    message_ids: string[]
    messages: OnlineChatMessage[]
  }>(response)
  return { message_ids: body.message_ids, messages: body.messages }
}

export async function createOperatorInitiatedDialog(payload: {
  text: string
  first_name?: string
  last_name?: string
  phone?: string
  operator_name: string
}): Promise<OnlineChatDialog> {
  const response = await fetch('/api/v1/online-chat/dialogs/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...payload,
      initiated_by: 'operator',
      channel: 'widget',
    }),
  })
  const body = await parseJson<{ ok: boolean; dialog: OnlineChatDialog }>(response)
  return body.dialog
}

export function onlineChatArmWsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}/ws/online-chat/arm/`
}

export const REPLY_TEMPLATES = [
  'Здравствуйте! Чем могу помочь?',
  'Проверяю информацию, одну минуту.',
  'Подскажите, пожалуйста, номер карты (последние 4 цифры).',
  'Операция выполнена. Могу ещё чем-то помочь?',
  'Спасибо за обращение! Хорошего дня.',
] as const
