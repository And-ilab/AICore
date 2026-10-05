import type {
  AppealHistoryItem,
  InternalContact,
  InternalThread,
  ReplyTemplateItem,
} from './types'

export const DEMO_CONTACTS: InternalContact[] = [
  {
    id: 'op-petrova',
    name: 'Петрова А.С.',
    department: 'Розничные продукты',
    presence: 'online',
    title: 'Оператор',
    activeDialogs: 2,
  },
  {
    id: 'op-sidorov',
    name: 'Сидоров М.В.',
    department: 'Ипотека',
    presence: 'busy',
    title: 'Оператор',
    activeDialogs: 3,
  },
  {
    id: 'op-kozlov',
    name: 'Козлов Д.А.',
    department: 'Карты',
    presence: 'away',
    title: 'Оператор',
    activeDialogs: 0,
  },
  {
    id: 'op-morozova',
    name: 'Морозова Е.И.',
    department: 'Розничные продукты',
    presence: 'online',
    title: 'Супервизор',
    activeDialogs: 1,
  },
  {
    id: 'op-vasiliev',
    name: 'Васильев Н.П.',
    department: 'Юрлица',
    presence: 'offline',
    title: 'Оператор',
    activeDialogs: 0,
  },
  {
    id: 'op-novik',
    name: 'Новик Т.В.',
    department: 'Мобильный банк',
    presence: 'online',
    title: 'Оператор',
    activeDialogs: 1,
  },
]

export const DEMO_INTERNAL_THREADS: InternalThread[] = [
  {
    contactId: 'op-petrova',
    pinned: true,
    unread: 1,
    updatedAt: new Date(Date.now() - 4 * 60_000).toISOString(),
    messages: [
      {
        id: 'm1',
        fromId: 'op-petrova',
        text: 'Можешь глянуть перевод по карте *4521? Клиент ждёт подтверждение банка.',
        at: new Date(Date.now() - 18 * 60_000).toISOString(),
        mine: false,
      },
      {
        id: 'm2',
        fromId: 'me',
        text: 'Смотрю. Похоже, зависло на антифроде — сейчас уточню у супервизора.',
        at: new Date(Date.now() - 12 * 60_000).toISOString(),
        mine: true,
      },
      {
        id: 'm3',
        fromId: 'op-petrova',
        text: 'Ок, спасибо. Держу клиента на линии.',
        at: new Date(Date.now() - 4 * 60_000).toISOString(),
        mine: false,
      },
    ],
  },
  {
    contactId: 'op-morozova',
    pinned: true,
    unread: 0,
    updatedAt: new Date(Date.now() - 55 * 60_000).toISOString(),
    messages: [
      {
        id: 'm4',
        fromId: 'me',
        text: 'Елена, могу перевести диалог по ипотеке на Сидорова? У меня лимит.',
        at: new Date(Date.now() - 70 * 60_000).toISOString(),
        mine: true,
      },
      {
        id: 'm5',
        fromId: 'op-morozova',
        text: 'Да, переводи в отдел «Ипотека», он online.',
        at: new Date(Date.now() - 55 * 60_000).toISOString(),
        mine: false,
      },
    ],
  },
  {
    contactId: 'op-sidorov',
    pinned: false,
    unread: 0,
    updatedAt: new Date(Date.now() - 3 * 3600_000).toISOString(),
    messages: [
      {
        id: 'm6',
        fromId: 'me',
        text: 'Какая актуальная ставка по «Моя квартира» для зарплатников?',
        at: new Date(Date.now() - 3.2 * 3600_000).toISOString(),
        mine: true,
      },
      {
        id: 'm7',
        fromId: 'op-sidorov',
        text: 'От 11,9% при страховке. Детали в шаблоне «Ипотека — ставка».',
        at: new Date(Date.now() - 3 * 3600_000).toISOString(),
        mine: false,
      },
    ],
  },
]

