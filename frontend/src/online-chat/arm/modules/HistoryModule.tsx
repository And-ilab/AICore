import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import {
  dialogRefCode,
  getDialog,
  listDialogs,
  maskPhone,
  type OnlineChatDialog,
  type OnlineChatMessage,
} from '../../api/onlineChatApi'
import { Pill, Row, Text } from '../primitives'
import { TopicChip } from '../summaryTopics'
import type { ArmTheme } from '../theme'
import { ArmModuleFrame, formatDateTime, formatTime, ModuleEmpty } from './ArmModuleFrame'
import { DEMO_APPEALS } from './demoData'
import type { AppealHistoryItem, ArmModuleProps, ModuleSchemePalette } from './types'

const STATUS_LABEL: Record<AppealHistoryItem['status'], string> = {
  closed: 'Закрыт',
  active: 'В работе',
  lost: 'Потерянный',
  offline: 'Офлайн',
}

const STATUS_TONE: Record<AppealHistoryItem['status'], 'success' | 'info' | 'warning' | 'neutral'> = {
  closed: 'success',
  active: 'info',
  lost: 'warning',
  offline: 'neutral',
}

const CHANNEL_FALLBACK = ['Сайт', 'Telegram', 'Viber', 'Телефония', 'Мобильный банк']

type FeedbackFilter = 'all' | 'with' | 'without'
const HISTORY_LEFT_WIDTH_MIN = 240
const HISTORY_LEFT_WIDTH_MAX = 520
const HISTORY_RIGHT_WIDTH_MIN = 220
const HISTORY_RIGHT_WIDTH_MAX = 460

function clampWidth(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, Math.round(value)))
}

