/** Demo datasets for II.6 reports UI (canvas-parity, no backend required). */

export type ReportViewMode = 'table' | 'pie' | 'bar'

export type ReportTypeId =
  | 'rpt-01'
  | 'rpt-02'
  | 'rpt-04'
  | 'rpt-05'
  | 'rpt-06'
  | 'rpt-07'
  | 'rpt-08'
  | 'rpt-09'
  | 'rpt-10'
  | 'rpt-11'
  | 'rpt-12'
  | 'rpt-13'
  | 'chat-period'
  | 'chat-sla'
  | 'chat-ratings'
  | 'chat-operators'
  | 'chat-topics'
  | 'chat-offline'

export const REPORT_TYPES: {
  id: ReportTypeId
  label: string
  defaultView: ReportViewMode
  group: string
}[] = [
  { id: 'chat-period', label: 'Онлайн-чат: обращения за период', defaultView: 'bar', group: 'Общая отчётность' },
  { id: 'chat-sla', label: 'SLA и время ожидания', defaultView: 'bar', group: 'Общая отчётность' },
  { id: 'chat-operators', label: 'Нагрузка и эффективность операторов', defaultView: 'table', group: 'Общая отчётность' },
  { id: 'chat-ratings', label: 'Оценки клиентов', defaultView: 'pie', group: 'Онлайн-чат' },
  { id: 'chat-topics', label: 'Тематики закрытия диалогов', defaultView: 'pie', group: 'Онлайн-чат' },
  { id: 'chat-offline', label: 'Офлайн / потерянные / отказы', defaultView: 'pie', group: 'Онлайн-чат' },
  { id: 'rpt-02', label: 'Релевантность подсказок', defaultView: 'pie', group: 'Релевантность' },
  { id: 'rpt-08', label: 'Полезность по отметкам операторов', defaultView: 'pie', group: 'Оценки операторов' },
  { id: 'rpt-04', label: 'Корректность: подсказка vs ответ оператора', defaultView: 'bar', group: 'Качество ответов' },
  { id: 'rpt-05', label: 'Производительность (p95, AHT)', defaultView: 'bar', group: 'Производительность' },
  { id: 'rpt-07', label: 'Релевантность по каналам и тематикам', defaultView: 'bar', group: 'По каналам' },
  { id: 'rpt-09', label: 'Ошибки распознавания и подсказок', defaultView: 'table', group: 'Ошибки' },
  { id: 'rpt-11', label: 'Сводка по каналам и качеству', defaultView: 'bar', group: 'Сводные отчёты' },
  { id: 'rpt-12', label: 'Повторные обращения', defaultView: 'table', group: 'Повторные обращения' },
  { id: 'rpt-13', label: 'Закономерности по тематике', defaultView: 'table', group: 'Закономерности' },
  { id: 'rpt-06', label: 'Оповещения при отклонении порогов', defaultView: 'table', group: 'Оповещения' },
  { id: 'rpt-10', label: 'Периодический отчёт для руководства', defaultView: 'table', group: 'Для руководства' },
  { id: 'rpt-01', label: 'Мониторинг этапов обработки', defaultView: 'table', group: 'Контроль обработки' },
]

export const CLOSE_TOPICS = [
  'Карты и счета',
  'Платежи / ЕРИП',
  'Мобильный банк',
  'Кредиты',
  'Ипотека',
  'Вклады',
  'Юрлица',
  'Блокировка / безопасность',
  'Техническая поддержка',
  'Прочее',
]

export const CHANNEL_OPTIONS = [
  { value: 'all', label: 'Все каналы' },
  { value: 'widget', label: 'Виджет сайта' },
  { value: 'telegram', label: 'Telegram' },
  { value: 'viber', label: 'Viber' },
  { value: 'vk', label: 'ВКонтакте' },
  { value: 'ok', label: 'Одноклассники' },
  { value: 'phone', label: 'Телефония' },
]

