import type { ChatMessage } from './hooks/useChatSufler'
import type { SuflerHint } from '../sufler/api/suggest'

export type QueueSectionId =
  | 'waiting'
  | 'mine'
  | 'offline'
  | 'lost'
  | 'shared'
  | 'colleagues'

export type ChatChannel =
  | 'Сайт'
  | 'Telegram'
  | 'Viber'
  | 'VK'
  | 'Одноклассники'

export interface QueueItem {
  id: string
  name: string
  channel: ChatChannel | string
  dept?: string
  preview: string
  wait: string
  urgent?: boolean
  active?: boolean
  result?: 'offline' | 'lost' | 'declined'
  operatorName?: string
  readOnly?: boolean
  sessionId: string
}

export interface QueueSection {
  id: QueueSectionId
  title: string
  defaultExpanded: boolean
  items: QueueItem[]
}

export interface ChatSession {
  id: string
  queueItemId: string
  clientName: string
  channel: string
  dialogNo: string
  messages: ChatMessage[]
  readOnly?: boolean
}

const LIMIT_HINTS: SuflerHint[] = [
  {
    rank: 1,
    text:
      'Суточный лимит снятия в банкоматах Беларусбанка для дебетовых карт составляет 2 000 BYN. Лимит обнуляется в 00:00 по минскому времени.',
    relevance_score: 0.94,
    relevance_percent: 94,
    citations: [
      {
        article_id: 201,
        chunk_index: 0,
        title: 'Лимиты снятия наличных',
        permalink: 'https://suz.local/articles/201',
      },
    ],
  },
  {
    rank: 2,
    text:
      'Комиссия за снятие наличных в банкоматах других банков составляет от 1,5% от суммы, минимум 3 BYN. В банкоматах Беларусбанка для карт банка комиссия не взимается.',
    relevance_score: 0.81,
    relevance_percent: 81,
    citations: [
      {
        article_id: 202,
        chunk_index: 0,
        title: 'Комиссии банкоматов',
        permalink: 'https://suz.local/articles/202',
      },
    ],
  },
]