function startColumnResize(
  event: { clientX: number; preventDefault: () => void },
  initialWidth: number,
  setWidth: (next: number) => void,
  min: number,
  max: number,
  invert = false,
): void {
  event.preventDefault()
  const startX = event.clientX
  const handleMove = (moveEvent: MouseEvent) => {
    const delta = moveEvent.clientX - startX
    setWidth(clampWidth(invert ? initialWidth - delta : initialWidth + delta, min, max))
  }
  const handleUp = () => {
    window.removeEventListener('mousemove', handleMove)
    window.removeEventListener('mouseup', handleUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('mousemove', handleMove)
  window.addEventListener('mouseup', handleUp)
}

function mapDialogStatus(dialog: OnlineChatDialog): AppealHistoryItem['status'] {
  if (dialog.status === 'active' || dialog.status === 'waiting') return 'active'
  if (dialog.outcome === 'lost') return 'lost'
  if (dialog.outcome === 'offline') return 'offline'
  if (dialog.status === 'closed' || dialog.status === 'blocked') return 'closed'
  return 'closed'
}

function dialogToAppeal(dialog: OnlineChatDialog): AppealHistoryItem {
  return {
    id: dialog.id,
    clientName: dialog.client_name || 'Клиент',
    phoneMasked: maskPhone(dialog.client_phone || ''),
    channel: dialog.channel || 'Сайт',
    topic: dialog.close_topic || dialog.preview || 'Без темы',
    status: mapDialogStatus(dialog),
    operatorName: dialog.operator_name || '—',
    clientIp: dialog.client_ip || '',
    feedbackRating: typeof dialog.feedback_rating === 'number' ? dialog.feedback_rating : null,
    openedAt: dialog.created_at,
    closedAt: dialog.closed_at ?? undefined,
    summary: '',
  }
}

function demoMessagesFor(item: AppealHistoryItem): OnlineChatMessage[] {
  const base = item.openedAt || new Date().toISOString()
  const t0 = new Date(base).getTime()
  return [
    {
      id: `${item.id}-c1`,
      dialog_id: item.id,
      speaker: 'client',
      text: item.summary || `Здравствуйте, вопрос по теме: ${item.topic}`,
      created_at: new Date(t0).toISOString(),
    },
    {
      id: `${item.id}-o1`,
      dialog_id: item.id,
      speaker: 'operator',
      text: `Добрый день! Меня зовут ${item.operatorName}. Уточняю информацию по вашему обращению.`,
      created_at: new Date(t0 + 90_000).toISOString(),
    },
    {
      id: `${item.id}-c2`,
      dialog_id: item.id,
      speaker: 'client',
      text: 'Спасибо, жду ответа.',
      created_at: new Date(t0 + 150_000).toISOString(),
    },
    {
      id: `${item.id}-o2`,
      dialog_id: item.id,
      speaker: 'operator',
      text: 'Готово. Если появятся вопросы — пишите в чат.',
      created_at: new Date(t0 + 240_000).toISOString(),
    },
  ]
}

function matchesDemoFilters(
  item: AppealHistoryItem,
  opts: {
    query: string
    channel: string
    status: 'all' | AppealHistoryItem['status']
    dateFrom: string
    dateTo: string
    closeTopic: string
    operatorFilter: string
    clientIp: string
    ratings: number[]
    isElevated: boolean
    operatorName: string
  },
): boolean {
  if (!opts.isElevated && opts.operatorName && item.operatorName !== opts.operatorName) {
    return false
  }
  if (opts.isElevated && opts.operatorFilter.trim() && item.operatorName !== opts.operatorFilter.trim()) {
    return false
  }
  if (opts.channel !== 'all' && item.channel !== opts.channel) return false
  if (opts.status !== 'all' && item.status !== opts.status) return false
  if (opts.closeTopic.trim()) {
    const needle = opts.closeTopic.trim().toLowerCase()
    if (!item.topic.toLowerCase().includes(needle)) return false
  }
  const ipNeedle = opts.clientIp.trim().toLowerCase()
  if (ipNeedle) {
    const itemIp = (item.clientIp || '').toLowerCase()
    if (!itemIp.includes(ipNeedle)) return false
  }
  if (opts.ratings.length) {
    const rating = typeof item.feedbackRating === 'number' ? item.feedbackRating : null
    if (rating === null || !opts.ratings.includes(rating)) return false
  }
  if (opts.dateFrom) {
    const day = item.openedAt.slice(0, 10)
    if (day < opts.dateFrom) return false
  }
  if (opts.dateTo) {
    const day = item.openedAt.slice(0, 10)
    if (day > opts.dateTo) return false
  }
  const q = opts.query.trim().toLowerCase()
  if (!q) return true
  const tokens = q.split(/\s+/).filter(Boolean)
  const hay = [
    item.clientName,
    item.phoneMasked,
    item.topic,
    item.id,
    item.operatorName,
    item.channel,
  ]
    .join(' ')
    .toLowerCase()
  return tokens.every((token) => hay.includes(token))
}

export function HistoryModule({ t, scheme, onBack, armRole, operatorName }: ArmModuleProps) {
  const isElevated = armRole === 'supervisor' || armRole === 'admin'

  const [items, setItems] = useState<AppealHistoryItem[]>([])
  const [dialogsById, setDialogsById] = useState<Record<string, OnlineChatDialog>>({})
  const [usingLive, setUsingLive] = useState(false)
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [channel, setChannel] = useState('all')
  const [status, setStatus] = useState<'all' | AppealHistoryItem['status']>('all')
  const [hasFeedback, setHasFeedback] = useState<FeedbackFilter>('all')
  const [closeTopic, setCloseTopic] = useState('')
  const [debouncedCloseTopic, setDebouncedCloseTopic] = useState('')
  const [clientIpFilter, setClientIpFilter] = useState('')
  const [debouncedClientIpFilter, setDebouncedClientIpFilter] = useState('')
  const [ratingFilter, setRatingFilter] = useState('')
  const [operatorFilter, setOperatorFilter] = useState(() => {
    try {
      return new URLSearchParams(window.location.search).get('historyOperator') || ''
    } catch {
      return ''
    }
  })
  const [selectedId, setSelectedId] = useState<string | null>(() => {
    try {
      return new URLSearchParams(window.location.search).get('historyDialog')
    } catch {
      return null
    }
  })
  const [messages, setMessages] = useState<OnlineChatMessage[]>([])
  const [messagesLoading, setMessagesLoading] = useState(false)
  const [showSkeleton, setShowSkeleton] = useState(false)
  const [messagesError, setMessagesError] = useState('')
  const [filtersCollapsed, setFiltersCollapsed] = useState(false)
  const [leftWidth, setLeftWidth] = useState(320)
  const [rightWidth, setRightWidth] = useState(280)
  const [leftPanelCollapsed, setLeftPanelCollapsed] = useState(false)
  const [rightPanelCollapsed, setRightPanelCollapsed] = useState(false)
  const [transcriptKey, setTranscriptKey] = useState(0)
  const messagesCacheRef = useRef<Record<string, OnlineChatMessage[]>>({})
  const itemsRef = useRef(items)
  itemsRef.current = items
  const knownChannelsRef = useRef<Set<string>>(new Set(CHANNEL_FALLBACK))
  const knownOperatorsRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query), 320)
    return () => window.clearTimeout(timer)
  }, [query])

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedCloseTopic(closeTopic), 320)
    return () => window.clearTimeout(timer)
  }, [closeTopic])

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedClientIpFilter(clientIpFilter), 320)
    return () => window.clearTimeout(timer)
  }, [clientIpFilter])

  const ratingValues = useMemo(() => {
    return Array.from(
      new Set(
        ratingFilter
          .split(/[,\s]+/)
          .map((chunk) => Number.parseInt(chunk, 10))
          .filter((value) => Number.isInteger(value) && value >= 1 && value <= 5),
      ),
    ).sort((a, b) => a - b)
  }, [ratingFilter])

  const refresh = useCallback(async () => {
    const extras: Parameters<typeof listDialogs>[1] = {}
    const q = debouncedQuery.trim()
    if (q) extras.q = q
    if (dateFrom) extras.date_from = dateFrom
    if (dateTo) extras.date_to = dateTo
    if (channel !== 'all') extras.channel = channel
    if (hasFeedback === 'with') extras.has_feedback = true
    if (hasFeedback === 'without') extras.has_feedback = false
    const topic = debouncedCloseTopic.trim()
    if (topic) extras.close_topic = topic
    const ip = debouncedClientIpFilter.trim()
    if (ip) extras.client_ip = ip
    if (ratingValues.length) extras.ratings = ratingValues.join(',')

    if (!isElevated && operatorName) {
      extras.operator_name = operatorName
    } else if (isElevated && operatorFilter.trim()) {
      extras.operator_name = operatorFilter.trim()
    }

    try {
      const [closed, active, waiting] = await Promise.all([
        listDialogs('closed', extras),
        listDialogs('active', extras),
        listDialogs('waiting', extras),
      ])
      const merged = Array.from(
        new Map(
          [...closed, ...active, ...waiting].map((dialog) => [dialog.id, dialog]),
        ).values(),
      ).sort((a, b) => (a.created_at < b.created_at ? 1 : -1))

      const mapped = merged.map(dialogToAppeal)
      const byId: Record<string, OnlineChatDialog> = {}
      for (const dialog of merged) {
        byId[dialog.id] = dialog
        if (dialog.channel) knownChannelsRef.current.add(dialog.channel)
        if (dialog.operator_name) knownOperatorsRef.current.add(dialog.operator_name)
      }
      setItems(mapped)
      setDialogsById((prev) => ({ ...prev, ...byId }))
      setUsingLive(true)
      setSelectedId((prev) =>
        prev && mapped.some((item) => item.id === prev) ? prev : null,
      )
    } catch {
      const demo = DEMO_APPEALS.filter((item) =>
        matchesDemoFilters(item, {
          query: debouncedQuery,
          channel,
          status: 'all',
          dateFrom,
          dateTo,
          closeTopic: debouncedCloseTopic,
          operatorFilter,
          clientIp: debouncedClientIpFilter,
          ratings: ratingValues,
          isElevated,
          operatorName,
        }),
      )
      // has_feedback has no demo signal — hide all when "with", keep when "without"/all
      const demoFiltered =
        hasFeedback === 'with' ? [] : demo
      setItems(demoFiltered)
      setDialogsById({})
      setUsingLive(false)
      setSelectedId((prev) =>
        prev && demoFiltered.some((item) => item.id === prev) ? prev : null,
      )
    }
  }, [
    debouncedQuery,
    dateFrom,
    dateTo,
    channel,
    hasFeedback,
    debouncedCloseTopic,
    debouncedClientIpFilter,
    ratingValues,
    operatorFilter,
    isElevated,
    operatorName,
  ])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => {
      void refresh()
    }, 5000)
    return () => window.clearInterval(timer)
  }, [refresh])

  useEffect(() => {
    if (!selectedId) {
      setMessages([])
      setMessagesError('')
      setMessagesLoading(false)
      setShowSkeleton(false)
      return
    }

    let cancelled = false
    setMessagesError('')
    setTranscriptKey((key) => key + 1)

    const cached = messagesCacheRef.current[selectedId]
    if (cached) {
      setMessages(cached)
      setMessagesLoading(false)
      setShowSkeleton(false)
    } else {
      setMessages([])
      setMessagesLoading(true)
    }

    // Skeleton only if load takes noticeable time and we have nothing to show.
    const skeletonTimer = window.setTimeout(() => {
      if (!cancelled && !messagesCacheRef.current[selectedId]) {
        setShowSkeleton(true)
      }
    }, 160)

    if (!usingLive) {
      const demoItem = itemsRef.current.find((item) => item.id === selectedId)
      const demo = demoItem ? demoMessagesFor(demoItem) : []
      messagesCacheRef.current[selectedId] = demo
      setMessages(demo)
      setMessagesLoading(false)
      setShowSkeleton(false)
      window.clearTimeout(skeletonTimer)
      return () => {
        cancelled = true
        window.clearTimeout(skeletonTimer)
      }
    }

    void getDialog(selectedId)
      .then((dialog) => {
        if (cancelled) return
        const next = dialog.messages ?? []
        messagesCacheRef.current[dialog.id] = next
        setDialogsById((prev) => ({ ...prev, [dialog.id]: dialog }))
        setMessages(next)
      })
      .catch(() => {
        if (!cancelled && !messagesCacheRef.current[selectedId]) {
          setMessages([])
          setMessagesError('Не удалось загрузить переписку')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setMessagesLoading(false)
          setShowSkeleton(false)
        }
      })

    return () => {
      cancelled = true
      window.clearTimeout(skeletonTimer)
    }
  }, [selectedId, usingLive])

  const channels = useMemo(() => {
    const fromItems = items.map((item) => item.channel)
    return ['all', ...Array.from(new Set([...knownChannelsRef.current, ...fromItems])).sort()]
  }, [items])

  const operatorOptions = useMemo(() => {
    const fromItems = items.map((item) => item.operatorName).filter((name) => name && name !== '—')
    return Array.from(new Set([...knownOperatorsRef.current, ...fromItems])).sort()
  }, [items])

  const filtered = useMemo(() => {
    return items.filter((item) => {
      if (status !== 'all' && item.status !== status) return false
      if (!usingLive) {
        return matchesDemoFilters(item, {
          query: debouncedQuery,
          channel,
          status: 'all',
          dateFrom,
          dateTo,
          closeTopic: debouncedCloseTopic,
          operatorFilter,
          clientIp: debouncedClientIpFilter,
          ratings: ratingValues,
          isElevated,
          operatorName,
        })
      }
      return true
    })
  }, [
    items,
    status,
    usingLive,
    debouncedQuery,
    channel,
    dateFrom,
    dateTo,
    debouncedCloseTopic,
    debouncedClientIpFilter,
    ratingValues,
    operatorFilter,
    isElevated,
    operatorName,
  ])

  const selected = selectedId
    ? filtered.find((item) => item.id === selectedId) ?? items.find((item) => item.id === selectedId) ?? null
    : null
  const selectedDialog = selected ? dialogsById[selected.id] : undefined
  const showEmpty = !messagesLoading && !showSkeleton && !messagesError && messages.length === 0

  return (
    <ArmModuleFrame
      t={t}
      scheme={scheme}
      title="История обращений"
      subtitle="Библиотека диалогов для QA и супервизоров — поиск по переписке и фильтрам"
      onBack={onBack}
      bodyStyle={{ overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
    >
      <div style={{ borderBottom: `1px solid ${t.stroke.tertiary}`, flexShrink: 0 }}>
        <div
          style={{
            padding: '10px 12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 8,
          }}
        >
          <Text weight="semibold" style={{ fontSize: 13 }}>Фильтры</Text>
          <button
            type="button"
            onClick={() => setFiltersCollapsed((open) => !open)}
            style={ghostButtonStyle(t)}
          >
            {filtersCollapsed ? 'Развернуть' : 'Свернуть'}
          </button>
        </div>
        {!filtersCollapsed ? (
          <div
            style={{
              padding: '0 12px 10px',
              display: 'flex',
              gap: 10,
              flexWrap: 'wrap',
              alignItems: 'center',
            }}
          >
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="слова в диалоге (оператор, IP, тема, телефон...)"
              title="Несколько слов через пробел — все должны встретиться в метаданных или тексте сообщений (AND)"
              style={{
                flex: '1 1 260px',
                minWidth: 220,
                padding: '8px 10px',
                borderRadius: 8,
                border: `1px solid ${t.stroke.secondary}`,
                background: t.bg.editor,
                color: t.text.primary,
                fontFamily: 'inherit',
                fontSize: 13,
              }}
            />
            <label style={labelStyle(t)}>
              с
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                style={dateInputStyle(t)}
              />
            </label>
            <label style={labelStyle(t)}>
              по
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                style={dateInputStyle(t)}
              />
            </label>
            <select
              value={channel}
              onChange={(e) => setChannel(e.target.value)}
              style={selectStyle(t)}
            >
              {channels.map((value) => (
                <option key={value} value={value}>
                  {value === 'all' ? 'Все каналы' : value}
                </option>
              ))}
            </select>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as typeof status)}
              style={selectStyle(t)}
            >
              <option value="all">Все статусы</option>
              <option value="closed">Закрытые</option>
              <option value="active">В работе</option>
              <option value="lost">Потерянные</option>
              <option value="offline">Офлайн</option>
            </select>
            <select
              value={hasFeedback}
              onChange={(e) => setHasFeedback(e.target.value as FeedbackFilter)}
              style={selectStyle(t)}
            >
              <option value="all">Оценка: все</option>
              <option value="with">С оценкой</option>
              <option value="without">Без оценки</option>
            </select>
            <input
              value={closeTopic}
              onChange={(e) => setCloseTopic(e.target.value)}
              placeholder="тема/слова закрытия"
              style={filterInputStyle(t)}
            />
            <input
              value={clientIpFilter}
              onChange={(e) => setClientIpFilter(e.target.value)}
              placeholder="IP клиента"
              style={filterInputStyle(t)}
            />
            <input
              value={ratingFilter}
              onChange={(e) => setRatingFilter(e.target.value)}
              placeholder="оценки (пример: 4,5)"
              style={filterInputStyle(t)}
            />
            {isElevated ? (
              <select
                value={operatorFilter}
                onChange={(e) => setOperatorFilter(e.target.value)}
                style={selectStyle(t)}
              >
                <option value="">Все операторы</option>
                {operatorOptions.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            ) : null}
            <Text style={{ fontSize: 12, color: t.text.tertiary }}>
              {filtered.length} из {items.length}
            </Text>
          </div>
        ) : null}
      </div>

      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        {/* Left: dialog library */}
        {leftPanelCollapsed ? (
          <aside style={collapsedPanelStyle(t)}>
            <button type="button" onClick={() => setLeftPanelCollapsed(false)} style={collapsedToggleStyle(t)}>
              ▸
            </button>
          </aside>
        ) : (
          <>
            <aside
              style={{
                width: leftWidth,
                flexShrink: 0,
                borderRight: `1px solid ${t.stroke.secondary}`,
                overflowY: 'auto',
                padding: 8,
                background: t.bg.editor,
                minWidth: HISTORY_LEFT_WIDTH_MIN,
                maxWidth: HISTORY_LEFT_WIDTH_MAX,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <Text weight="semibold" style={{ fontSize: 12 }}>Список диалогов</Text>
                <button type="button" onClick={() => setLeftPanelCollapsed(true)} style={ghostButtonStyle(t)}>
                  Свернуть
                </button>
              </div>
              {filtered.length === 0 ? (
                <ModuleEmpty t={t} title="Ничего не найдено" hint="Измените фильтры или поисковый запрос." />
              ) : (
                filtered.map((item) => {
                  const active = selectedId === item.id
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setSelectedId(item.id)}
                      style={{
                        width: '100%',
                        textAlign: 'left',
                        padding: '11px 12px',
                        marginBottom: 6,
                        borderRadius: 10,
                        border: `1px solid ${active ? scheme.accent : t.stroke.tertiary}`,
                        background: active ? t.fill.tertiary : t.bg.elevated,
                        cursor: 'pointer',
                        fontFamily: 'inherit',
                        color: t.text.primary,
                      }}
                    >
                      <Row style={{ justifyContent: 'space-between', gap: 8 }}>
                        <Text weight="semibold" style={{ fontSize: 13 }}>{item.clientName}</Text>
                        <Pill tone={STATUS_TONE[item.status]} size="sm">{STATUS_LABEL[item.status]}</Pill>
                      </Row>
                      <Text style={{ fontSize: 12, color: t.text.secondary, marginTop: 4 }}>
                        {item.channel} · {item.topic}
                      </Text>
                      <Text style={{ fontSize: 11, color: t.text.tertiary, marginTop: 4 }}>
                        {formatDateTime(item.openedAt)} · {item.operatorName}
                      </Text>
                    </button>
                  )
                })
              )}
            </aside>
            <HistoryResizeHandle
              t={t}
              label="Изменить ширину списка диалогов"
              onMouseDown={(event) =>
                startColumnResize(
                  event,
                  leftWidth,
                  setLeftWidth,
                  HISTORY_LEFT_WIDTH_MIN,
                  HISTORY_LEFT_WIDTH_MAX,
                )}
            />
          </>
        )}

        {/* Center: transcript */}
        <section
          style={{
            flex: 1,
            minWidth: 0,
            display: 'flex',
            flexDirection: 'column',
            background: t.bg.elevated,
            borderRight: `1px solid ${t.stroke.secondary}`,
          }}
        >
          {!selected ? (
            <ModuleEmpty
              t={t}
              title="Выберите диалог"
              hint="Список слева — библиотека обращений. После выбора здесь откроется полная переписка."
            />
          ) : (
            <>
              <div
                style={{
                  padding: '10px 16px',
                  borderBottom: `1px solid ${t.stroke.tertiary}`,
                  flexShrink: 0,
                }}
              >
                <Text weight="semibold" style={{ fontSize: 15 }}>
                  {selected.clientName}
                </Text>
                <Text style={{ fontSize: 12, color: t.text.secondary, marginTop: 2 }}>
                  {selected.channel} · {STATUS_LABEL[selected.status]} · №{' '}
                  {dialogRefCode({ id: selected.id, ref_code: selectedDialog?.ref_code })}
                </Text>
              </div>
              <div
                style={{
                  flex: 1,
                  minHeight: 0,
                  overflowY: 'auto',
                  padding: '14px 16px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 10,
                  position: 'relative',
                }}
              >
                <style>{`
                  @keyframes historyShimmer {
                    0% { background-position: 100% 0; }
                    100% { background-position: -100% 0; }
                  }
                  @keyframes historyFadeIn {
                    from { opacity: 0; transform: translateY(4px); }
                    to { opacity: 1; transform: translateY(0); }
                  }
                `}</style>
                {messagesError ? (
                  <Text style={{ fontSize: 13, color: '#C62828' }}>{messagesError}</Text>
                ) : null}
                {showSkeleton ? (
                  <TranscriptSkeleton t={t} scheme={scheme} />
                ) : null}
                {showEmpty ? (
                  <ModuleEmpty t={t} title="Нет сообщений" hint="В этом диалоге пока нет сохранённой переписки." />
                ) : null}
                {!showSkeleton && messages.length > 0 ? (
                  <div
                    key={transcriptKey}
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 10,
                      animation: 'historyFadeIn 180ms ease-out',
                    }}
                  >
                    {messages.map((message) => (
                      <HistoryMessageBubble
                        key={message.id}
                        t={t}
                        scheme={scheme}
                        message={message}
                        clientName={selected.clientName}
                        operatorName={selected.operatorName}
                      />
                    ))}
                  </div>
                ) : null}
                {messagesLoading && messages.length > 0 ? (
                  <div
                    aria-hidden
                    style={{
                      position: 'absolute',
                      top: 10,
                      right: 14,
                      width: 8,
                      height: 8,
                      borderRadius: 999,
                      background: scheme.accentControl,
                      opacity: 0.55,
                      boxShadow: `0 0 0 4px ${scheme.accentWeak}`,
                    }}
                  />
                ) : null}
              </div>
            </>
          )}
        </section>

        {/* Right: brief facts */}
        {!rightPanelCollapsed ? (
          <>
            <HistoryResizeHandle
              t={t}
              label="Изменить ширину блока метаданных"
              onMouseDown={(event) =>
                startColumnResize(
                  event,
                  rightWidth,
                  setRightWidth,
                  HISTORY_RIGHT_WIDTH_MIN,
                  HISTORY_RIGHT_WIDTH_MAX,
                  true,
                )}
            />
            <aside
              style={{
                width: rightWidth,
                minWidth: HISTORY_RIGHT_WIDTH_MIN,
                maxWidth: HISTORY_RIGHT_WIDTH_MAX,
                flexShrink: 0,
                overflowY: 'auto',
                padding: 14,
                background: t.bg.editor,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <Text weight="semibold" style={{ fontSize: 12 }}>Данные</Text>
                <button type="button" onClick={() => setRightPanelCollapsed(true)} style={ghostButtonStyle(t)}>
                  Свернуть
                </button>
              </div>
          {!selected ? (
            <Text style={{ fontSize: 12, color: t.text.tertiary, lineHeight: 1.45 }}>
              Здесь появится краткая информация о выбранном диалоге и участниках.
            </Text>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div>
                <Text weight="semibold" style={{ fontSize: 14, marginBottom: 8 }}>
                  О диалоге
                </Text>
                <div style={{ display: 'grid', gap: 10 }}>
                  <Meta t={t} label="Статус" value={STATUS_LABEL[selected.status]} />
                  <Meta t={t} label="Канал" value={selected.channel} />
                  <div>
                    <Text style={{ fontSize: 11, color: t.text.tertiary }}>Тема закрытия</Text>
                    <div style={{ marginTop: 4 }}>
                      <TopicChip t={t} topic={selected.topic || 'Без темы'} size="sm" />
                    </div>
                  </div>
                  <Meta t={t} label="Открыт" value={formatDateTime(selected.openedAt)} />
                  {selected.closedAt ? (
                    <Meta t={t} label="Закрыт" value={formatDateTime(selected.closedAt)} />
                  ) : null}
                  {selectedDialog?.accepted_at ? (
                    <Meta t={t} label="Принят оператором" value={formatDateTime(selectedDialog.accepted_at)} />
                  ) : null}
                  {typeof selectedDialog?.wait_seconds === 'number' ? (
                    <Meta
                      t={t}
                      label="Ожидание в очереди"
                      value={`${Math.max(0, Math.round(selectedDialog.wait_seconds))} с`}
                    />
                  ) : null}
                  {typeof selectedDialog?.has_feedback === 'boolean' ? (
                    <Meta
                      t={t}
                      label="Оценка"
                      value={
                        typeof selectedDialog.feedback_rating === 'number'
                          ? `${selectedDialog.feedback_rating}/5`
                          : selectedDialog.has_feedback
                            ? 'Есть'
                            : 'Нет'
                      }
                    />
                  ) : null}
                  <Meta
                    t={t}
                    label="№ обращения"
                    value={dialogRefCode({ id: selected.id, ref_code: selectedDialog?.ref_code })}
                  />
                </div>
              </div>

              <div
                style={{
                  height: 1,
                  background: t.stroke.tertiary,
                }}
              />

              <div>
                <Text weight="semibold" style={{ fontSize: 14, marginBottom: 8 }}>
                  Участники
                </Text>
                <div style={{ display: 'grid', gap: 10 }}>
                  <Meta t={t} label="Клиент" value={selected.clientName} />
                  <Meta t={t} label="Телефон" value={selected.phoneMasked || '—'} />
                  <Meta t={t} label="IP клиента" value={selected.clientIp || '—'} />
                  <Meta t={t} label="Оператор" value={selected.operatorName || '—'} />
                  {selectedDialog?.department_name ? (
                    <Meta t={t} label="Отдел" value={selectedDialog.department_name} />
                  ) : null}
                  {selectedDialog?.placement ? (
                    <Meta t={t} label="Точка входа" value={selectedDialog.placement} />
                  ) : null}
                </div>
              </div>

              <Text style={{ fontSize: 11, color: t.text.tertiary, lineHeight: 1.4 }}>
                Режим просмотра: сообщения только для чтения.
              </Text>
            </div>
          )}
            </aside>
          </>
        ) : (
          <aside style={collapsedPanelStyle(t)}>
            <button type="button" onClick={() => setRightPanelCollapsed(false)} style={collapsedToggleStyle(t)}>
              ◂
            </button>
          </aside>
        )}
      </div>
    </ArmModuleFrame>
  )
}