export const SUFLER_REPORT_IDS = new Set([
  'usefulness',
  'relevance',
  'errors',
  'rpt-08',
  'rpt-02',
  'rpt-07',
  'rpt-09',
])

export const DEPARTMENT_OPTIONS = [
  { value: 'all', label: 'Все отделы' },
  { value: 'retail', label: 'Розничные продукты' },
  { value: 'legal', label: 'Юрлица' },
  { value: 'mortgage', label: 'Ипотека' },
]

export function channelLabelRu(channel: string): string {
  const map: Record<string, string> = {
    telephony: 'Телефония',
    phone: 'Телефония',
    online_chat: 'Онлайн-чат',
    widget: 'Виджет сайта',
    telegram: 'Telegram',
    viber: 'Viber',
    vk: 'ВКонтакте',
    ok: 'Одноклассники',
    all: 'Все каналы',
    '': 'Все каналы',
  }
  return map[channel] || channel
}

export function statusLabelRu(status: string): string {
  const map: Record<string, string> = {
    online: 'в сети',
    busy: 'занят',
    break: 'перерыв',
    offline: 'не в сети',
    lunch: 'обед',
    training: 'обучение',
    meeting: 'совещание',
    tech_issue: 'тех. проблема',
    closed: 'Закрыт',
    active: 'В работе',
    waiting: 'Ожидает',
    lost: 'Потерянный',
    declined: 'Отказ клиента',
    offline_queue: 'Офлайн',
  }
  return map[status] || status
}

export type PieSlice = {
  label: string
  value: number
  tone?: 'success' | 'warning' | 'danger' | 'info' | 'neutral'
}

export type ReportPreview = {
  title: string
  table?: { headers: string[]; rows: string[][] }
  pie?: PieSlice[]
  bar?: {
    categories: string[]
    series: { name: string; data: number[]; tone?: string }[]
    valueSuffix?: string
  }
}

