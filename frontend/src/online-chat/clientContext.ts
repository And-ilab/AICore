/** Demo client context from online-chat canvas ARM. */

export const CLOSE_TOPICS = [
  'Карты и счета',
  'Платежи и переводы',
  'Мобильный банк',
  'Кредиты',
  'Ипотека',
  'Вклады',
  'Юрлица',
  'Блокировка / безопасность',
  'Техническая поддержка',
  'Прочее',
] as const

export type ClientInfoData = {
  name: string
  phoneMasked: string
  phoneFull: string
  dialogNo: string
  visitorId: string
  visitTime: string
  entryPath: string
  entryChannel: string
  browser: string
  device: string
  email: string
  channel: string
}

export const ACTIVE_CLIENT: ClientInfoData = {
  name: 'Анна Козлова',
  phoneMasked: '+375 ** ***-**-45',
  phoneFull: '+375 29 123-45-45',
  dialogNo: '№ 18 944',
  visitorId: 'vis-7f3a2b1c',
  visitTime: '09.07.2026, 08:42',
  entryPath: '/fizicheskim_licam/cards/',
  entryChannel: 'Виджет сайта',
  browser: 'Chrome 125',
  device: 'Windows 11',
  email: 'anna.k@example.com',
  channel: 'Сайт',
}

export type SummaryHistoryData = {
  summary: string
  detailedSummary: string
  preview: string
}

export const ACTIVE_SUMMARY_HISTORY: SummaryHistoryData = {
  summary:
    'Клиент обращался 12.05 (чат, лимит ATM) и 03.04 (Telegram). Текущая тема повторяется — лимиты.',
  detailedSummary:
    'За 90 дней — 3 обращения по теме лимитов и переводов.\n\n12.05.2026 · онлайн-чат · лимит ATM — оператор Сидорова М.В. Разъяснены суточные лимиты карты Visa, клиент подтвердил понимание.\n\n03.04.2026 · Telegram · лимиты переводов — оператор Козлов Д.А. Проверены настройки лимита в мобильном банке.\n\n15.03.2026 · телефония (Oktell) · перевод в РФ — оператор Петрова А.С., длит. 4:12. Рекомендован раздел «Платежи → За рубеж».\n\nПовторная тема: лимиты. Рекомендация: проверить актуальный лимит в мобильном банке перед ответом.',
  preview:
    'Клиент обращался 12.05 (чат, лимит ATM) и 03.04 (Telegram). Текущая тема повторяется — лимиты.',
}
