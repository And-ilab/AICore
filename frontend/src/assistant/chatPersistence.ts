import type { AssistantMessage } from './types'

const LEGACY_KEY = 'sufler.assistant.chat.v1'
const HISTORY_KEY = 'sufler.assistant.history.v2'
const MAX_DIALOGS = 40

export interface ChatDialogSummary {
  id: string
  title: string
  updatedAt: number
  createdAt: number
  preview: string
}

export interface ChatDialog extends ChatDialogSummary {
  messages: AssistantMessage[]
}

export interface ChatHistoryStore {
  version: 2
  activeId: string
  dialogs: ChatDialog[]
}

/** @deprecated legacy single-chat shape */
export interface PersistedAssistantChat {
  sessionId: string
  messages: AssistantMessage[]
  updatedAt: number
}

function sanitizeMessages(messages: AssistantMessage[]): AssistantMessage[] {
  return messages.map((item) => ({
    ...item,
    pending: false,
  }))
}

export function formatDialogDate(ts: number): string {
  try {
    return new Intl.DateTimeFormat('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(ts))
  } catch {
    return new Date(ts).toLocaleString('ru-RU')
  }
}

/** Cheap local title: first words of the first user question, else date. */
export function titleFromMessages(
  messages: readonly AssistantMessage[],
  fallbackAt: number = Date.now(),
): string {
  const firstUser = messages.find(
    (item) => item.role === 'user' && item.content.trim(),
  )
  if (!firstUser) {
    return messages.length ? formatDialogDate(fallbackAt) : 'Новый диалог'
  }

  const normalized = firstUser.content.trim().replace(/\s+/g, ' ')
  const words = normalized.split(' ').filter(Boolean)
  const take = words.slice(0, 7).join(' ')
  if (take.length >= normalized.length) return take
  return `${take}…`
}

function previewFromMessages(messages: readonly AssistantMessage[]): string {
  const last = [...messages]
    .reverse()
    .find((item) => item.content.trim())
  if (!last) return 'Пустой диалог'
  const text = last.content.trim().replace(/\s+/g, ' ')
  return text.length > 72 ? `${text.slice(0, 72)}…` : text
}

function emptyStore(activeId?: string): ChatHistoryStore {
  const id = activeId || `sess-${Date.now()}`
  const now = Date.now()
  return {
    version: 2,
    activeId: id,
    dialogs: [
      {
        id,
        title: 'Новый диалог',
        createdAt: now,
        updatedAt: now,
        preview: 'Пустой диалог',
        messages: [],
      },
    ],
  }
}

function readLegacy(): ChatHistoryStore | null {
  try {
    const raw = sessionStorage.getItem(LEGACY_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as PersistedAssistantChat
    if (!parsed?.sessionId || !Array.isArray(parsed.messages)) return null
    const updatedAt = parsed.updatedAt || Date.now()
    return {
      version: 2,
      activeId: parsed.sessionId,
      dialogs: [
        {
          id: parsed.sessionId,
          title: titleFromMessages(parsed.messages, updatedAt),
          createdAt: updatedAt,
          updatedAt,
          preview: previewFromMessages(parsed.messages),
          messages: sanitizeMessages(parsed.messages),
        },
      ],
    }
  } catch {
    return null
  }
}

function readStore(): ChatHistoryStore | null {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    if (!raw) return readLegacy()
    const parsed = JSON.parse(raw) as ChatHistoryStore
    if (
      !parsed
      || parsed.version !== 2
      || !parsed.activeId
      || !Array.isArray(parsed.dialogs)
    ) {
      return readLegacy()
    }
    return parsed
  } catch {
    return readLegacy()
  }
}

function writeStore(store: ChatHistoryStore): void {
  try {
    const trimmed: ChatHistoryStore = {
      ...store,
      dialogs: store.dialogs
        .slice()
        .sort((a, b) => b.updatedAt - a.updatedAt)
        .slice(0, MAX_DIALOGS),
    }
    if (!trimmed.dialogs.some((item) => item.id === trimmed.activeId)) {
      trimmed.activeId = trimmed.dialogs[0]?.id || emptyStore().activeId
    }
    localStorage.setItem(HISTORY_KEY, JSON.stringify(trimmed))
    sessionStorage.removeItem(LEGACY_KEY)
  } catch {
    /* ignore quota / private mode */
  }
}

export function loadChatHistory(): ChatHistoryStore {
  return readStore() || emptyStore()
}

export function loadPersistedChat(): PersistedAssistantChat | null {
  const store = loadChatHistory()
  const active =
    store.dialogs.find((item) => item.id === store.activeId) || store.dialogs[0]
  if (!active) return null
  return {
    sessionId: active.id,
    messages: active.messages,
    updatedAt: active.updatedAt,
  }
}

export function listDialogSummaries(
  store: ChatHistoryStore = loadChatHistory(),
): ChatDialogSummary[] {
  return store.dialogs
    .slice()
    .sort((a, b) => b.updatedAt - a.updatedAt)
    .map(({ id, title, updatedAt, createdAt, preview }) => ({
      id,
      title,
      updatedAt,
      createdAt,
      preview,
    }))
}

export function savePersistedChat(
  sessionId: string,
  messages: AssistantMessage[],
): void {
  const store = loadChatHistory()
  const now = Date.now()
  const cleaned = sanitizeMessages(messages)
  const existing = store.dialogs.find((item) => item.id === sessionId)
  const nextDialog: ChatDialog = {
    id: sessionId,
    title: titleFromMessages(cleaned, existing?.createdAt || now),
    createdAt: existing?.createdAt || now,
    updatedAt: now,
    preview: previewFromMessages(cleaned),
    messages: cleaned,
  }
  const others = store.dialogs.filter((item) => item.id !== sessionId)
  writeStore({
    version: 2,
    activeId: sessionId,
    dialogs: [nextDialog, ...others],
  })
}

export function clearPersistedChat(): void {
  try {
    localStorage.removeItem(HISTORY_KEY)
    sessionStorage.removeItem(LEGACY_KEY)
  } catch {
    /* ignore */
  }
}

export function createDialogInHistory(
  messages: AssistantMessage[] = [],
): ChatDialog {
  const store = loadChatHistory()
  const now = Date.now()
  const id = `sess-${now}-${Math.random().toString(36).slice(2, 7)}`
  const dialog: ChatDialog = {
    id,
    title: titleFromMessages(messages, now),
    createdAt: now,
    updatedAt: now,
    preview: previewFromMessages(messages),
    messages: sanitizeMessages(messages),
  }
  writeStore({
    version: 2,
    activeId: id,
    dialogs: [dialog, ...store.dialogs],
  })
  return dialog
}

export function openDialogInHistory(dialogId: string): ChatDialog | null {
  const store = loadChatHistory()
  const dialog = store.dialogs.find((item) => item.id === dialogId)
  if (!dialog) return null
  writeStore({ ...store, activeId: dialogId })
  return dialog
}

export function deleteDialogFromHistory(dialogId: string): ChatHistoryStore {
  const store = loadChatHistory()
  const dialogs = store.dialogs.filter((item) => item.id !== dialogId)
  if (!dialogs.length) {
    const fresh = emptyStore()
    writeStore(fresh)
    return fresh
  }
  const activeId =
    store.activeId === dialogId ? dialogs[0].id : store.activeId
  const next = { version: 2 as const, activeId, dialogs }
  writeStore(next)
  return next
}