export const DEMO_APPEALS: AppealHistoryItem[] = [
  {
    id: 'a-10021',
    clientName: 'Анна Козлова',
    phoneMasked: '+375 ** *** ** 21',
    channel: 'Сайт',
    topic: 'Карты и счета',
    status: 'closed',
    operatorName: 'Иванов И.И.',
    openedAt: new Date(Date.now() - 2 * 3600_000).toISOString(),
    closedAt: new Date(Date.now() - 1.5 * 3600_000).toISOString(),
    summary: 'Клиент уточнил лимит снятия наличных. Лимит озвучен, дополнительные вопросы не задавал.',
  },
  {
    id: 'a-10018',
    clientName: 'Анна Козлова',
    phoneMasked: '+375 ** *** ** 21',
    channel: 'Телефония',
    topic: 'Блокировка / безопасность',
    status: 'closed',
    operatorName: 'Петрова А.С.',
    openedAt: new Date(Date.now() - 5 * 86400_000).toISOString(),
    closedAt: new Date(Date.now() - 5 * 86400_000 + 900_000).toISOString(),
    summary: 'Временная блокировка карты по подозрению на мошенничество. Карта разблокирована после сверки.',
  },
  {
    id: 'a-10044',
    clientName: 'Дмитрий В.',
    phoneMasked: '+375 ** *** ** 08',
    channel: 'Viber',
    topic: 'Ипотека',
    status: 'active',
    operatorName: 'Сидоров М.В.',
    openedAt: new Date(Date.now() - 20 * 60_000).toISOString(),
    summary: 'Уточнение ставки по программе «Моя квартира». Диалог в работе.',
  },
  {
    id: 'a-10039',
    clientName: 'Марина Т.',
    phoneMasked: '+375 ** *** ** 55',
    channel: 'Telegram',
    topic: 'Мобильный банк',
    status: 'lost',
    operatorName: 'Козлов Д.А.',
    openedAt: new Date(Date.now() - 6 * 3600_000).toISOString(),
    closedAt: new Date(Date.now() - 5.5 * 3600_000).toISOString(),
    summary: 'Клиент отключился до ответа. Статус: потерянный.',
  },
  {
    id: 'a-10031',
    clientName: 'ООО «Север»',
    phoneMasked: '+375 ** *** ** 77',
    channel: 'Сайт',
    topic: 'Юрлица',
    status: 'offline',
    operatorName: 'Васильев Н.П.',
    openedAt: new Date(Date.now() - 26 * 3600_000).toISOString(),
    summary: 'Офлайн-вопрос по р/с. Ожидает ответа оператора.',
  },
]

export const DEFAULT_TEMPLATES: ReplyTemplateItem[] = [
  {
    id: 'tpl-hello',
    title: 'Приветствие',
    category: 'Общие',
    body: 'Здравствуйте, {{client_name}}! Меня зовут {{operator_name}}. Чем могу помочь?',
    updatedAt: new Date().toISOString(),
    favorite: true,
    scope: 'shared',
  },
  {
    id: 'tpl-wait',
    title: 'Проверяю информацию',
    category: 'Общие',
    body: 'Проверяю информацию, одну минуту. Оставайтесь, пожалуйста, на связи.',
    updatedAt: new Date().toISOString(),
    favorite: true,
    scope: 'shared',
  },
  {
    id: 'tpl-card4',
    title: 'Запрос 4 цифр карты',
    category: 'Карты',
    body: 'Подскажите, пожалуйста, последние 4 цифры карты для идентификации.',
    updatedAt: new Date().toISOString(),
    scope: 'shared',
  },
  {
    id: 'tpl-mortgage',
    title: 'Ипотека — ставка',
    category: 'Ипотека',
    body: 'По программе «Моя квартира» актуальная ставка для зарплатных клиентов — от 11,9% годовых при оформлении страховки. Могу рассчитать ориентировочный платёж.',
    updatedAt: new Date().toISOString(),
    scope: 'shared',
  },
  {
    id: 'tpl-bye',
    title: 'Завершение',
    category: 'Общие',
    body: 'Спасибо за обращение! Если появятся вопросы — пишите в чат. Хорошего дня!',
    updatedAt: new Date().toISOString(),
    favorite: true,
    scope: 'shared',
  },
]

export const COLLEAGUE_DIALOG_DEMO: Record<
  string,
  { client: string; channel: string; preview: string; wait: string; urgent: boolean }[]
> = {
  'Петрова А.С.': [
    { client: 'Анна Козлова', channel: 'Сайт', preview: 'Лимит снятия наличных?', wait: '02:14', urgent: true },
    { client: 'Марина Т.', channel: 'Telegram', preview: 'SMS-информирование', wait: '03:55', urgent: false },
  ],
  'Сидоров М.В.': [
    { client: 'Дмитрий В.', channel: 'Viber', preview: 'Ставка по ипотеке', wait: '01:08', urgent: false },
  ],
  'Козлов Д.А.': [
    { client: 'Игорь Н.', channel: 'Сайт', preview: 'Блокировка карты', wait: '00:42', urgent: true },
  ],
  'Морозова Е.И.': [
    { client: 'Ольга С.', channel: 'Сайт', preview: 'Перевод на карту', wait: '01:30', urgent: false },
  ],
  'Васильев Н.П.': [],
  'Новик Т.В.': [
    { client: 'Павел К.', channel: 'Мобильный банк', preview: 'Не приходит push', wait: '04:10', urgent: false },
  ],
}