export const DEFAULT_QUEUE_SECTIONS: QueueSection[] = [
  {
    id: 'waiting',
    title: 'Ожидают ответа',
    defaultExpanded: true,
    items: [
      {
        id: '1',
        sessionId: 'sess-1',
        name: 'Анна Козлова',
        channel: 'Сайт',
        dept: 'Розничные продукты',
        preview: 'Подскажите лимит снятия наличных в банкомате?',
        wait: '02:14',
        urgent: true,
        active: true,
      },
      {
        id: '2',
        sessionId: 'sess-2',
        name: 'Пётр Мельников',
        channel: 'Telegram',
        dept: 'Розничные продукты',
        preview: 'Не приходит SMS для подтверждения операции',
        wait: '00:45',
      },
      {
        id: '3',
        sessionId: 'sess-3',
        name: 'ООО «Вектор»',
        channel: 'Сайт',
        dept: 'Юрлица',
        preview: 'Тарифы на РКО для ИП',
        wait: '00:12',
      },
    ],
  },
  {
    id: 'mine',
    title: 'В диалоге со мной',
    defaultExpanded: true,
    items: [
      {
        id: 'm1',
        sessionId: 'sess-m1',
        name: 'Светлана Р.',
        channel: 'Viber',
        dept: 'Розничные продукты',
        preview: 'Когда будет готов перевод SWIFT?',
        wait: '04:32',
        active: true,
      },
      {
        id: 'm2',
        sessionId: 'sess-m2',
        name: 'Дмитрий В.',
        channel: 'Сайт',
        dept: 'Ипотека',
        preview: 'Уточните ставку по ипотеке «Моя квартира»',
        wait: '01:08',
      },
    ],
  },
  {
    id: 'colleagues',
    title: 'Диалоги коллег',
    defaultExpanded: false,
    items: [
      {
        id: 'c1',
        sessionId: 'sess-c1',
        name: 'Анна Козлова',
        channel: 'Сайт',
        dept: 'Розничные продукты',
        preview: 'Подскажите лимит снятия наличных в банкомате?',
        wait: '02:14',
        urgent: true,
        operatorName: 'Петрова А.С.',
        readOnly: true,
      },
      {
        id: 'c2',
        sessionId: 'sess-c2',
        name: 'Дмитрий В.',
        channel: 'Viber',
        dept: 'Ипотека',
        preview: 'Уточните ставку по ипотеке «Моя квартира»',
        wait: '01:08',
        operatorName: 'Сидоров М.В.',
        readOnly: true,
      },
      {
        id: 'c3',
        sessionId: 'sess-c3',
        name: 'Марина Т.',
        channel: 'Telegram',
        dept: 'Розничные продукты',
        preview: 'Как подключить SMS-информирование?',
        wait: '03:55',
        operatorName: 'Петрова А.С.',
        readOnly: true,
      },
    ],
  },
  {
    id: 'offline',
    title: 'Офлайн',
    defaultExpanded: false,
    items: [
      {
        id: 'o1',
        sessionId: 'sess-o1',
        name: 'Пётр Мельников',
        channel: 'Telegram',
        preview: 'Не приходит SMS для подтверждения операции',
        wait: '—',
        result: 'offline',
      },
    ],
  },
  {
    id: 'lost',
    title: 'Потерянные',
    defaultExpanded: false,
    items: [
      {
        id: 'l1',
        sessionId: 'sess-l1',
        name: 'ООО «Вектор»',
        channel: 'Сайт',
        preview: 'Тарифы на РКО для ИП',
        wait: '—',
        result: 'lost',
      },
    ],
  },
  {
    id: 'shared',
    title: 'Общая очередь',
    defaultExpanded: false,
    items: [
      {
        id: 's1',
        sessionId: 'sess-s1',
        name: 'Марина Т.',
        channel: 'Сайт',
        preview: 'Как подключить SMS-информирование?',
        wait: '03:55',
        urgent: true,
      },
      {
        id: 's2',
        sessionId: 'sess-s2',
        name: 'ИП Ковалёв',
        channel: 'Telegram',
        preview: 'Запрос выписки по расчётному счёту',
        wait: '02:40',
      },
    ],
  },
]

