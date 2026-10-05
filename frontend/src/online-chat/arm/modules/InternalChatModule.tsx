import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  listInternalMessages,
  markInternalMessagesRead,
  operatorsApi,
  sendInternalMessage,
  type ChatOperator,
  type InternalMessage as ApiInternalMessage,
} from '../../api/managementApi'
import { onlineChatArmWsUrl } from '../../api/onlineChatApi'
import { Button, Pill, Row, Text, TextArea } from '../primitives'
import {
  ArmModuleFrame,
  ModuleEmpty,
  formatTime,
  presenceColor,
} from './ArmModuleFrame'
import type { ArmModuleProps, InternalContact, PresenceTone } from './types'

const PINS_KEY = 'arm-internal-chat-pins-v1'

type UiMessage = {
  id: string
  fromId: string
  text: string
  at: string
  mine: boolean
}

type UiThread = {
  contactId: string
  messages: UiMessage[]
  unread: number
  updatedAt: string
}

function mapApiPresence(presence: string): PresenceTone {
  if (presence === 'online') return 'online'
  if (presence === 'busy' || presence === 'meeting' || presence === 'training') return 'busy'
  if (presence === 'break' || presence === 'lunch' || presence === 'tech_issue') return 'away'
  return 'offline'
}

function presenceLabel(presence: PresenceTone): string {
  if (presence === 'online') return 'в сети'
  if (presence === 'busy') return 'занят'
  if (presence === 'away') return 'отошёл'
  return 'не в сети'
}

function loadPins(): string[] {
  try {
    const raw = localStorage.getItem(PINS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as string[]
    return Array.isArray(parsed) ? parsed.map(String) : []
  } catch {
    return []
  }
}

function toUiMessage(item: ApiInternalMessage, myId: string): UiMessage {
  const fromId = String(item.sender_id ?? '')
  return {
    id: String(item.id),
    fromId,
    text: item.text,
    at: item.created_at ?? new Date().toISOString(),
    mine: fromId === myId,
  }
}

function buildThreads(
  items: ApiInternalMessage[],
  myId: string,
): UiThread[] {
  const byPeer = new Map<string, UiThread>()
  for (const item of items) {
    const senderId = String(item.sender_id ?? '')
    const recipientId = String(item.recipient_id ?? '')
    const peerId = senderId === myId ? recipientId : senderId
    if (!peerId || peerId === myId) continue
    const ui = toUiMessage(item, myId)
    const existing = byPeer.get(peerId)
    const unreadInc = !item.read_at && recipientId === myId ? 1 : 0
    if (!existing) {
      byPeer.set(peerId, {
        contactId: peerId,
        messages: [ui],
        unread: unreadInc,
        updatedAt: ui.at,
      })
    } else {
      existing.messages.push(ui)
      existing.unread += unreadInc
      if (ui.at > existing.updatedAt) existing.updatedAt = ui.at
    }
  }
  return Array.from(byPeer.values()).sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1))
}

/**
 * Internal operator chat (FR-CHAT-16 / UC-O6) backed by InternalMessage DB + ARM WS.
 */
