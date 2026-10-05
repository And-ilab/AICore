/** Russian labels for report UI (field keys, statuses, metrics). */

const FIELD_LABELS: Record<string, string> = {
  date: 'Дата',
  channel: 'Канал',
  channel_label: 'Канал',
  operator: 'Оператор',
  sessions: 'Обращений',
  closed: 'Закрыто',
  waiting: 'В очереди',
  active: 'В работе',
  avg_first_response_sec: 'Среднее время первого ответа, с',
  avg_aht_sec: 'Среднее время обработки, с',
  aht_sec: 'Время обработки, с',
  sla_ok_pct: 'Соблюдение SLA, %',
  sla_ok: 'SLA соблюдён',
  avg_rating: 'Средняя оценка',
  rating: 'Оценка',
  ratings: 'Оценок',
  ref: 'Номер',
  client: 'Клиент',
  phone: 'Телефон',
  status: 'Статус',
  outcome: 'Результат обращения',
  topic: 'Тематика',
  topics: 'Тематик',
  created_at: 'Создан',
  closed_at: 'Закрыт',
  messages: 'Сообщений',
  summary: 'Краткое саммари',
  wait_sec: 'Ожидание до назначения, с',
  first_response_sec: 'Первый ответ клиенту, с',
  result: 'Результат обращения',
  mark: 'Отметка',
  prev_dialogs: 'За прошлый период (такая же длительность)',
  role: 'Роль',
  role_label: 'Роль',
  comment: 'Комментарий',
  dialogs: 'Диалогов',
  share_pct: 'Доля, %',
  growth_pct: 'Рост, %',
  label: 'Показатель',
  count: 'Количество',
  pct: 'Доля, %',
  choice: 'Отметка',
  value: 'Значение',
  useful_pct: 'Полезность суфлёра, %',
  incomplete_pct: 'Неполный ответ, %',
  unused_pct: 'Не воспользовался, %',
  avg_relevance: 'Средняя релевантность, %',
  answers: 'Ответов',
  used_pct: 'Воспользовался, %',
  reason: 'Причина',
  example: 'Пример',
  relevance_pct: 'Релевантность, %',
  at: 'Когда',
  query: 'Запрос',
  hint: 'Подсказка',
  repeats: 'Повторов',
  channels: 'Каналы',
  metric: 'Показатель',
  unit: 'Ед.',
  online_chat: 'Онлайн-чат',
  telephony: 'Телефония',
  total: 'Итого',
  p95_first_response_sec: 'p95 первого ответа, с',
  p95_ms: 'p95 первого ответа, мс',
  dialogs_total: 'Число диалогов',
  dialogs_closed: 'Закрытых диалогов',
  sla_pct: 'Соблюдение SLA первого ответа, %',
  csat: 'Средняя оценка клиента',
  relevance_avg: 'Средняя релевантность, %',
  incorrect_llm: 'Доля «не использовал», %',
  topics_top: 'Число тематик',
  sufler_used_pct: 'Использование суфлёра, %',
  aht: 'Среднее время обработки, с',
  target_sec: 'Целевой SLA, с',
  answered: 'С ответом',
  operators: 'Операторов',
  cases: 'Кейсов',
  clients: 'Клиентов',
  repeat_clients: 'Повторных клиентов',
  repeat_pct: 'Доля повторных, %',
  sufler: 'Отметок суфлёра',
  sufler_total: 'Отметок суфлёра',
  sufler_avg_relevance: 'Средняя релевантность',
  resolution_rate: 'Доля закрытых, %',
  rows: 'Строк',
  period: 'Период',
  category: 'Категория',
  department: 'Отдел',
  incoming: 'Обращений поступило',
  first_time: 'Запрос впервые',
  operator_messages: 'Сообщений операторов',
  visitor_messages: 'Сообщений посетителей',
  avg_queue: 'Среднее время в очереди',
  avg_operator_queue: 'Среднее время ожидания оператора',
  avg_missed_wait: 'Среднее время ожидания для пропущенных',
  avg_reply: 'Среднее время ответа',
  answered_20s: 'Ответ дан за 20 с.',
  pct_10s: 'Ответ за 10 сек',
  pct_20s: 'Ответ за 20 сек',
  pct_30s: 'Ответ за 30 сек',
  pct_40s: 'Ответ за 40 сек',
  missed: 'Пропущенных',
  rejected: 'Отказов',
  ignored_invites: 'Непринятых приглашений',
  max_operators_online: 'Максимум операторов онлайн',
  queued: 'Офлайновых попало в общую очередь',
  assigned: 'Офлайновых назначено на оператора',
  processed: 'Обработанных офлайн',
  interval: 'Интервал',
  offline_assigned: 'Офлайновых назначено на оператора',
  offline_processed: 'Обработанных офлайн',
  avg_length: 'Средняя длина сообщения (в символах)',
  invited: 'Кол-во приглашённых посетителей',
  transfers_out: 'Кол-во переводов из отдела',
  transfers_in: 'Кол-во переводов в отдел',
  busy_notices: 'Кол-во сообщений о занятости оператора',
  avg_wait: 'Среднее время ожидания для пропущенных',
  time_online: 'Время онлайн',
  time_in_dialogs: 'Время в диалогах',
  time_in_dialogs_sum: 'Суммарное время в диалогах',
  one_chat: 'Время с одним диалогом',
  two_chats: 'Время с двумя диалогами',
  three_chats: 'Время c тремя и более диалогами',
  avg_dialog: 'Среднее время в диалоге',
  on_phone: 'На телефоне',
  training: 'На проведении инструктажа',
  tech: 'Технический перерыв',
  short_break: 'Короткий перерыв',
  invisible: 'Невидимка',
  offline_process: 'Обработка офлайн-обращений',
}