export function getReportPreview(
  reportId: ReportTypeId,
  view: ReportViewMode,
): ReportPreview {
  const meta = REPORT_TYPES.find((item) => item.id === reportId)

  const pieFor = (): PieSlice[] => {
    if (reportId === 'chat-ratings') {
      return [
        { label: '5 ★', value: 412, tone: 'success' },
        { label: '4 ★', value: 286, tone: 'success' },
        { label: '3 ★', value: 74, tone: 'warning' },
        { label: '1–2 ★', value: 28, tone: 'danger' },
      ]
    }
    if (reportId === 'chat-topics') {
      return [
        { label: 'Карты и счета', value: 34 },
        { label: 'Платежи', value: 22 },
        { label: 'Мобильный банк', value: 18 },
        { label: 'Кредиты', value: 14 },
        { label: 'Прочее', value: 12 },
      ]
    }
    if (reportId === 'chat-offline') {
      return [
        { label: 'Закрыты online', value: 842, tone: 'success' },
        { label: 'Офлайн', value: 96, tone: 'info' },
        { label: 'Потерянные', value: 41, tone: 'warning' },
        { label: 'Отказы', value: 23, tone: 'neutral' },
      ]
    }
    return [
      { label: 'Воспользовался', value: 58, tone: 'success' },
      { label: 'Неполный ответ', value: 24, tone: 'warning' },
      { label: 'Не воспользовался', value: 18, tone: 'danger' },
    ]
  }

  if (
    reportId === 'rpt-02'
    || reportId === 'rpt-08'
    || reportId === 'chat-ratings'
    || reportId === 'chat-topics'
    || reportId === 'chat-offline'
    || view === 'pie'
  ) {
    const pie = pieFor()
    const total = pie.reduce((sum, row) => sum + row.value, 0) || 1
    return {
      title: meta?.label ?? 'Распределение',
      pie: view === 'pie' ? pie : undefined,
      bar:
        view === 'bar'
          ? {
              categories: pie.map((item) => item.label),
              series: [{ name: 'Количество', data: pie.map((item) => item.value) }],
            }
          : undefined,
      table:
        view === 'table'
          ? {
              headers: ['Категория', 'Кол-во', 'Доля'],
              rows: pie.map((item) => [
                item.label,
                String(item.value),
                `${Math.round((item.value / total) * 100)}%`,
              ]),
            }
          : undefined,
    }
  }

  if (
    view === 'bar'
    || reportId === 'rpt-05'
    || reportId === 'chat-sla'
    || reportId === 'chat-period'
    || reportId === 'rpt-07'
    || reportId === 'rpt-11'
    || reportId === 'rpt-04'
  ) {
    const categories = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    let bar: ReportPreview['bar']
    if (reportId === 'rpt-05') {
      bar = {
        categories,
        series: [
          { name: 'AHT (мин)', data: [6.2, 5.8, 6.5, 5.9, 6.1, 4.2, 3.8] },
          { name: 'p95 подсказки (с)', data: [2.1, 1.9, 2.4, 2.0, 2.2, 1.6, 1.5] },
        ],
      }
    } else if (reportId === 'chat-sla') {
      bar = {
        categories,
        valueSuffix: '%',
        series: [
          { name: 'SLA ≤ целевого', data: [94, 96, 92, 95, 93, 98, 99] },
          { name: 'Ср. ожидание (мин)', data: [1.8, 1.4, 2.1, 1.6, 1.9, 0.8, 0.5] },
        ],
      }
    } else if (reportId === 'rpt-07' || reportId === 'rpt-11') {
      bar = {
        categories: ['Виджет', 'Telegram', 'Viber', 'ВК', 'Телефония'],
        series: [
          { name: 'Обращений', data: [620, 210, 86, 54, 314] },
          { name: 'Закрыто', data: [582, 198, 79, 51, 288], tone: 'success' },
        ],
      }
    } else if (reportId === 'rpt-04') {
      bar = {
        categories: ['Совпало', 'Частично', 'Не использовано', 'Неверно'],
        series: [{ name: 'Доля, %', data: [61, 22, 12, 5] }],
        valueSuffix: '%',
      }
    } else {
      bar = {
        categories,
        series: [
          { name: 'Виджет', data: [120, 134, 128, 141, 136, 62, 48] },
          { name: 'Telegram', data: [44, 52, 49, 58, 51, 22, 18] },
          { name: 'Viber', data: [18, 21, 19, 24, 20, 9, 7] },
          { name: 'Телефония', data: [88, 92, 85, 97, 90, 40, 28] },
        ],
      }
    }
    return {
      title: meta?.label ?? 'Динамика',
      bar: view === 'bar' || view === 'table' ? bar : undefined,
      table: {
        headers: ['День', ...(bar?.series.map((s) => s.name) ?? [])],
        rows: (bar?.categories ?? []).map((day, index) => [
          day,
          ...(bar?.series.map((series) => String(series.data[index])) ?? []),
        ]),
      },
    }
  }

  if (reportId === 'chat-operators') {
    return {
      title: meta?.label ?? 'Операторы',
      table: {
        headers: ['Оператор', 'Диалогов', 'AHT', 'CSAT', 'SLA'],
        rows: [
          ['Иванов И.И.', '148', '5:42', '4.7', '96%'],
          ['Петрова М.С.', '132', '6:10', '4.6', '94%'],
          ['Козлов Д.В.', '121', '5:55', '4.5', '95%'],
          ['Сидорова А.П.', '109', '6:28', '4.4', '92%'],
          ['Орлов Н.В.', '97', '5:18', '4.8', '97%'],
          ['Васильева Е.К.', '88', '6:02', '4.5', '93%'],
        ],
      },
    }
  }

  if (reportId === 'rpt-12' || reportId === 'rpt-13') {
    return {
      title: meta?.label ?? 'Тематики',
      table: {
        headers: ['Тематика', 'Обращений', 'Рост', 'Повторные'],
        rows: [
          ['Лимиты ATM', '96', '+18%', '14'],
          ['Карты и счета', '84', '+4%', '9'],
          ['ЕРИП', '71', '−2%', '6'],
          ['Кредиты', '55', '+8%', '11'],
          ['Мобильный банк', '49', '+12%', '7'],
        ],
      },
    }
  }

  if (reportId === 'rpt-06') {
    return {
      title: meta?.label ?? 'Оповещения',
      table: {
        headers: ['Время', 'Событие', 'Канал', 'Действие'],
        rows: [
          ['14:22', 'SLA очереди > 3 мин', 'Розница', 'email + дашборд'],
          ['11:05', 'p95 подсказки > 2 с', 'Все каналы', 'дашборд'],
          ['09:40', 'Рост тематики «Лимиты ATM» +18%', 'Онлайн-чат', 'автоуведомление'],
          ['08:15', 'Доля «неверно» > 8%', 'Телефония', 'email'],
        ],
      },
    }
  }

  if (reportId === 'rpt-09') {
    return {
      title: meta?.label ?? 'Ошибки',
      table: {
        headers: ['Причина', 'Канал', 'Кол-во', 'Пример'],
        rows: [
          ['Нет статьи в базе', 'Онлайн-чат', '18', 'лимит ATM ночью'],
          ['Неполный сценарий', 'Телефония', '11', 'блокировка карты'],
          ['Низкая релевантность', 'Онлайн-чат', '9', 'комиссия юрлицу'],
          ['Плохое распознавание', 'Телефония', '15', 'ЕРИП / ерип'],
        ],
      },
    }
  }

  return {
    title: meta?.label ?? 'Отчёт',
    table: {
      headers: ['Показатель', 'Телефония', 'Онлайн-чат', 'Итого'],
      rows: [
        ['Обращений', '1 240', '980', '2 220'],
        ['Средняя релевантность', '84%', '88%', '86%'],
        ['Полезность', '68%', '72%', '70%'],
        ['p95 подсказки', '1.45 с', '0.92 с', '1.38 с'],
        ['CSAT', '4.3', '4.5', '4.4'],
      ],
    },
  }
}