function TranscriptSkeleton({
  t,
  scheme,
}: {
  t: ArmTheme
  scheme: ModuleSchemePalette
}) {
  const bars = [
    { side: 'left' as const, width: '62%' },
    { side: 'right' as const, width: '54%' },
    { side: 'left' as const, width: '71%' },
    { side: 'right' as const, width: '48%' },
    { side: 'left' as const, width: '58%' },
  ]
  const shimmer = {
    backgroundImage: `linear-gradient(90deg, ${t.fill.tertiary} 0%, ${scheme.accentWeak} 45%, ${t.fill.tertiary} 90%)`,
    backgroundSize: '200% 100%',
    animation: 'historyShimmer 1.1s ease-in-out infinite',
  }

  return (
    <div
      aria-hidden
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
        paddingTop: 4,
        animation: 'historyFadeIn 160ms ease-out',
      }}
    >
      {bars.map((bar, index) => (
        <div
          key={index}
          style={{
            display: 'flex',
            justifyContent: bar.side === 'left' ? 'flex-start' : 'flex-end',
          }}
        >
          <div
            style={{
              width: bar.width,
              maxWidth: 420,
              height: index % 2 === 0 ? 52 : 40,
              borderRadius: 12,
              borderBottomRightRadius: bar.side === 'right' ? 4 : 12,
              borderBottomLeftRadius: bar.side === 'left' ? 4 : 12,
              ...shimmer,
            }}
          />
        </div>
      ))}
    </div>
  )
}