export const DEFAULT_SESSIONS: Record<string, ChatSession> = {
  'sess-1': {
    id: 'sess-1',
    queueItemId: '1',
    clientName: 'Анна Козлова',
    channel: 'Сайт',
    dialogNo: '№ 18 944',
    messages: [
      {
        id: 't1-client',
        speaker: 'client',
        text: 'Подскажите лимит снятия наличных в банкомате?',
        turnId: 't1',
        hints: LIMIT_HINTS,
      },
      {
        id: 't1-operator',
        speaker: 'operator',
        text: 'Проверяю лимиты по вашей карте, одну минуту.',
        turnId: 't1-op',
      },
    ],
  },
  'sess-2': {
    id: 'sess-2',
    queueItemId: '2',
    clientName: 'Пётр Мельников',
    channel: 'Telegram',
    dialogNo: '№ 18 951',
    messages: [
      {
        id: 't2-client',
        speaker: 'client',
        text: 'Не приходит SMS для подтверждения операции',
        turnId: 't2',
      },
    ],
  },
  'sess-3': {
    id: 'sess-3',
    queueItemId: '3',
    clientName: 'ООО «Вектор»',
    channel: 'Сайт',
    dialogNo: '№ 18 960',
    messages: [
      {
        id: 't3-client',
        speaker: 'client',
        text: 'Тарифы на РКО для ИП',
        turnId: 't3',
      },
    ],
  },
  'sess-m1': {
    id: 'sess-m1',
    queueItemId: 'm1',
    clientName: 'Светлана Р.',
    channel: 'Viber',
    dialogNo: '№ 18 900',
    messages: [
      {
        id: 'tm1-client',
        speaker: 'client',
        text: 'Когда будет готов перевод SWIFT?',
        turnId: 'tm1',
      },
      {
        id: 'tm1-operator',
        speaker: 'operator',
        text: 'Проверяю статус перевода, минуту.',
        turnId: 'tm1-op',
      },
    ],
  },
  'sess-m2': {
    id: 'sess-m2',
    queueItemId: 'm2',
    clientName: 'Дмитрий В.',
    channel: 'Сайт',
    dialogNo: '№ 18 901',
    messages: [
      {
        id: 'tm2-client',
        speaker: 'client',
        text: 'Уточните ставку по ипотеке «Моя квартира»',
        turnId: 'tm2',
      },
    ],
  },
  'sess-o1': {
    id: 'sess-o1',
    queueItemId: 'o1',
    clientName: 'Пётр Мельников',
    channel: 'Telegram',
    dialogNo: '№ 18 880',
    messages: [
      {
        id: 'to1-client',
        speaker: 'client',
        text: 'Не приходит SMS для подтверждения операции',
        turnId: 'to1',
      },
    ],
  },
  'sess-l1': {
    id: 'sess-l1',
    queueItemId: 'l1',
    clientName: 'ООО «Вектор»',
    channel: 'Сайт',
    dialogNo: '№ 18 870',
    messages: [
      {
        id: 'tl1-client',
        speaker: 'client',
        text: 'Тарифы на РКО для ИП',
        turnId: 'tl1',
      },
    ],
  },
  'sess-s1': {
    id: 'sess-s1',
    queueItemId: 's1',
    clientName: 'Марина Т.',
    channel: 'Сайт',
    dialogNo: '№ 18 990',
    messages: [
      {
        id: 'ts1-client',
        speaker: 'client',
        text: 'Как подключить SMS-информирование?',
        turnId: 'ts1',
      },
    ],
  },
  'sess-s2': {
    id: 'sess-s2',
    queueItemId: 's2',
    clientName: 'ИП Ковалёв',
    channel: 'Telegram',
    dialogNo: '№ 18 991',
    messages: [
      {
        id: 'ts2-client',
        speaker: 'client',
        text: 'Запрос выписки по расчётному счёту',
        turnId: 'ts2',
      },
    ],
  },
  'sess-c1': {
    id: 'sess-c1',
    queueItemId: 'c1',
    clientName: 'Анна Козлова',
    channel: 'Сайт',
    dialogNo: '№ 18 944',
    readOnly: true,
    messages: [
      {
        id: 'tc1-client',
        speaker: 'client',
        text: 'Подскажите лимит снятия наличных в банкомате?',
        turnId: 'tc1',
        hints: LIMIT_HINTS,
      },
      {
        id: 'tc1-operator',
        speaker: 'operator',
        text: 'Проверяю лимиты по вашей карте, одну минуту.',
        turnId: 'tc1-op',
      },
    ],
  },
  'sess-c2': {
    id: 'sess-c2',
    queueItemId: 'c2',
    clientName: 'Дмитрий В.',
    channel: 'Viber',
    dialogNo: '№ 18 902',
    readOnly: true,
    messages: [
      {
        id: 'tc2-client',
        speaker: 'client',
        text: 'Уточните ставку по ипотеке «Моя квартира»',
        turnId: 'tc2',
      },
    ],
  },
  'sess-c3': {
    id: 'sess-c3',
    queueItemId: 'c3',
    clientName: 'Марина Т.',
    channel: 'Telegram',
    dialogNo: '№ 18 903',
    readOnly: true,
    messages: [
      {
        id: 'tc3-client',
        speaker: 'client',
        text: 'Как подключить SMS-информирование?',
        turnId: 'tc3',
      },
    ],
  },
}

export function flattenQueueItems(sections: QueueSection[]): QueueItem[] {
  return sections.flatMap((section) => section.items)
}

export function findQueueItem(
  sections: QueueSection[],
  queueItemId: string,
): QueueItem | undefined {
  return flattenQueueItems(sections).find((item) => item.id === queueItemId)
}

export function queueItemCount(sections: QueueSection[]): number {
  return flattenQueueItems(sections).length
}