export const LIVE_DEMO = {
  kpis: [
    { label: 'В работе', value: '24', tone: 'info' as const },
    { label: 'В очереди', value: '7', tone: 'warning' as const },
    { label: 'Ср. ожидание', value: '1:42', tone: 'neutral' as const },
    { label: 'Операторов в сети', value: '18', tone: 'success' as const },
    { label: 'SLA', value: '91.5%', tone: 'success' as const },
    { label: 'p95 подсказки', value: '1.4 с', tone: 'info' as const },
  ],
  alerts: [
    { tone: 'warning' as const, title: 'SLA очереди > 3 мин', detail: 'Розница · 14:22 · email + дашборд' },
    { tone: 'warning' as const, title: 'p95 подсказки > 2 с', detail: 'Все каналы · 11:05 · дашборд супервизора' },
    { tone: 'info' as const, title: 'Рост тематики «Лимиты ATM» +18%', detail: 'автоуведомление 14:22' },
  ],
  departments: [
    { name: 'Розничные продукты', active: 12, queue: 4 },
    { name: 'Юрлица', active: 8, queue: 2 },
    { name: 'Ипотека', active: 4, queue: 1 },
  ],
  operators: [
    { name: 'Иванов И.И.', status: 'online', active: 5, channel: 'Онлайн-чат' },
    { name: 'Петрова М.С.', status: 'online', active: 4, channel: 'Онлайн-чат' },
    { name: 'Козлов Д.В.', status: 'break', active: 0, channel: 'Телефония' },
    { name: 'Сидорова А.П.', status: 'online', active: 3, channel: 'Телефония' },
    { name: 'Орлов Н.В.', status: 'offline', active: 0, channel: 'Онлайн-чат' },
    { name: 'Васильева Е.К.', status: 'online', active: 2, channel: 'Онлайн-чат' },
  ],
  feed: [
    { time: '14:28', channel: 'Онлайн-чат', operator: 'Иванов И.И.', topic: 'Карты и счета', relevance: '92%', feedback: 'воспользовался' },
    { time: '14:25', channel: 'Телефония', operator: 'Сидорова А.П.', topic: 'Кредиты', relevance: '74%', feedback: 'неполный' },
    { time: '14:22', channel: 'Онлайн-чат', operator: 'Петрова М.С.', topic: 'ЕРИП', relevance: '88%', feedback: 'воспользовался' },
    { time: '14:18', channel: 'Виджет сайта', operator: 'Васильева Е.К.', topic: 'Лимиты ATM', relevance: '69%', feedback: 'не воспользовался' },
    { time: '14:11', channel: 'Telegram', operator: 'Иванов И.И.', topic: 'Мобильный банк', relevance: '91%', feedback: 'воспользовался' },
  ],
}