export function InternalChatModule({
  t,
  scheme,
  operatorName,
  onBack,
  onNavigate,
  onUnreadChange,
}: ArmModuleProps & { onUnreadChange?: (count: number) => void }) {
  const [meId, setMeId] = useState<string | null>(null)
  const [contacts, setContacts] = useState<InternalContact[]>([])
  const [threads, setThreads] = useState<UiThread[]>([])
  const [pinnedIds, setPinnedIds] = useState<string[]>(() => loadPins())
  const [activeId, setActiveId] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [draft, setDraft] = useState('')
  const [listTab, setListTab] = useState<'recent' | 'online' | 'all'>('recent')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const activeIdRef = useRef<string | null>(null)
  const meIdRef = useRef<string | null>(null)

  useEffect(() => {
    activeIdRef.current = activeId
  }, [activeId])
  useEffect(() => {
    meIdRef.current = meId
  }, [meId])

  useEffect(() => {
    try {
      localStorage.setItem(PINS_KEY, JSON.stringify(pinnedIds))
    } catch {
      /* ignore */
    }
  }, [pinnedIds])

  const refreshMessages = useCallback(async () => {
    if (!operatorName) return
    try {
      const body = await listInternalMessages({ operatorName })
      const operatorId = body.operator_id ? String(body.operator_id) : meIdRef.current
      if (operatorId) {
        setMeId(operatorId)
        meIdRef.current = operatorId
        const nextThreads = buildThreads(body.items ?? [], operatorId)
        setThreads(nextThreads)
        onUnreadChange?.(body.unread_count ?? 0)
      } else if ((body.items ?? []).length === 0) {
        setThreads([])
        onUnreadChange?.(0)
      }
      setError(null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Не удалось загрузить сообщения')
    }
  }, [operatorName, onUnreadChange])

  useEffect(() => {
    let cancelled = false
    void operatorsApi
      .list()
      .then((list) => {
        if (cancelled) return
        const me = list.find((item) => item.name === operatorName)
        if (me) {
          setMeId(String(me.id))
          meIdRef.current = String(me.id)
        }
        const mapped: InternalContact[] = list
          .filter((item) => item.is_active !== false && item.name !== operatorName)
          .map((item: ChatOperator) => ({
            id: String(item.id),
            name: item.name,
            department:
              item.department_name
              || (typeof item.department === 'object' && item.department
                ? item.department.name
                : 'Без отдела'),
            presence: mapApiPresence(item.presence),
            title: 'Оператор',
            activeDialogs: item.active_dialogs ?? 0,
          }))
        setContacts(mapped)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [operatorName])

  useEffect(() => {
    void refreshMessages()
    const timer = window.setInterval(() => {
      void refreshMessages()
    }, 2500)
    let socket: WebSocket | null = null
    try {
      socket = new WebSocket(onlineChatArmWsUrl())
      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as { type?: string }
          if (
            data.type === 'internal.message.created'
            || data.type === 'internal.messages.read'
          ) {
            void refreshMessages()
          }
        } catch {
          /* ignore */
        }
      }
    } catch {
      /* WS optional — polling covers delivery */
    }
    return () => {
      window.clearInterval(timer)
      socket?.close()
    }
  }, [refreshMessages])

  const contactById = useMemo(() => {
    const map = new Map(contacts.map((c) => [c.id, c]))
    for (const th of threads) {
      if (!map.has(th.contactId)) {
        map.set(th.contactId, {
          id: th.contactId,
          name: `Сотрудник ${th.contactId.slice(0, 6)}`,
          department: '—',
          presence: 'offline',
        })
      }
    }
    return map
  }, [contacts, threads])

  const filteredContacts = useMemo(() => {
    const q = query.trim().toLowerCase()
    let list = [...contacts]
    for (const th of threads) {
      if (!list.some((c) => c.id === th.contactId)) {
        const fallback = contactById.get(th.contactId)
        if (fallback) list.push(fallback)
      }
    }
    if (q) {
      list = list.filter(
        (c) =>
          c.name.toLowerCase().includes(q)
          || c.department.toLowerCase().includes(q),
      )
    }
    if (listTab === 'online') list = list.filter((c) => c.presence === 'online')
    if (listTab === 'recent') {
      const recentIds = new Set(threads.map((th) => th.contactId))
      const recent = list
        .filter((c) => recentIds.has(c.id))
        .sort((a, b) => {
          const ta = threads.find((th) => th.contactId === a.id)?.updatedAt ?? ''
          const tb = threads.find((th) => th.contactId === b.id)?.updatedAt ?? ''
          return ta < tb ? 1 : -1
        })
      const rest = list.filter((c) => !recentIds.has(c.id) && c.presence === 'online')
      list = [...recent, ...rest]
    }
    return list
  }, [contacts, query, listTab, threads, contactById])

  const pinnedContacts = useMemo(
    () => pinnedIds.map((id) => contactById.get(id)).filter(Boolean) as InternalContact[],
    [pinnedIds, contactById],
  )

  const activeContact = activeId ? contactById.get(activeId) ?? null : null
  const activeThread = threads.find((th) => th.contactId === activeId) ?? null

  const openOrCreate = async (contactId: string) => {
    setActiveId(contactId)
    if (operatorName) {
      try {
        const result = await markInternalMessagesRead({
          operator_name: operatorName,
          peer_id: contactId,
        })
        onUnreadChange?.(result.unread_count)
        setThreads((prev) =>
          prev.map((th) => (th.contactId === contactId ? { ...th, unread: 0 } : th)),
        )
      } catch {
        /* ignore mark-read errors */
      }
    }
  }

  const togglePin = (contactId: string) => {
    setPinnedIds((prev) =>
      prev.includes(contactId) ? prev.filter((id) => id !== contactId) : [contactId, ...prev],
    )
  }

  const sendMessage = async () => {
    const text = draft.trim()
    if (!text || !activeId || sending) return
    setSending(true)
    setError(null)
    try {
      const saved = await sendInternalMessage({
        text,
        sender_name: operatorName,
        recipient_id: activeId,
      })
      if (saved.sender_id) {
        setMeId(String(saved.sender_id))
        meIdRef.current = String(saved.sender_id)
      }
      setDraft('')
      await refreshMessages()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Не удалось отправить')
    } finally {
      setSending(false)
    }
  }

  const lastPreview = (contactId: string): string => {
    const th = threads.find((item) => item.contactId === contactId)
    const last = th?.messages[th.messages.length - 1]
    return last?.text ?? 'Начать переписку'
  }

  const unreadOf = (contactId: string) =>
    threads.find((item) => item.contactId === contactId)?.unread ?? 0

  return (
    <ArmModuleFrame
      t={t}
      scheme={scheme}
      title="Внутренний чат"
      onBack={onBack}
      bodyStyle={{ overflow: 'hidden', display: 'flex' }}
    >
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <aside
          style={{
            width: 300,
            flexShrink: 0,
            borderRight: `1px solid ${t.stroke.secondary}`,
            display: 'flex',
            flexDirection: 'column',
            background: t.bg.editor,
            minHeight: 0,
          }}
        >
          <div style={{ padding: 12, borderBottom: `1px solid ${t.stroke.tertiary}` }}>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Поиск коллег по ФИО или отделу"
              aria-label="Поиск коллег"
              style={{
                width: '100%',
                padding: '8px 10px',
                borderRadius: 8,
                border: `1px solid ${t.stroke.secondary}`,
                background: t.bg.elevated,
                color: t.text.primary,
                fontFamily: 'inherit',
                fontSize: 13,
              }}
            />
            <Row style={{ gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
              {(
                [
                  ['recent', 'Недавние'],
                  ['online', 'В сети'],
                  ['all', 'Все'],
                ] as const
              ).map(([id, label]) => (
                <Pill key={id} size="sm" active={listTab === id} onClick={() => setListTab(id)}>
                  {label}
                </Pill>
              ))}
            </Row>
            {error ? (
              <Text style={{ fontSize: 11, color: '#C62828', marginTop: 8 }}>{error}</Text>
            ) : null}
          </div>

          {pinnedContacts.length > 0 ? (
            <div style={{ padding: '10px 12px 4px' }}>
              <Text style={{ fontSize: 11, fontWeight: 700, color: t.text.tertiary, letterSpacing: '0.04em' }}>
                ЗАКРЕПЛЁННЫЕ
              </Text>
              <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 4 }}>
                {pinnedContacts.map((contact) => (
                  <ContactRow
                    key={`pin-${contact.id}`}
                    t={t}
                    scheme={scheme}
                    contact={contact}
                    preview={lastPreview(contact.id)}
                    unread={unreadOf(contact.id)}
                    active={activeId === contact.id}
                    pinned
                    onClick={() => void openOrCreate(contact.id)}
                  />
                ))}
              </div>
            </div>
          ) : null}

          <div style={{ padding: '10px 12px 4px', flexShrink: 0 }}>
            <Text style={{ fontSize: 11, fontWeight: 700, color: t.text.tertiary, letterSpacing: '0.04em' }}>
              {listTab === 'online' ? 'В СЕТИ' : listTab === 'all' ? 'СОТРУДНИКИ' : 'НЕДАВНИЕ И ДОСТУПНЫЕ'}
            </Text>
          </div>
          <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '0 8px 12px' }}>
            {filteredContacts.length === 0 ? (
              <Text style={{ fontSize: 12, color: t.text.secondary, padding: 8 }}>
                Нет сотрудников. Запустите симулятор или добавьте операторов.
              </Text>
            ) : (
              filteredContacts
                .filter((c) => !pinnedIds.includes(c.id) || listTab !== 'recent')
                .map((contact) => (
                  <ContactRow
                    key={contact.id}
                    t={t}
                    scheme={scheme}
                    contact={contact}
                    preview={lastPreview(contact.id)}
                    unread={unreadOf(contact.id)}
                    active={activeId === contact.id}
                    pinned={pinnedIds.includes(contact.id)}
                    onClick={() => void openOrCreate(contact.id)}
                  />
                ))
            )}
          </div>
        </aside>

        <section
          style={{
            flex: 1,
            minWidth: 0,
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
            background: t.bg.elevated,
          }}
        >
          {!activeContact ? (
            <ModuleEmpty
              t={t}
              title="Выберите коллегу"
              hint="Найдите сотрудника слева или откройте закреплённый контакт."
            />
          ) : (
            <>
              <div
                style={{
                  padding: '12px 16px',
                  borderBottom: `1px solid ${t.stroke.secondary}`,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  flexShrink: 0,
                }}
              >
                <PresenceDot presence={activeContact.presence} size={10} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <Text weight="semibold">{activeContact.name}</Text>
                  <Text style={{ fontSize: 12, color: t.text.secondary }}>
                    {presenceLabel(activeContact.presence)} · {activeContact.department}
                  </Text>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => togglePin(activeContact.id)}
                  title={pinnedIds.includes(activeContact.id) ? 'Открепить' : 'Закрепить'}
                >
                  {pinnedIds.includes(activeContact.id) ? '★ Закреплён' : '☆ Закрепить'}
                </Button>
              </div>

              <div
                style={{
                  flex: 1,
                  minHeight: 0,
                  overflowY: 'auto',
                  padding: '16px 18px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 10,
                  background:
                    t.kind === 'light'
                      ? 'linear-gradient(180deg, #F7FBF8 0%, #FFFFFF 40%)'
                      : t.bg.editor,
                }}
              >
                {(activeThread?.messages ?? []).length === 0 ? (
                  <Text style={{ fontSize: 13, color: t.text.secondary, textAlign: 'center', marginTop: 40 }}>
                    Напишите первое сообщение.
                  </Text>
                ) : (
                  (activeThread?.messages ?? []).map((msg) => (
                    <div
                      key={msg.id}
                      style={{
                        alignSelf: msg.mine ? 'flex-end' : 'flex-start',
                        maxWidth: '72%',
                      }}
                    >
                      <div
                        style={{
                          padding: '9px 12px',
                          borderRadius: msg.mine ? '12px 12px 4px 12px' : '12px 12px 12px 4px',
                          background: msg.mine ? scheme.accentControl : t.fill.secondary,
                          color: msg.mine ? t.text.onAccent : t.text.primary,
                          fontSize: 13,
                          lineHeight: 1.45,
                          border: msg.mine ? 'none' : `1px solid ${t.stroke.tertiary}`,
                        }}
                      >
                        {msg.text}
                      </div>
                      <Text
                        style={{
                          fontSize: 10,
                          color: t.text.tertiary,
                          marginTop: 3,
                          textAlign: msg.mine ? 'right' : 'left',
                        }}
                      >
                        {formatTime(msg.at)}
                      </Text>
                    </div>
                  ))
                )}
              </div>

              <div
                style={{
                  padding: 12,
                  borderTop: `1px solid ${t.stroke.secondary}`,
                  flexShrink: 0,
                  background: t.bg.elevated,
                }}
              >
                <TextArea
                  value={draft}
                  onChange={setDraft}
                  rows={2}
                  placeholder={`Сообщение для ${activeContact.name}…`}
                  style={{ minHeight: 56, resize: 'none' }}
                />
                <Row style={{ justifyContent: 'flex-end', marginTop: 8, gap: 8 }}>
                  <Button
                    variant="primary"
                    size="sm"
                    disabled={!draft.trim() || sending}
                    onClick={() => void sendMessage()}
                  >
                    {sending ? 'Отправка…' : 'Отправить'}
                  </Button>
                </Row>
              </div>
            </>
          )}
        </section>

        <aside
          style={{
            width: 240,
            flexShrink: 0,
            borderLeft: `1px solid ${t.stroke.secondary}`,
            padding: 14,
            background: t.fill.secondary,
            display: activeContact ? 'flex' : 'none',
            flexDirection: 'column',
            gap: 12,
            minHeight: 0,
            overflowY: 'auto',
          }}
        >
          {activeContact ? (
            <>
              <div>
                <Text weight="semibold" style={{ fontSize: 15 }}>{activeContact.name}</Text>
                <Text style={{ fontSize: 12, color: t.text.secondary, marginTop: 4 }}>
                  {activeContact.title ?? 'Оператор'} · {activeContact.department}
                </Text>
              </div>
              <Row style={{ gap: 8, alignItems: 'center' }}>
                <PresenceDot presence={activeContact.presence} />
                <Text style={{ fontSize: 12 }}>{presenceLabel(activeContact.presence)}</Text>
              </Row>
              <div
                style={{
                  padding: 10,
                  borderRadius: 8,
                  background: t.bg.elevated,
                  border: `1px solid ${t.stroke.tertiary}`,
                }}
              >
                <Text style={{ fontSize: 11, color: t.text.tertiary }}>Активных клиентских диалогов</Text>
                <Text weight="semibold" style={{ fontSize: 22, marginTop: 2 }}>
                  {activeContact.activeDialogs ?? 0}
                </Text>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => onNavigate?.('colleagues')}
              >
                Диалоги коллеги →
              </Button>
            </>
          ) : null}
        </aside>
      </div>
    </ArmModuleFrame>
  )
}