function HistoryMessageBubble({
  t,
  scheme,
  message,
  clientName,
  operatorName,
}: {
  t: ArmTheme
  scheme: ModuleSchemePalette
  message: OnlineChatMessage
  clientName: string
  operatorName: string
}) {
  if (message.speaker === 'system') {
    return (
      <Text
        style={{
          textAlign: 'center',
          fontSize: 11,
          color: t.text.tertiary,
          padding: '6px 0',
        }}
      >
        {message.text}
      </Text>
    )
  }

  const isOp = message.speaker === 'operator' || message.speaker === 'bot'
  const label =
    message.speaker === 'bot'
      ? 'Бот'
      : message.speaker === 'operator'
        ? operatorName
        : clientName
  const body = message.is_deleted
    ? 'Сообщение удалено'
    : message.text || (message.attachment_name ? `📎 ${message.attachment_name}` : '')

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: isOp ? 'flex-end' : 'flex-start',
      }}
    >
      <div
        style={{
          maxWidth: '78%',
          padding: '10px 12px 8px',
          borderRadius: 12,
          borderBottomRightRadius: isOp ? 4 : 12,
          borderBottomLeftRadius: isOp ? 12 : 4,
          background: isOp ? scheme.headerBg : t.bg.editor,
          border: `1px solid ${isOp ? scheme.accent : t.stroke.secondary}`,
        }}
      >
        <Text style={{ fontSize: 11, color: t.text.tertiary, marginBottom: 4 }}>{label}</Text>
        {message.quoted_text ? (
          <div
            style={{
              marginBottom: 6,
              padding: '6px 8px',
              borderRadius: 8,
              borderLeft: `3px solid ${scheme.accentControl}`,
              background: t.fill.tertiary,
              fontSize: 12,
              color: t.text.secondary,
            }}
          >
            {message.quoted_text}
          </div>
        ) : null}
        <Text
          style={{
            fontSize: 13,
            lineHeight: 1.45,
            whiteSpace: 'pre-wrap',
            fontStyle: message.is_deleted ? 'italic' : undefined,
            color: message.is_deleted ? t.text.tertiary : t.text.primary,
          }}
        >
          {body}
        </Text>
        <Text style={{ fontSize: 10, color: t.text.tertiary, marginTop: 6, textAlign: 'right' }}>
          {formatTime(message.created_at)}
          {message.edited_at ? ' · изм.' : ''}
        </Text>
      </div>
    </div>
  )
}