export const ASR_DEMO_ITEMS = [
  {
    id: 1,
    session_id: 'TEL-260806-001',
    channel: 'telephony' as const,
    operator_name: 'Сидорова А.П.',
    started_at: '2026-08-06T09:12:00+03:00',
    duration_sec: 312,
    avg_confidence: 0.91,
    recognition_status: 'recognized' as const,
    has_training_candidate: false,
  },
  {
    id: 2,
    session_id: 'TEL-260806-014',
    channel: 'telephony' as const,
    operator_name: 'Козлов Д.В.',
    started_at: '2026-08-06T10:44:00+03:00',
    duration_sec: 248,
    avg_confidence: 0.62,
    recognition_status: 'partial' as const,
    has_training_candidate: true,
  },
  {
    id: 3,
    session_id: 'CHAT-260806-088',
    channel: 'online_chat' as const,
    operator_name: 'Иванов И.И.',
    started_at: '2026-08-06T11:05:00+03:00',
    duration_sec: 540,
    avg_confidence: 1,
    recognition_status: 'recognized' as const,
    has_training_candidate: false,
  },
  {
    id: 4,
    session_id: 'TEL-260805-203',
    channel: 'telephony' as const,
    operator_name: 'Орлов Н.В.',
    started_at: '2026-08-05T16:20:00+03:00',
    duration_sec: 190,
    avg_confidence: 0.41,
    recognition_status: 'unrecognized' as const,
    has_training_candidate: false,
  },
  {
    id: 5,
    session_id: 'CHAT-260805-441',
    channel: 'online_chat' as const,
    operator_name: 'Петрова М.С.',
    started_at: '2026-08-05T15:02:00+03:00',
    duration_sec: 420,
    avg_confidence: 1,
    recognition_status: 'recognized' as const,
    has_training_candidate: false,
  },
]

export const FILTER_FIELD_CATALOG = [
  { value: 'period', label: 'Период' },
  { value: 'channel', label: 'Канал' },
  { value: 'department', label: 'Отдел / скилл-группа' },
  { value: 'topic', label: 'Тематика закрытия' },
  { value: 'operator', label: 'Оператор' },
  { value: 'dialogue_status', label: 'Статус диалога' },
]

export const METRIC_FIELD_CATALOG = [
  { value: 'dialogs_total', label: 'Обращений всего' },
  { value: 'dialogs_closed', label: 'Закрытых диалогов' },
  { value: 'sla_pct', label: '% соблюдения SLA' },
  { value: 'aht', label: 'AHT' },
  { value: 'csat', label: 'Средняя оценка клиента' },
  { value: 'sufler_used_pct', label: '% использования суфлёра' },
  { value: 'repeat_rate', label: '% повторных обращений' },
]