function PresenceDot({ presence, size = 8 }: { presence: PresenceTone; size?: number }) {
  return (
    <span
      aria-hidden
      style={{
        width: size,
        height: size,
        borderRadius: 999,
        background: presenceColor(presence),
        display: 'inline-block',
        flexShrink: 0,
        boxShadow: presence === 'online' ? `0 0 0 3px ${presenceColor(presence)}33` : undefined,
      }}
    />
  )
}

function ContactRow({
  t,
  scheme,
  contact,
  preview,
  unread,
  active,
  pinned,
  onClick,
}: {
  t: ArmModuleProps['t']
  scheme: ArmModuleProps['scheme']
  contact: InternalContact
  preview: string
  unread: number
  active: boolean
  pinned?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        width: '100%',
        display: 'flex',
        gap: 10,
        alignItems: 'flex-start',
        padding: '9px 10px',
        marginBottom: 2,
        borderRadius: 8,
        border: `1px solid ${active ? scheme.accent : 'transparent'}`,
        background: active ? t.fill.tertiary : 'transparent',
        cursor: 'pointer',
        textAlign: 'left',
        fontFamily: 'inherit',
        color: t.text.primary,
      }}
    >
      <PresenceDot presence={contact.presence} size={9} />
      <div style={{ minWidth: 0, flex: 1 }}>
        <Row style={{ justifyContent: 'space-between', gap: 6 }}>
          <Text weight="semibold" style={{ fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {pinned ? '★ ' : ''}
            {contact.name}
          </Text>
          {unread > 0 ? (
            <span
              style={{
                minWidth: 18,
                height: 18,
                padding: '0 5px',
                borderRadius: 999,
                background: scheme.badge,
                color: '#fff',
                fontSize: 10,
                fontWeight: 700,
                display: 'inline-grid',
                placeItems: 'center',
              }}
            >
              {unread}
            </span>
          ) : null}
        </Row>
        <Text
          style={{
            fontSize: 11,
            color: t.text.secondary,
            marginTop: 2,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {preview}
        </Text>
      </div>
    </button>
  )
}