function Meta({ t, label, value }: { t: ArmModuleProps['t']; label: string; value: string }) {
  return (
    <div>
      <Text style={{ fontSize: 11, color: t.text.tertiary }}>{label}</Text>
      <Text style={{ fontSize: 13, marginTop: 2, lineHeight: 1.35 }}>{value}</Text>
    </div>
  )
}

function HistoryResizeHandle({
  t,
  label,
  onMouseDown,
}: {
  t: ArmTheme
  label: string
  onMouseDown: (event: { clientX: number; preventDefault: () => void }) => void
}) {
  return (
    <div
      role="separator"
      aria-label={label}
      title="Перетащите для изменения ширины"
      onMouseDown={onMouseDown}
      style={{
        width: 10,
        flexShrink: 0,
        alignSelf: 'stretch',
        cursor: 'col-resize',
        background: t.fill.secondary,
        borderLeft: `1px solid ${t.stroke.secondary}`,
        borderRight: `1px solid ${t.stroke.secondary}`,
      }}
    />
  )
}

function ghostButtonStyle(t: ArmModuleProps['t']): CSSProperties {
  return {
    padding: '6px 8px',
    borderRadius: 8,
    border: `1px solid ${t.stroke.secondary}`,
    background: t.bg.elevated,
    color: t.text.secondary,
    fontFamily: 'inherit',
    fontSize: 12,
    cursor: 'pointer',
  }
}