const STATUS_LABELS: Record<string, string> = {
  waiting: 'В очереди',
  active: 'В работе',
  closed: 'Закрыт',
  blocked: 'Заблокирован',
  offline: 'Офлайн',
  lost: 'Потерянный',
  rejected: 'Отказ клиента',
  declined: 'Отказ клиента',
  resolved: 'Решён',
  escalated: 'Эскалация',
  used: 'Воспользовался',
  not_used: 'Не воспользовался',
  partial: 'Неполный ответ',
  incomplete: 'Неполный ответ',
  online: 'В сети',
  busy: 'Занят',
  break: 'Перерыв',
  lunch: 'Обед',
  training: 'Обучение',
  meeting: 'Совещание',
  tech_issue: 'Тех. проблема',
  true: 'да',
  false: 'нет',
}

const SUMMARY_LABELS: Record<string, string> = {
  ...FIELD_LABELS,
  dialogs: 'Диалогов',
  closed: 'Закрыто',
  channels: 'Каналов',
  sla_ok_pct: 'Соблюдение SLA, %',
  avg_first_response_sec: 'Ср. время первого ответа, с',
  avg_wait_sec: 'Ср. ожидание, с',
  avg_rating: 'Средняя оценка',
  ratings: 'Оценок',
  operators: 'Операторов',
  topics: 'Тематик',
  total: 'Всего отметок',
  used_pct: 'Воспользовался, %',
  avg_relevance: 'Ср. релевантность, %',
  answers: 'Ответов',
  avg_aht_sec: 'Ср. время обработки, с',
  clients: 'Клиентов',
  repeat_clients: 'Повторных клиентов',
  repeat_pct: 'Доля повторных, %',
  cases: 'Кейсов',
  sufler: 'Отметок суфлёра',
  target_sec: 'Целевой SLA, с',
  answered: 'С ответом',
}

export function fieldLabel(key: string): string {
  return FIELD_LABELS[key] || key
}

export function summaryLabel(key: string): string {
  return SUMMARY_LABELS[key] || FIELD_LABELS[key] || key
}

export function localizeCell(value: unknown): string {
  if (value == null || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'да' : 'нет'
  const raw = String(value)
  if (raw === 'telegram_inline' || raw === 'telegram_inline_keyboard') return '—'
  if (/^\d{4}-\d{2}-\d{2}T/.test(raw)) {
    try {
      return new Date(raw).toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return raw
    }
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
    try {
      return new Date(`${raw}T12:00:00`).toLocaleDateString('ru-RU')
    } catch {
      return raw
    }
  }
  return (
    STATUS_LABELS[raw]
    || STATUS_LABELS[raw.toLowerCase()]
    || FIELD_LABELS[raw]
    || raw
  )
}

export function metricLabel(
  metricId: string,
  catalog: { id: string; label: string }[] = [],
): string {
  return catalog.find((item) => item.id === metricId)?.label || FIELD_LABELS[metricId] || metricId
}