function filterInputStyle(t: ArmModuleProps['t']): CSSProperties {
  return {
    flex: '0 1 180px',
    minWidth: 140,
    padding: '8px 10px',
    borderRadius: 8,
    border: `1px solid ${t.stroke.secondary}`,
    background: t.bg.editor,
    color: t.text.primary,
    fontFamily: 'inherit',
    fontSize: 13,
  }
}

function collapsedPanelStyle(t: ArmModuleProps['t']): CSSProperties {
  return {
    width: 28,
    flexShrink: 0,
    borderLeft: `1px solid ${t.stroke.secondary}`,
    borderRight: `1px solid ${t.stroke.secondary}`,
    background: t.bg.editor,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  }
}

function collapsedToggleStyle(t: ArmModuleProps['t']): CSSProperties {
  return {
    width: 20,
    height: 44,
    borderRadius: 10,
    border: `1px solid ${t.stroke.secondary}`,
    background: t.bg.elevated,
    color: t.text.secondary,
    cursor: 'pointer',
    fontSize: 12,
  }
}

function selectStyle(t: ArmModuleProps['t']): CSSProperties {
  return {
    padding: '8px 10px',
    borderRadius: 8,
    border: `1px solid ${t.stroke.secondary}`,
    background: t.bg.elevated,
    color: t.text.primary,
    fontFamily: 'inherit',
    fontSize: 13,
  }
}

function labelStyle(t: ArmModuleProps['t']): CSSProperties {
  return {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    fontSize: 12,
    color: t.text.secondary,
  }
}

function dateInputStyle(t: ArmModuleProps['t']): CSSProperties {
  return {
    padding: '7px 8px',
    borderRadius: 8,
    border: `1px solid ${t.stroke.secondary}`,
    background: t.bg.elevated,
    color: t.text.primary,
    fontFamily: 'inherit',
    fontSize: 13,
  }
}
