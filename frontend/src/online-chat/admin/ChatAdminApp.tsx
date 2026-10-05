import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  baseMessagesApi,
  channelsApi,
  botsApi,
  departmentsApi,
  dialogTopicsApi,
  getAdPendingOperators,
  getAnalytics,
  getSlaSettings,
  getWorkScheduleSettings,
  operatorsApi,
  placementsApi,
  routingRulesApi,
  updateSlaSettings,
  updateWorkScheduleSettings,
  type AnalyticsResponse,
  type BaseMessage,
  type ChatChannel,
  type BotConfiguration,
  type ChatOperator,
  type Department,
  type DialogTopicNode,
  type EntityId,
  type RoutingRule,
  type WidgetFormField,
  type WidgetPlacement,
  type WorkDayOverride,
} from '../api/managementApi'
import { TopicGroupIcon, TopicLeafIcon, TrashIcon } from '../arm/topicIcons'
import '../shell/Management.css'

type Tab =
  | 'operators'
  | 'departments'
  | 'placements'
  | 'channels'
  | 'routing'
  | 'bots'
  | 'messages'
  | 'dialog_topics'
  | 'analytics'
  | 'sla'
  | 'schedule'

type ConfirmRequest = {
  title: string
  description: string
}

type PerformFn = (
  action: () => Promise<unknown>,
  message: string,
  confirm?: ConfirmRequest,
) => Promise<boolean>

const tabs: Array<{ id: Tab; label: string }> = [
  { id: 'operators', label: 'Операторы' },
  { id: 'departments', label: 'Отделы' },
  { id: 'placements', label: 'Виджеты' },
  { id: 'channels', label: 'Каналы платформы' },
  { id: 'routing', label: 'Маршрутизация' },
  { id: 'bots', label: 'Боты' },
  { id: 'messages', label: 'Базовые сообщения' },
  { id: 'dialog_topics', label: 'Темы диалогов' },
  { id: 'sla', label: 'SLA' },
  { id: 'schedule', label: 'Рабочий календарь' },
  { id: 'analytics', label: 'Аналитика' },
]

const POPULAR_FORM_FIELDS: WidgetFormField[] = [
  { key: 'name', label: 'Имя', type: 'text', required: true },
  { key: 'last_name', label: 'Фамилия', type: 'text', required: false },
  { key: 'phone', label: 'Телефон', type: 'tel', required: true },
  { key: 'email', label: 'Email', type: 'email', required: false },
  { key: 'account', label: 'Номер счёта или карты', type: 'text', required: false },
  { key: 'city', label: 'Город', type: 'text', required: false },
  { key: 'passport', label: 'Серия и номер паспорта', type: 'text', required: false },
  { key: 'inn', label: 'УНП / ИНН', type: 'text', required: false },
  { key: 'company', label: 'Организация', type: 'text', required: false },
]

const FIELD_KEY_ALIASES: Record<string, string> = {
  first_name: 'name',
  fio: 'name',
  tel: 'phone',
  telephone: 'phone',
  mobile: 'phone',
}

function canonicalFieldKey(key: string): string {
  const normalized = key.trim().toLowerCase()
  return FIELD_KEY_ALIASES[normalized] || normalized
}

function sanitizeFormFields(fields: WidgetFormField[] | undefined | null): WidgetFormField[] {
  if (!Array.isArray(fields)) return []
  const seen = new Set<string>()
  const cleaned: WidgetFormField[] = []
  for (const field of fields) {
    if (!field?.key) continue
    const key = canonicalFieldKey(field.key)
    if (!key || key === 'question' || seen.has(key)) continue
    seen.add(key)
    cleaned.push({
      ...field,
      key,
      required: Boolean(field.required),
      type: key === 'phone' ? 'tel' : key === 'email' ? 'email' : (field.type || 'text'),
    })
  }
  return cleaned
}

function slugHint(value: string): string {
  const ascii = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return ascii || `item-${Date.now().toString(36)}`
}

/** «Шейпа Семен Игоревич» → «Шейпа С.И.» */
function formatOperatorFio(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return ''
  if (parts.length === 1) return parts[0]
  const surname = parts[0]
  const initials = parts
    .slice(1)
    .map((part) => `${part[0]?.toUpperCase() ?? ''}.`)
    .join('')
  return `${surname} ${initials}`.trim()
}

function adRoleLabel(role: string): string {
  const map: Record<string, string> = {
    operator_cc: 'Оператор КЦ',
    supervisor_cc: 'Супервизор КЦ',
    admin_cc: 'Администратор КЦ',
    operator: 'Оператор',
    supervisor: 'Супервизор',
    admin: 'Администратор',
  }
  return map[role] || role
}

/** Demo-only helper: fabricate a "new AD employee" so the yellow onboarding
 * card can be shown on demand. In production the card appears from a real AD
 * sync — this button and generator are hidden outside the demo build. */
const SHOW_AD_DEMO = import.meta.env.DEV || import.meta.env.VITE_SUFLER_DEMO === '1'

const DEMO_AD_PEOPLE: ReadonlyArray<{ display_name: string; email: string; ad_role: string }> = [
  { display_name: 'Ковалёва Анна Сергеевна', email: 'a.kovaleva', ad_role: 'operator_cc' },
  { display_name: 'Дроздов Игорь Петрович', email: 'i.drozdov', ad_role: 'operator_cc' },
  { display_name: 'Савицкая Мария Олеговна', email: 'm.savitskaya', ad_role: 'operator_cc' },
  { display_name: 'Гурский Павел Викторович', email: 'p.gursky', ad_role: 'supervisor_cc' },
  { display_name: 'Лаврик Ольга Дмитриевна', email: 'o.lavrik', ad_role: 'operator_cc' },
]

function makeDemoAdEmployee(): {
  external_id: string
  display_name: string
  email: string
  ad_role: string
  detected_at: string
  needs: string[]
} {
  const person = DEMO_AD_PEOPLE[Math.floor(Math.random() * DEMO_AD_PEOPLE.length)]
  return {
    external_id: `ad-demo-${Date.now()}`,
    display_name: person.display_name,
    email: `${person.email}@belarusbank.by`,
    ad_role: person.ad_role,
    detected_at: new Date().toISOString(),
    needs: ['limits', 'photo', 'skill_tags'],
  }
}

function OperatorAvatarPreview({ url, name }: { url: string; name: string }) {
  return (
    <span className="chat-management__avatar" title={name} aria-hidden={!url}>
      {url ? (
        <img src={url} alt="" />
      ) : (
        <svg viewBox="0 0 40 40" width="40" height="40" aria-hidden>
          <circle cx="20" cy="20" r="20" fill="#d7e3db" />
          <circle cx="20" cy="13" r="9" fill="#7a9486" />
          <path d="M3 40c2.2-12 9.5-17.5 17-17.5S34.8 28 37 40" fill="#7a9486" />
        </svg>
      )}
    </span>
  )
}

/** ARM presence labels; map to backend OperatorPresence on save. */
const ARM_PRESENCE_OPTIONS = [
  { ui: 'online', api: 'online', label: 'в сети' },
  { ui: 'invisible', api: 'offline', label: 'невидимка' },
  { ui: 'break', api: 'break', label: 'перерыв' },
  { ui: 'lunch', api: 'lunch', label: 'обед' },
  { ui: 'tech_break', api: 'tech_issue', label: 'техперерыв' },
  { ui: 'training', api: 'training', label: 'обучение' },
  { ui: 'meeting', api: 'meeting', label: 'встреча' },
  { ui: 'offline_queue', api: 'busy', label: 'офлайн-обращения' },
  { ui: 'offline', api: 'offline', label: 'не в сети' },
] as const

function presenceToUi(presence: string): string {
  if (presence === 'tech_issue') return 'tech_break'
  if (presence === 'busy') return 'offline_queue'
  return presence
}

function presenceToApi(ui: string): ChatOperator['presence'] {
  const found = ARM_PRESENCE_OPTIONS.find((item) => item.ui === ui)
  return (found?.api ?? 'offline') as ChatOperator['presence']
}

const CANONICAL_CHANNELS: Array<{ kind: string; name: string }> = [
  { kind: 'widget', name: 'Виджет сайта' },
  { kind: 'telegram', name: 'Telegram' },
  { kind: 'viber', name: 'Viber' },
  { kind: 'vk', name: 'ВКонтакте' },
  { kind: 'ok', name: 'Одноклассники' },
  { kind: 'api', name: 'API-канал' },
]

const emptyPlacement: Partial<WidgetPlacement> = {
  name: '',
  allowed_domains: [],
  welcome_message: 'Здравствуйте! Оставьте контакты — оператор подключится.',
  offline_message: 'Сейчас вне графика. Оставьте сообщение — ответим в рабочее время.',
  require_phone: true,
  theme_accent: '#007A43',
  form_fields: [
    { key: 'name', label: 'Имя', type: 'text', required: true },
    { key: 'last_name', label: 'Фамилия', type: 'text', required: false },
    { key: 'phone', label: 'Телефон', type: 'tel', required: true },
  ],
  is_active: true,
}

function departmentName(
  value: Department | EntityId | null | undefined,
  departments: Department[],
) {
  if (value && typeof value === 'object') return value.name
  return departments.find((item) => String(item.id) === String(value))?.name ?? '—'
}

function entityDepartmentId(entity: {
  department?: Department | EntityId | null
  department_id?: EntityId | null
}) {
  return entity.department_id ?? (entity.department && typeof entity.department === 'object'
    ? entity.department.id
    : entity.department) ?? ''
}

export function ChatAdminApp() {
  const [tab, setTab] = useState<Tab>('operators')
  const [departments, setDepartments] = useState<Department[]>([])
  const [operators, setOperators] = useState<ChatOperator[]>([])
  const [placements, setPlacements] = useState<WidgetPlacement[]>([])
  const [channels, setChannels] = useState<ChatChannel[]>([])
  const [rules, setRules] = useState<RoutingRule[]>([])
  const [bots, setBots] = useState<BotConfiguration[]>([])
  const [baseMessages, setBaseMessages] = useState<BaseMessage[]>([])
  const [dialogTopics, setDialogTopics] = useState<DialogTopicNode[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [pendingConfirm, setPendingConfirm] = useState<{
    title: string
    description: string
    action: () => Promise<unknown>
    message: string
  } | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const results = await Promise.allSettled([
        departmentsApi.list(),
        operatorsApi.list(),
        placementsApi.list(),
        channelsApi.list(),
        routingRulesApi.list(),
        botsApi.list(),
        baseMessagesApi.list(),
        dialogTopicsApi.list(false),
      ])
      const [
        departmentResult,
        operatorResult,
        placementResult,
        channelResult,
        ruleResult,
        botResult,
        messageResult,
        topicsResult,
      ] = results

      if (departmentResult.status === 'fulfilled') setDepartments(departmentResult.value)
      if (operatorResult.status === 'fulfilled') setOperators(operatorResult.value)
      if (placementResult.status === 'fulfilled') setPlacements(placementResult.value)
      if (channelResult.status === 'fulfilled') setChannels(channelResult.value)
      if (ruleResult.status === 'fulfilled') setRules(ruleResult.value)
      if (botResult.status === 'fulfilled') setBots(botResult.value)
      if (messageResult.status === 'fulfilled') setBaseMessages(messageResult.value)
      if (topicsResult.status === 'fulfilled') setDialogTopics(topicsResult.value)

      const failed = results.find((item) => item.status === 'rejected') as PromiseRejectedResult | undefined
      if (failed) {
        setError(failed.reason instanceof Error ? failed.reason.message : 'Не удалось загрузить часть настроек')
      } else {
        setError('')
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Не удалось загрузить настройки')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const runAction = async (action: () => Promise<unknown>, message: string) => {
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      await action()
      setSuccess(message)
      try {
        await refresh()
      } catch (refreshError) {
        setError(
          refreshError instanceof Error
            ? refreshError.message
            : 'Сохранено, но список настроек не обновился',
        )
      }
      return true
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Операция не выполнена')
      return false
    } finally {
      setSaving(false)
    }
  }

  const perform: PerformFn = async (action, message, confirm) => {
    if (confirm) {
      setPendingConfirm({
        title: confirm.title,
        description: confirm.description,
        action,
        message,
      })
      return false
    }
    return runAction(action, message)
  }

  return (
    <main className="chat-management">
      <div className="chat-management__inner">
        <div className="chat-management__heading">
          <div>
            <h1>Управление онлайн-чатом</h1>
            <p className="chat-management__muted">Операторы, точки входа и правила распределения</p>
          </div>
          <button className="is-secondary" onClick={() => void refresh()} disabled={loading}>
            {loading ? 'Загрузка…' : 'Обновить'}
          </button>
        </div>
        {error && <p className="chat-management__error" role="alert">{error}</p>}
        {success && <p className="chat-management__success" role="status">{success}</p>}
        {pendingConfirm ? (
          <div className="chat-management__confirm" role="dialog" aria-modal="true" aria-labelledby="admin-confirm-title">
            <div className="chat-management__confirm-card">
              <h2 id="admin-confirm-title">{pendingConfirm.title}</h2>
              <p>{pendingConfirm.description}</p>
              <div className="chat-management__actions">
                <button
                  type="button"
                  className="is-secondary"
                  onClick={() => setPendingConfirm(null)}
                  disabled={saving}
                >
                  Отмена
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const current = pendingConfirm
                    setPendingConfirm(null)
                    void runAction(current.action, current.message)
                  }}
                  disabled={saving}
                >
                  Подтвердить
                </button>
              </div>
            </div>
          </div>
        ) : null}
        <div className="chat-management__tabs" role="tablist" aria-label="Настройки онлайн-чата">
          {tabs.map((item) => (
            <button
              key={item.id}
              role="tab"
              aria-selected={tab === item.id}
              className={tab === item.id ? 'is-active' : undefined}
              onClick={() => {
                setTab(item.id)
                setSuccess('')
              }}
            >
              {item.label}
            </button>
          ))}
        </div>

        {tab === 'operators' && (
          <OperatorsTab
            items={operators}
            departments={departments}
            disabled={saving}
            perform={perform}
          />
        )}
        {tab === 'departments' && (
          <DepartmentsTab items={departments} disabled={saving} perform={perform} />
        )}
        {tab === 'placements' && (
          <PlacementsTab
            items={placements}
            departments={departments}
            disabled={saving}
            perform={perform}
          />
        )}
        {tab === 'channels' && (
          <ChannelsTab
            items={channels}
            placements={placements}
            disabled={saving}
            perform={perform}
          />
        )}
        {tab === 'routing' && (
          <RoutingTab
            items={rules}
            departments={departments}
            channels={channels}
            disabled={saving}
            perform={perform}
          />
        )}
        {tab === 'bots' && (
          <BotsTab
            items={bots}
            disabled={saving}
            perform={perform}
          />
        )}
        {tab === 'messages' && (
          <BaseMessagesTab
            items={baseMessages}
            placements={placements}
            channels={channels}
            disabled={saving}
            perform={perform}
          />
        )}
        {tab === 'dialog_topics' && (
          <DialogTopicsTab
            items={dialogTopics}
            disabled={saving}
            perform={perform}
          />
        )}
        {tab === 'sla' && <SlaTab disabled={saving} perform={perform} />}
        {tab === 'schedule' && <WorkScheduleTab disabled={saving} perform={perform} />}
        {tab === 'analytics' && <AnalyticsTab />}
      </div>
    </main>
  )
}

function DialogTopicsTab({
  items,
  disabled,
  perform,
}: {
  items: DialogTopicNode[]
  disabled: boolean
  perform: PerformFn
}) {
  const [trailIds, setTrailIds] = useState<string[]>([])
  const [deleteMode, setDeleteMode] = useState(false)
  const [draftKind, setDraftKind] = useState<'group' | 'leaf' | null>(null)
  const [draftName, setDraftName] = useState('')
  const [dragId, setDragId] = useState<string | null>(null)
  const [dragOverId, setDragOverId] = useState<string | null>(null)

  const findNode = (nodes: DialogTopicNode[], id: string): DialogTopicNode | null => {
    for (const node of nodes) {
      if (String(node.id) === id) return node
      if (node.children?.length) {
        const found = findNode(node.children, id)
        if (found) return found
      }
    }
    return null
  }

  const trail = useMemo(() => {
    const resolved: DialogTopicNode[] = []
    for (const id of trailIds) {
      const found = findNode(items, id)
      if (!found) break
      resolved.push(found)
    }
    return resolved
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, trailIds])

  useEffect(() => {
    if (trail.length !== trailIds.length) {
      setTrailIds(trail.map((node) => String(node.id)))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trail])

  const currentParent = trail.at(-1) ?? null
  const levelNodes = currentParent ? (currentParent.children ?? []) : items

  const openNode = (node: DialogTopicNode) => {
    if (node.is_selectable) return
    setDeleteMode(false)
    setTrailIds((prev) => [...prev, String(node.id)])
  }

  const goToDepth = (depth: number) => setTrailIds((prev) => prev.slice(0, depth))

  const openDraft = (kind: 'group' | 'leaf') => {
    setDraftKind(kind)
    setDraftName('')
  }

  const closeDraft = () => {
    setDraftKind(null)
    setDraftName('')
  }

  const submitDraft = async () => {
    if (!draftKind) return
    const label = draftName.trim()
    if (!label) return
    const nextSortOrder = levelNodes.length
      ? Math.max(...levelNodes.map((node) => node.sort_order)) + 10
      : 10
    const ok = await perform(
      () => dialogTopicsApi.create({
        label,
        parent_id: currentParent ? currentParent.id : null,
        sort_order: nextSortOrder,
        is_selectable: draftKind === 'leaf',
      }),
      draftKind === 'leaf' ? 'Тема добавлена.' : 'Вложение добавлено.',
    )
    if (ok) closeDraft()
  }

  const removeNode = (node: DialogTopicNode) => {
    void perform(
      () => dialogTopicsApi.remove(node.id),
      'Удалено.',
      {
        title: node.is_selectable ? 'Удалить тему?' : 'Удалить вложение?',
        description: node.is_selectable
          ? 'Это действие нельзя отменить.'
          : 'Это действие нельзя отменить. Все темы и вложения внутри также будут удалены.',
      },
    )
  }

  const handleDrop = (targetId: string) => {
    const sourceId = dragId
    setDragId(null)
    setDragOverId(null)
    if (!sourceId || sourceId === targetId) return
    const ids = levelNodes.map((node) => String(node.id))
    const fromIndex = ids.indexOf(sourceId)
    const toIndex = ids.indexOf(targetId)
    if (fromIndex === -1 || toIndex === -1) return
    const next = [...ids]
    next.splice(fromIndex, 1)
    next.splice(toIndex, 0, sourceId)
    const parentId = currentParent ? currentParent.id : null
    void perform(
      () => Promise.all(
        next.map((id, index) => dialogTopicsApi.reorder({ id, parent_id: parentId, sort_order: (index + 1) * 10 })),
      ),
      'Порядок обновлён.',
    )
  }

  return (
    <div className="chat-management__card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
        <h2 style={{ margin: 0 }}>Темы диалогов</h2>
        <div className="chat-management__actions">
          <button
            type="button"
            className="is-secondary"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
            onClick={() => openDraft('group')}
            disabled={disabled}
            title="Добавить вложение"
          >
            <TopicGroupIcon size={15} />
            Вложение
          </button>
          <button
            type="button"
            className="is-secondary"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
            onClick={() => openDraft('leaf')}
            disabled={disabled}
            title="Добавить тему"
          >
            <TopicLeafIcon size={15} />
            Тема
          </button>
          <button
            type="button"
            className={deleteMode ? 'is-danger' : 'is-secondary'}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
            onClick={() => setDeleteMode((prev) => !prev)}
            disabled={disabled}
            title="Удалить"
          >
            <TrashIcon size={15} />
            Удалить
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginTop: 16, marginBottom: 12 }}>
        <button
          type="button"
          className="is-secondary"
          style={{ padding: '4px 10px', minHeight: 30, fontWeight: trailIds.length === 0 ? 700 : 500 }}
          onClick={() => goToDepth(0)}
          disabled={trailIds.length === 0}
        >
          Все темы
        </button>
        {trail.map((node, index) => (
          <span key={String(node.id)} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span aria-hidden style={{ color: 'var(--arm-t-tertiary)' }}>/</span>
            <button
              type="button"
              className="is-secondary"
              style={{ padding: '4px 10px', minHeight: 30, fontWeight: index === trail.length - 1 ? 700 : 500 }}
              onClick={() => goToDepth(index + 1)}
              disabled={index === trail.length - 1}
            >
              {node.label}
            </button>
          </span>
        ))}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {levelNodes.length === 0 ? (
          <p className="chat-management__muted">Список пуст. Добавьте вложение или тему.</p>
        ) : (
          levelNodes.map((node) => {
            const nodeId = String(node.id)
            const isGroup = !node.is_selectable
            return (
              <div
                key={nodeId}
                draggable={!disabled}
                onDragStart={() => setDragId(nodeId)}
                onDragOver={(event) => {
                  event.preventDefault()
                  if (dragOverId !== nodeId) setDragOverId(nodeId)
                }}
                onDragLeave={() => setDragOverId((prev) => (prev === nodeId ? null : prev))}
                onDrop={(event) => {
                  event.preventDefault()
                  handleDrop(nodeId)
                }}
                onDragEnd={() => {
                  setDragId(null)
                  setDragOverId(null)
                }}
                onClick={() => openNode(node)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '10px 12px',
                  borderRadius: 8,
                  border: `1px solid ${dragOverId === nodeId ? 'var(--arm-accent-control)' : 'var(--arm-stroke-tertiary)'}`,
                  background: dragId === nodeId ? 'var(--arm-fill-tertiary)' : 'var(--arm-bg-elevated)',
                  cursor: isGroup ? 'pointer' : 'default',
                }}
              >
                <span aria-hidden style={{ cursor: 'grab', color: 'var(--arm-t-tertiary)', lineHeight: 1, fontSize: 14 }}>⠿⠿</span>
                {isGroup ? (
                  <TopicGroupIcon size={16} color="var(--arm-accent-control)" style={{ flexShrink: 0 }} />
                ) : (
                  <TopicLeafIcon size={16} color="var(--arm-t-secondary)" style={{ flexShrink: 0 }} />
                )}
                <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {node.label}
                </span>
                {isGroup ? <span aria-hidden style={{ color: 'var(--arm-t-tertiary)', flexShrink: 0 }}>›</span> : null}
                {deleteMode ? (
                  <button
                    type="button"
                    className="is-danger"
                    style={{ padding: '2px 9px', minHeight: 26, flexShrink: 0 }}
                    onClick={(event) => {
                      event.stopPropagation()
                      removeNode(node)
                    }}
                    aria-label={`Удалить «${node.label}»`}
                    disabled={disabled}
                  >
                    ×
                  </button>
                ) : null}
              </div>
            )
          })
        )}
      </div>

      {draftKind ? (
        <div className="chat-management__confirm" role="dialog" aria-modal="true" aria-labelledby="dialog-topic-draft-title">
          <div className="chat-management__confirm-card">
            <h2 id="dialog-topic-draft-title">{draftKind === 'leaf' ? 'Новая тема' : 'Новое вложение'}</h2>
            <label>
              Название
              <input
                autoFocus
                value={draftName}
                onChange={(event) => setDraftName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    void submitDraft()
                  }
                }}
              />
            </label>
            <div className="chat-management__actions">
              <button type="button" onClick={() => void submitDraft()} disabled={disabled || !draftName.trim()}>
                Добавить
              </button>
              <button type="button" className="is-secondary" onClick={closeDraft} disabled={disabled}>
                Отмена
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

function AnalyticsTab() {
  const [mode, setMode] = useState<'day' | 'week' | 'month' | 'custom'>('week')
  const [dateFrom, setDateFrom] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() - 7)
    return d.toISOString().slice(0, 10)
  })
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10))
  const [data, setData] = useState<AnalyticsResponse | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    const range = mode === 'custom' ? { date_from: dateFrom, date_to: dateTo } : undefined
    void getAnalytics(mode === 'custom' ? 'custom' : mode, range)
      .then((response) => {
        setData(response)
        setError('')
      })
      .catch((caught) => {
        setError(caught instanceof Error ? caught.message : 'Не удалось загрузить аналитику')
      })
      .finally(() => setLoading(false))
  }, [mode, dateFrom, dateTo])

  const kpis = (data?.kpis ?? {}) as Record<string, string | number | null | undefined>

  return (
    <section className="chat-management__section" aria-labelledby="analytics-heading">
      <div className="chat-management__toolbar">
        <h2 id="analytics-heading">Оперативная аналитика</h2>
        <label>
          Период
          <select
            value={mode}
            onChange={(event) => setMode(event.target.value as typeof mode)}
          >
            <option value="day">1 день</option>
            <option value="week">7 дней</option>
            <option value="month">30 дней</option>
            <option value="custom">Произвольные даты</option>
          </select>
        </label>
        {mode === 'custom' ? (
          <>
            <label>
              С
              <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
            </label>
            <label>
              По
              <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
            </label>
          </>
        ) : null}
      </div>
      {error && <p className="chat-management__error" role="alert">{error}</p>}
      {loading && <p className="chat-management__muted">Загрузка…</p>}
      <div className="chat-management__grid">
        {[
          ['Диалоги', kpis.dialogs ?? 0],
          ['Закрыто', kpis.closed ?? 0],
          ['В очереди', kpis.waiting ?? 0],
          ['Доля закрытых, %', kpis.resolution_rate ?? '—'],
          ['Среднее время первого ответа, сек', kpis.average_first_response_seconds ?? '—'],
          ['Оценка клиентов (CSAT)', kpis.average_rating == null ? '—' : Number(kpis.average_rating).toFixed(2)],
        ].map(([label, value]) => (
          <article className="chat-management__card chat-management__kpi" key={String(label)}>
            <span>{label}</span>
            <strong>{String(value)}</strong>
          </article>
        ))}
      </div>
    </section>
  )
}

function SlaTab({ disabled, perform }: TabProps) {
  const [seconds, setSeconds] = useState(120)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    void getSlaSettings()
      .then((settings) => {
        setSeconds(settings.first_response_seconds)
        setLoaded(true)
        setError('')
      })
      .catch((caught) => {
        setError(caught instanceof Error ? caught.message : 'Не удалось загрузить SLA')
        setLoaded(true)
      })
  }, [])

  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60

  return (
    <section className="chat-management__card" aria-labelledby="sla-heading">
      <h2 id="sla-heading">Целевой SLA первого ответа</h2>
      {error && <p className="chat-management__error" role="alert">{error}</p>}
      {!loaded ? (
        <p className="chat-management__muted">Загрузка…</p>
      ) : (
        <div className="chat-management__form-grid">
          <label>
            Цель, секунды
            <input
              type="number"
              min={15}
              max={3600}
              step={5}
              value={seconds}
              disabled={disabled}
              onChange={(event) => setSeconds(event.target.valueAsNumber || 15)}
            />
          </label>
          <div className="chat-management__muted" style={{ alignSelf: 'end', paddingBottom: 10 }}>
            Сейчас: <strong>{seconds} с</strong>
            {minutes > 0 ? ` (${minutes} мин${rest ? ` ${rest} с` : ''})` : ''}
          </div>
        </div>
      )}
      <div className="chat-management__actions" style={{ marginTop: 14 }}>
        <button
          type="button"
          disabled={disabled || !loaded}
          onClick={() => void perform(
            () => updateSlaSettings(seconds),
            `Целевой SLA обновлён: ${seconds} с.`,
            {
              title: 'Сохранить целевой SLA?',
              description: `Первый ответ оператора будет считаться в норме, если уложится в ${seconds} секунд.`,
            },
          )}
        >
          Сохранить SLA
        </button>
        {[60, 120, 180, 300].map((preset) => (
          <button
            key={preset}
            type="button"
            className="is-secondary"
            disabled={disabled}
            onClick={() => setSeconds(preset)}
          >
            {preset} с
          </button>
        ))}
      </div>
    </section>
  )
}

const WEEKDAY_LABELS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
const MONTH_LABELS = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
]

function pad2(value: number): string {
  return String(value).padStart(2, '0')
}

function toIsoDate(year: number, monthIndex: number, day: number): string {
  return `${year}-${pad2(monthIndex + 1)}-${pad2(day)}`
}

function parseIsoDate(value: string): Date {
  const [y, m, d] = value.split('-').map(Number)
  return new Date(y, m - 1, d)
}

function WorkScheduleTab({ disabled, perform }: TabProps) {
  const today = new Date()
  const enabled = true
  const [defaultStart, setDefaultStart] = useState('09:00')
  const [defaultEnd, setDefaultEnd] = useState('18:00')
  const [workdays, setWorkdays] = useState<number[]>([0, 1, 2, 3, 4])
  const [dayOverrides, setDayOverrides] = useState<Record<string, WorkDayOverride>>({})
  const [holidays, setHolidays] = useState<string[]>([])
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [viewYear, setViewYear] = useState(today.getFullYear())
  const [viewMonth, setViewMonth] = useState(today.getMonth())
  const [selectedDate, setSelectedDate] = useState(toIsoDate(today.getFullYear(), today.getMonth(), today.getDate()))

  useEffect(() => {
    void getWorkScheduleSettings()
      .then((settings) => {
        setDefaultStart(settings.start_time || '09:00')
        setDefaultEnd(settings.end_time || '18:00')
        setWorkdays(settings.workdays?.length ? settings.workdays : [0, 1, 2, 3, 4])
        setDayOverrides(settings.day_overrides ?? {})
        setHolidays(settings.holidays ?? [])
        setLoaded(true)
        setError('')
      })
      .catch((caught) => {
        setError(caught instanceof Error ? caught.message : 'Не удалось загрузить календарь')
        setLoaded(true)
      })
  }, [])

  const resolveDay = (iso: string) => {
    const date = parseIsoDate(iso)
    const override = dayOverrides[iso]
    // JS getDay: Sun=0…Sat=6; backend weekday: Mon=0…Sun=6
    const weekday = (date.getDay() + 6) % 7
    const isDefaultWork = workdays.includes(weekday) && !holidays.includes(iso)
    if (override) {
      return {
        isWorkday: !!override.is_workday,
        start: override.start_time || defaultStart,
        end: override.end_time || defaultEnd,
        hasOverride: true,
      }
    }
    return {
      isWorkday: isDefaultWork,
      start: defaultStart,
      end: defaultEnd,
      hasOverride: false,
    }
  }

  const selected = resolveDay(selectedDate)

  const monthCells = (() => {
    const first = new Date(viewYear, viewMonth, 1)
    const startPad = (first.getDay() + 6) % 7
    const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate()
    const cells: Array<{ iso: string; day: number; inMonth: boolean } | null> = []
    for (let i = 0; i < startPad; i += 1) cells.push(null)
    for (let day = 1; day <= daysInMonth; day += 1) {
      cells.push({
        iso: toIsoDate(viewYear, viewMonth, day),
        day,
        inMonth: true,
      })
    }
    while (cells.length % 7 !== 0) cells.push(null)
    return cells
  })()

  const shiftMonth = (delta: number) => {
    const next = new Date(viewYear, viewMonth + delta, 1)
    setViewYear(next.getFullYear())
    setViewMonth(next.getMonth())
  }

  const applySelectedDay = (patch: Partial<WorkDayOverride> & { is_workday?: boolean }) => {
    setDayOverrides((prev) => {
      const next = { ...prev }
      const current = resolveDay(selectedDate)
      next[selectedDate] = {
        is_workday: patch.is_workday ?? current.isWorkday,
        start_time: patch.start_time ?? current.start,
        end_time: patch.end_time ?? current.end,
      }
      return next
    })
  }

  const clearSelectedOverride = () => {
    setDayOverrides((prev) => {
      const next = { ...prev }
      delete next[selectedDate]
      return next
    })
  }

  return (
    <section className="chat-management__card" aria-labelledby="schedule-heading">
      <h2 id="schedule-heading">Рабочий календарь онлайн-чата</h2>
      {error && <p className="chat-management__error" role="alert">{error}</p>}
      {!loaded ? (
        <p className="chat-management__muted">Загрузка…</p>
      ) : (
        <>
          <div
            style={{
              border: '1px solid #d8dee6',
              borderRadius: 12,
              padding: 14,
              marginBottom: 14,
              background: '#f8fafc',
            }}
          >
            <div className="chat-management__form-grid">
              <label>
                Время по умолчанию (начало)
                <input
                  type="time"
                  value={defaultStart}
                  disabled={disabled}
                  onChange={(event) => setDefaultStart(event.target.value)}
                />
              </label>
              <label>
                Время по умолчанию (конец)
                <input
                  type="time"
                  value={defaultEnd}
                  disabled={disabled}
                  onChange={(event) => setDefaultEnd(event.target.value)}
                />
              </label>
            </div>
            <p className="chat-management__muted" style={{ marginTop: 8, marginBottom: 0 }}>
              Выбранный день: <strong>{selectedDate}</strong>
              {selected.hasOverride ? ' · есть перенос' : ' · по шаблону 5/2'}
            </p>
            <div className="chat-management__actions" style={{ marginTop: 10 }}>
              <button
                type="button"
                disabled={disabled}
                className={selected.isWorkday ? undefined : 'is-secondary'}
                onClick={() => applySelectedDay({ is_workday: true })}
              >
                Рабочий
              </button>
              <button
                type="button"
                disabled={disabled}
                className={!selected.isWorkday ? undefined : 'is-secondary'}
                onClick={() => applySelectedDay({ is_workday: false })}
              >
                Выходной
              </button>
              {selected.hasOverride ? (
                <button type="button" className="is-secondary" disabled={disabled} onClick={clearSelectedOverride}>
                  Сбросить на шаблон
                </button>
              ) : null}
            </div>
            {selected.isWorkday ? (
              <div className="chat-management__form-grid" style={{ marginTop: 10 }}>
                <label>
                  Начало
                  <input
                    type="time"
                    value={selected.start}
                    disabled={disabled}
                    onChange={(event) => applySelectedDay({ start_time: event.target.value, is_workday: true })}
                  />
                </label>
                <label>
                  Конец
                  <input
                    type="time"
                    value={selected.end}
                    disabled={disabled}
                    onChange={(event) => applySelectedDay({ end_time: event.target.value, is_workday: true })}
                  />
                </label>
              </div>
            ) : (
              <p className="chat-management__muted" style={{ marginTop: 10 }}>
                В этот день линия закрыта — диалоги копятся в офлайн-очереди.
              </p>
            )}
          </div>

          <div
            style={{
              border: '1px solid #d8dee6',
              borderRadius: 12,
              padding: 14,
            }}
          >
            <div className="chat-management__actions" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
              <button type="button" className="is-secondary" disabled={disabled} onClick={() => shiftMonth(-1)}>
                ←
              </button>
              <strong>
                {MONTH_LABELS[viewMonth]} {viewYear}
              </strong>
              <button type="button" className="is-secondary" disabled={disabled} onClick={() => shiftMonth(1)}>
                →
              </button>
            </div>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(7, 1fr)',
                gap: 6,
                marginBottom: 6,
              }}
            >
              {WEEKDAY_LABELS.map((label) => (
                <div key={label} className="chat-management__muted" style={{ textAlign: 'center', fontSize: 12 }}>
                  {label}
                </div>
              ))}
            </div>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(7, 1fr)',
                gap: 6,
              }}
            >
              {monthCells.map((cell, index) => {
                if (!cell) {
                  return <div key={`empty-${index}`} />
                }
                const plan = resolveDay(cell.iso)
                const isSelected = cell.iso === selectedDate
                return (
                  <button
                    key={cell.iso}
                    type="button"
                    disabled={disabled}
                    onClick={() => setSelectedDate(cell.iso)}
                    style={{
                      minHeight: 54,
                      borderRadius: 10,
                      border: isSelected ? '2px solid #1d4ed8' : '1px solid #e2e8f0',
                      background: plan.isWorkday ? '#ecfdf5' : '#f8fafc',
                      color: plan.isWorkday ? '#065f46' : '#64748b',
                      cursor: 'pointer',
                      fontFamily: 'inherit',
                      padding: '6px 4px',
                    }}
                  >
                    <div style={{ fontWeight: 700 }}>{cell.day}</div>
                    <div style={{ fontSize: 10, marginTop: 2 }}>
                      {plan.isWorkday ? `${plan.start}–${plan.end}` : 'вых.'}
                    </div>
                  </button>
                )
              })}
            </div>
          </div>
        </>
      )}
      <div className="chat-management__actions" style={{ marginTop: 14 }}>
        <button
          type="button"
          disabled={disabled || !loaded}
          onClick={() => void perform(
            async () => {
              const saved = await updateWorkScheduleSettings({
                enabled,
                start_time: defaultStart,
                end_time: defaultEnd,
                workdays,
                holidays,
                day_overrides: dayOverrides,
                manual_override: 'auto',
              })
              setDayOverrides(saved.day_overrides ?? {})
            },
            'Рабочий календарь сохранён.',
            {
              title: 'Сохранить календарь?',
              description: `Шаблон ${defaultStart}–${defaultEnd}, переносов: ${Object.keys(dayOverrides).length}.`,
            },
          )}
        >
          Сохранить календарь
        </button>
      </div>
    </section>
  )
}

interface TabProps {
  disabled: boolean
  perform: PerformFn
}

function OperatorsTab({
  items,
  departments,
  disabled,
  perform,
}: TabProps & { items: ChatOperator[]; departments: Department[] }) {
  const [fullName, setFullName] = useState('')
  const [username, setUsername] = useState('')
  const [departmentId, setDepartmentId] = useState('')
  const [capacity, setCapacity] = useState(5)
  const [skillTags, setSkillTags] = useState('')
  const [photoUrl, setPhotoUrl] = useState('')
  const [adPending, setAdPending] = useState<Awaited<ReturnType<typeof getAdPendingOperators>>['items']>([])

  useEffect(() => {
    void getAdPendingOperators()
      .then((response) => setAdPending(response.items ?? []))
      .catch(() => setAdPending([]))
  }, [items])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const name = formatOperatorFio(fullName)
    if (!name) return
    await perform(
      async () => {
        await operatorsApi.create({
          name,
          username,
          department_id: departmentId || null,
          capacity,
          presence: 'offline',
          is_active: true,
          photo_url: photoUrl.trim() || undefined,
          skill_tags: skillTags
            .split(',')
            .map((tag) => tag.trim())
            .filter(Boolean),
        })
        setFullName('')
        setUsername('')
        setSkillTags('')
        setPhotoUrl('')
      },
      'Оператор создан.',
      {
        title: 'Создать оператора?',
        description: `Будет создан оператор «${name}» с лимитом ${capacity} диалогов.`,
      },
    )
  }

  return (
    <div className="chat-management__split">
      <form className="chat-management__card" onSubmit={(event) => void submit(event)}>
        <h2>Новый оператор</h2>
        <div className="chat-management__form-grid">
          <label className="is-wide">
            ФИО
            <input
              required
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
            />
          </label>
          <label>Логин<input required value={username} onChange={(event) => setUsername(event.target.value)} /></label>
          <label>
            Отдел
            <select value={departmentId} onChange={(event) => setDepartmentId(event.target.value)}>
              <option value="">Без отдела</option>
              {departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label>
            Лимит диалогов
            <input type="number" min="1" max="50" value={capacity} onChange={(event) => setCapacity(event.target.valueAsNumber)} />
          </label>
          <label className="is-wide">
            Навыки / каналы (через запятую)
            <input
              value={skillTags}
              placeholder="мессенджеры, сайт, соцсети"
              onChange={(event) => setSkillTags(event.target.value)}
            />
          </label>
          <label className="is-wide">
            Фото аватара
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 6 }}>
              <OperatorAvatarPreview url={photoUrl} name={fullName || 'Новый'} />
              <input
                type="file"
                accept="image/*"
                disabled={disabled}
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  if (!file) return
                  const reader = new FileReader()
                  reader.onload = () => setPhotoUrl(String(reader.result || ''))
                  reader.readAsDataURL(file)
                }}
              />
            </div>
          </label>
        </div>
        <div className="chat-management__actions">
          <button disabled={disabled}>Создать оператора</button>
        </div>
      </form>
      <section className="chat-management__card" aria-labelledby="operators-admin-heading">
        <div className="chat-management__toolbar">
          <h2 id="operators-admin-heading">Операторы</h2>
          {SHOW_AD_DEMO ? (
            <button
              type="button"
              className="is-secondary"
              onClick={() => setAdPending((prev) => [makeDemoAdEmployee(), ...prev])}
              title="Демо: имитировать появление нового сотрудника в Active Directory"
            >
              Симулировать сотрудника из AD
            </button>
          ) : null}
        </div>
        {adPending.length ? (
          <div className="chat-management__ad-pending" aria-label="Новые операторы из Active Directory">
            <header>
              <strong>Новые из Active Directory</strong>
              <span className="chat-management__pill is-warn">{adPending.length}</span>
            </header>
            <p className="chat-management__muted">
              Пользователи с ролью КЦ появились в AD. Назначьте лимит диалогов, фото и навыки, затем создайте оператора.
            </p>
            <ul className="chat-management__ad-list">
              {adPending.map((item) => (
                <li key={item.external_id} className="chat-management__ad-card">
                  <OperatorAvatarPreview url="" name={item.display_name} />
                  <div>
                    <strong>{item.display_name}</strong>
                    <div className="chat-management__muted">{item.email}</div>
                    <div>
                      <span className="chat-management__pill">{adRoleLabel(item.ad_role)}</span>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="is-secondary"
                    disabled={disabled}
                    onClick={() => {
                      setFullName(item.display_name)
                      setUsername(item.email.split('@')[0] || item.external_id)
                    }}
                  >
                    Заполнить форму
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <div className="chat-management__table-wrap">
          <table>
            <thead><tr><th>Фото</th><th>ФИО</th><th>Отдел</th><th>Навыки</th><th>Статус</th><th>Лимит</th><th>Активен</th></tr></thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>
                    <label className="chat-management__avatar-upload" title="Загрузить фото">
                      <OperatorAvatarPreview url={item.photo_url || ''} name={item.name} />
                      <input
                        type="file"
                        accept="image/*"
                        disabled={disabled}
                        aria-label={`Загрузить фото ${item.name}`}
                        onChange={(event) => {
                          const file = event.target.files?.[0]
                          if (!file) return
                          const reader = new FileReader()
                          reader.onload = () => {
                            const next = String(reader.result || '')
                            void perform(
                              () => operatorsApi.update(item.id, { photo_url: next }),
                              `Фото ${item.name} обновлено.`,
                            )
                          }
                          reader.readAsDataURL(file)
                        }}
                      />
                    </label>
                  </td>
                  <td>
                    <strong>{item.name}</strong>
                  </td>
                  <td>{item.department_name ?? departmentName(item.department_id ?? item.department, departments)}</td>
                  <td>
                    <input
                      aria-label={`Навыки ${item.name}`}
                      defaultValue={(item.skill_tags ?? []).join(', ')}
                      key={`${item.id}-skills-${(item.skill_tags ?? []).join(',')}`}
                      placeholder="мессенджеры, сайт"
                      onBlur={(event) => {
                        const next = event.target.value
                          .split(',')
                          .map((tag) => tag.trim())
                          .filter(Boolean)
                        const prev = item.skill_tags ?? []
                        if (next.join('|') === prev.join('|')) return
                        void perform(
                          () => operatorsApi.update(item.id, { skill_tags: next }),
                          `Навыки ${item.name} обновлены.`,
                          {
                            title: 'Изменить навыки / каналы?',
                            description: `Для «${item.name}»: ${next.join(', ') || 'без тегов'}.`,
                          },
                        )
                        event.target.value = prev.join(', ')
                      }}
                    />
                  </td>
                  <td>
                    <select
                      aria-label={`Присутствие ${item.name}`}
                      value={presenceToUi(item.presence)}
                      disabled={disabled}
                      onChange={(event) => {
                        const nextUi = event.target.value
                        const label = ARM_PRESENCE_OPTIONS.find((option) => option.ui === nextUi)?.label ?? nextUi
                        void perform(
                          () => operatorsApi.setPresence(item.id, presenceToApi(nextUi)),
                          `Статус ${item.name} обновлён.`,
                          {
                            title: 'Изменить статус оператора?',
                            description: `Установить для «${item.name}» статус «${label}»?`,
                          },
                        )
                        event.target.value = presenceToUi(item.presence)
                      }}
                    >
                      {ARM_PRESENCE_OPTIONS.map((option) => (
                        <option key={option.ui} value={option.ui}>{option.label}</option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <input
                      aria-label={`Лимит диалогов ${item.name}`}
                      type="number"
                      min="1"
                      max="50"
                      defaultValue={item.capacity}
                      key={`${item.id}-${item.capacity}`}
                      onBlur={(event) => {
                        const next = event.target.valueAsNumber
                        if (Number.isNaN(next) || next === item.capacity) return
                        void perform(
                          () => operatorsApi.update(item.id, { capacity: next }),
                          `Лимит ${item.name} обновлён.`,
                          {
                            title: 'Изменить лимит диалогов?',
                            description: `Для «${item.name}» лимит будет изменён с ${item.capacity} на ${next}.`,
                          },
                        )
                        event.target.value = String(item.capacity)
                      }}
                    />
                  </td>
                  <td>
                    <label className="chat-management__active-check">
                      <input
                        aria-label={`Оператор ${item.name} активен`}
                        type="checkbox"
                        checked={item.is_active !== false}
                        disabled={disabled}
                        onChange={() => void perform(
                          () => operatorsApi.update(item.id, { is_active: item.is_active === false }),
                          `Доступность ${item.name} обновлена.`,
                          {
                            title: item.is_active === false ? 'Активировать оператора?' : 'Деактивировать оператора?',
                            description: item.is_active === false
                              ? `Оператор «${item.name}» снова сможет получать диалоги.`
                              : `Оператор «${item.name}» будет недоступен для назначения.`,
                          },
                        )}
                      />
                    </label>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!items.length && <div className="chat-management__empty">Операторов пока нет.</div>}
        </div>
      </section>
    </div>
  )
}

function DepartmentsTab({ items, disabled, perform }: TabProps & { items: Department[] }) {
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [description, setDescription] = useState('')

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    await perform(
      async () => {
        await departmentsApi.create({
          name,
          code: code.trim() || slugHint(name),
          description,
          is_active: true,
        })
        setName('')
        setCode('')
        setDescription('')
      },
      'Отдел создан.',
      {
        title: 'Создать отдел?',
        description: `Будет создан отдел «${name}».`,
      },
    )
  }

  return (
    <div className="chat-management__split">
      <form className="chat-management__card" onSubmit={(event) => void submit(event)}>
        <h2>Новый отдел</h2>
        <div className="chat-management__form-grid">
          <label>Название<input required value={name} onChange={(event) => setName(event.target.value)} /></label>
          <label>
            Код
            <input
              value={code}
              placeholder="авто, если пусто"
              onChange={(event) => setCode(event.target.value)}
            />
          </label>
          <label className="is-wide">Описание<textarea value={description} onChange={(event) => setDescription(event.target.value)} /></label>
        </div>
        <div className="chat-management__actions">
          <button disabled={disabled}>Создать отдел</button>
        </div>
      </form>
      <section className="chat-management__card">
        <h2>Отделы</h2>
        <ul className="chat-management__list">
          {items.map((item) => (
            <li className="chat-management__list-item" key={item.id}>
              <header><div><strong>{item.name}</strong> <small>{item.code}</small></div></header>
              <p className="chat-management__muted">{item.description || 'Без описания'}</p>
              <div className="chat-management__actions">
                <button
                  className="is-secondary"
                  disabled={disabled}
                  onClick={() => {
                    const next = window.prompt('Новое название отдела', item.name)?.trim()
                    if (next && next !== item.name) {
                      void perform(
                        () => departmentsApi.update(item.id, { name: next }),
                        'Отдел обновлён.',
                        {
                          title: 'Переименовать отдел?',
                          description: `«${item.name}» → «${next}».`,
                        },
                      )
                    }
                  }}
                >
                  Переименовать
                </button>
                <button
                  className="is-danger"
                  disabled={disabled}
                  onClick={() => void perform(
                    () => departmentsApi.remove(item.id),
                    'Отдел удалён.',
                    {
                      title: 'Удалить отдел?',
                      description: `Отдел «${item.name}» будет удалён.`,
                    },
                  )}
                >
                  Удалить
                </button>
              </div>
            </li>
          ))}
        </ul>
        {!items.length && <div className="chat-management__empty">Отделов пока нет.</div>}
      </section>
    </div>
  )
}

function FormFieldsPicker({
  value,
  onChange,
  allowReorder = false,
}: {
  value: WidgetFormField[]
  onChange: (fields: WidgetFormField[]) => void
  /** Messenger channels: drag to set ask order. Widget: selection only. */
  allowReorder?: boolean
}) {
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null)
  const selectedKeys = new Set(value.map((field) => field.key))
  const togglePopular = (field: WidgetFormField) => {
    if (selectedKeys.has(field.key)) {
      onChange(value.filter((item) => item.key !== field.key))
      return
    }
    onChange([...value, { ...field }])
  }
  const setRequired = (key: string, required: boolean) => {
    onChange(value.map((item) => (item.key === key ? { ...item, required } : item)))
  }
  const removeField = (key: string) => {
    onChange(value.filter((item) => item.key !== key))
  }
  const reorderTo = (from: number, to: number) => {
    if (from === to || from < 0 || to < 0 || from >= value.length || to >= value.length) return
    const next = [...value]
    const [item] = next.splice(from, 1)
    next.splice(to, 0, item)
    onChange(next)
  }

  return (
    <div className="chat-management__field-picker is-wide">
      <div className="chat-management__field-picker-head">
        <strong>Поля формы</strong>
      </div>

      <div className="chat-management__field-grid" role="group" aria-label="Доступные поля">
        {POPULAR_FORM_FIELDS.map((field) => {
          const checked = selectedKeys.has(field.key)
          return (
            <label
              key={field.key}
              className={`chat-management__field-option${checked ? ' is-checked' : ''}`}
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={() => togglePopular(field)}
              />
              <span>{field.label}</span>
            </label>
          )
        })}
      </div>

      <div className="chat-management__field-selected">
        <div className="chat-management__field-selected-title">
          Выбранные поля
          <span>{value.length}</span>
        </div>
        {value.length ? (
          <ul className="chat-management__selected-fields">
            {value.map((field, index) => (
              <li
                key={field.key}
                className={[
                  allowReorder ? 'is-sortable' : '',
                  dragIndex === index ? 'is-dragging' : '',
                  dragOverIndex === index && dragIndex !== index ? 'is-drag-over' : '',
                ].filter(Boolean).join(' ')}
                draggable={allowReorder}
                onDragStart={(event) => {
                  if (!allowReorder) return
                  setDragIndex(index)
                  event.dataTransfer.effectAllowed = 'move'
                  event.dataTransfer.setData('text/plain', String(index))
                }}
                onDragOver={(event) => {
                  if (!allowReorder || dragIndex === null) return
                  event.preventDefault()
                  event.dataTransfer.dropEffect = 'move'
                  if (dragOverIndex !== index) setDragOverIndex(index)
                }}
                onDragLeave={() => {
                  if (dragOverIndex === index) setDragOverIndex(null)
                }}
                onDrop={(event) => {
                  if (!allowReorder) return
                  event.preventDefault()
                  const from = dragIndex ?? Number(event.dataTransfer.getData('text/plain'))
                  reorderTo(from, index)
                  setDragIndex(null)
                  setDragOverIndex(null)
                }}
                onDragEnd={() => {
                  setDragIndex(null)
                  setDragOverIndex(null)
                }}
              >
                {allowReorder ? (
                  <span className="chat-management__selected-fields-index" aria-hidden>
                    {index + 1}
                  </span>
                ) : null}
                <span
                  className="chat-management__selected-fields-label"
                  title={allowReorder ? 'Перетащите, чтобы изменить порядок' : undefined}
                >
                  {allowReorder ? (
                    <span className="chat-management__selected-fields-grip" aria-hidden>⠿</span>
                  ) : null}
                  {field.label}
                </span>
                <label className="chat-management__required-toggle">
                  <input
                    type="checkbox"
                    checked={Boolean(field.required)}
                    onChange={(event) => setRequired(field.key, event.target.checked)}
                  />
                  <span>Обязательное</span>
                </label>
                <button
                  type="button"
                  className="chat-management__icon-x"
                  aria-label={`Удалить поле «${field.label}»`}
                  onClick={() => removeField(field.key)}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="chat-management__field-empty">Пока ничего не выбрано</p>
        )}
      </div>
    </div>
  )
}

function PlacementsTab({
  items,
  departments,
  disabled,
  perform,
}: TabProps & { items: WidgetPlacement[]; departments: Department[] }) {
  const [editingId, setEditingId] = useState<EntityId | null>(null)
  const [form, setForm] = useState<Partial<WidgetPlacement>>(emptyPlacement)
  const [domains, setDomains] = useState('')

  const edit = (item: WidgetPlacement) => {
    setEditingId(item.id)
    setForm(item)
    setDomains((item.allowed_domains ?? []).join(', '))
  }
  const reset = () => {
    setEditingId(null)
    setForm(emptyPlacement)
    setDomains('')
  }
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const payload: Partial<WidgetPlacement> = {
      ...form,
      code: (form.code || '').trim() || slugHint(form.name || 'widget'),
      allowed_domains: domains.split(',').map((value) => value.trim()).filter(Boolean),
    }
    await perform(
      async () => {
        if (editingId == null) await placementsApi.create(payload)
        else await placementsApi.update(editingId, payload)
        reset()
      },
      editingId == null ? 'Виджет создан.' : 'Виджет обновлён.',
      {
        title: editingId == null ? 'Создать виджет?' : 'Сохранить виджет?',
        description: editingId == null
          ? `Будет создан виджет «${form.name || ''}». Поля формы настраиваются в «Каналы платформы».`
          : `Изменения виджета «${form.name || ''}» будут сохранены.`,
      },
    )
  }
  const set = <K extends keyof WidgetPlacement>(key: K, value: WidgetPlacement[K]) =>
    setForm((current) => ({ ...current, [key]: value }))

  return (
    <div className="chat-management__split">
      <form className="chat-management__card" onSubmit={(event) => void submit(event)}>
        <h2>{editingId == null ? 'Новый виджет' : 'Редактирование виджета'}</h2>
        <div className="chat-management__form-grid">
          <label>Название<input required value={form.name ?? ''} onChange={(event) => set('name', event.target.value)} /></label>
          <label>
            Код (widget_id)
            <input
              value={form.code ?? ''}
              placeholder="авто, если пусто"
              onChange={(event) => set('code', event.target.value)}
            />
          </label>
          <label className="is-wide">
            Разрешённые домены (через запятую)
            <input placeholder="example.by, bank.example.by" value={domains} onChange={(event) => setDomains(event.target.value)} />
          </label>
          <label>
            Отдел
            <select value={entityDepartmentId(form)} onChange={(event) => set('department_id', event.target.value || null)}>
              <option value="">Общий</option>
              {departments.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label>
            Акцент темы
            <input type="color" value={form.theme_accent ?? '#007A43'} onChange={(event) => set('theme_accent', event.target.value)} />
          </label>
          <label className="chat-management__check">
            <input type="checkbox" checked={form.is_active !== false} onChange={(event) => set('is_active', event.target.checked)} />
            Виджет активен
          </label>
          <label className="is-wide">
            Приветствие
            <textarea
              value={form.welcome_message ?? ''}
              onChange={(event) => set('welcome_message', event.target.value)}
              rows={2}
            />
          </label>
          <p className="chat-management__muted is-wide" style={{ margin: '4px 0 0' }}>
            Сообщение вне графика настраивается в разделе «Базовые сообщения».
          </p>
        </div>
        <div className="chat-management__actions">
          <button disabled={disabled}>{editingId == null ? 'Создать' : 'Сохранить'}</button>
          {editingId != null && <button type="button" className="is-secondary" onClick={reset}>Отмена</button>}
        </div>
        {(form.name || editingId != null) ? (
          <div
            className="chat-management__widget-preview"
            style={{
              marginTop: 16,
              border: '1px solid #d7e0d9',
              borderRadius: 12,
              overflow: 'hidden',
              background: '#f4f7f5',
            }}
          >
            <div style={{ padding: '10px 12px', background: form.theme_accent || '#007A43', color: '#fff', fontWeight: 600 }}>
              Чат банка · превью
            </div>
            <div style={{ padding: 12, display: 'grid', gap: 8 }}>
              <p style={{ margin: 0, fontSize: 13, color: '#334' }}>
                {(form.welcome_message || 'Здравствуйте! Оставьте контакты — оператор подключится.').slice(0, 160)}
              </p>
              {(form.form_fields?.length ? form.form_fields : POPULAR_FORM_FIELDS.slice(0, 3)).map((field) => (
                <label key={field.key} style={{ display: 'grid', gap: 4, fontSize: 12 }}>
                  {field.label}{field.required ? ' *' : ''}
                  <input disabled placeholder={field.type === 'tel' ? '+375 …' : ''} style={{ padding: 8, borderRadius: 6, border: '1px solid #c9d4cc' }} />
                </label>
              ))}
              <button type="button" disabled style={{ padding: '8px 12px', borderRadius: 8, background: form.theme_accent || '#007A43', color: '#fff', border: 0 }}>
                Начать диалог
              </button>
            </div>
          </div>
        ) : null}
      </form>
      <section className="chat-management__card">
        <h2>Виджеты</h2>
        <ul className="chat-management__list">
          {items.map((item) => (
            <li className="chat-management__list-item" key={item.id}>
              <header>
                <div><strong>{item.name}</strong> <span className="chat-management__pill">{item.code}</span></div>
                <span className={`chat-management__pill ${item.is_active === false ? 'is-error' : 'is-success'}`}>
                  {item.is_active === false ? 'выключено' : 'активно'}
                </span>
              </header>
              <p className="chat-management__muted">{(item.allowed_domains ?? []).join(', ') || 'Все домены'}</p>
              <div className="chat-management__actions">
                <button className="is-secondary" onClick={() => edit(item)}>Изменить</button>
                <button
                  className="is-secondary"
                  type="button"
                  onClick={() => {
                    const snippet = `<script src="/widget/widget.js" data-widget-id="${item.code ?? item.id}" data-placement="website" defer></script>`
                    void navigator.clipboard?.writeText(snippet)
                    window.alert(`Код встраивания скопирован:\n\n${snippet}`)
                  }}
                >
                  Код
                </button>
                <button
                  className="is-danger"
                  disabled={disabled}
                  onClick={() => void perform(
                    () => placementsApi.remove(item.id),
                    'Виджет удалён.',
                    {
                      title: 'Удалить виджет?',
                      description: `Виджет «${item.name}» будет удалён.`,
                    },
                  )}
                >
                  Удалить
                </button>
              </div>
            </li>
          ))}
        </ul>
        {!items.length && <div className="chat-management__empty">Виджетов пока нет.</div>}
      </section>
    </div>
  )
}

function healthLabel(status?: string): { text: string; tone: string } {
  switch (status) {
    case 'ok':
      return { text: 'соединение ок', tone: 'is-success' }
    case 'not_configured':
      return { text: 'не настроен', tone: 'is-warn' }
    case 'error':
      return { text: 'ошибка', tone: 'is-error' }
    default:
      return { text: 'не проверен', tone: '' }
  }
}

function ChannelsTab({
  items,
  placements,
  disabled,
  perform,
}: TabProps & { items: ChatChannel[]; placements: WidgetPlacement[] }) {
  const [formTarget, setFormTarget] = useState<{
    kind: 'channel' | 'placement'
    id: EntityId
    name: string
    fields: WidgetFormField[]
    allowReorder: boolean
  } | null>(null)

  const messengerRows = CANONICAL_CHANNELS.filter((item) => item.kind !== 'widget').map((canonical) => {
    const existing = items.find((item) => (item.kind ?? item.channel ?? '') === canonical.kind)
    return { ...canonical, existing }
  })
  const widgetChannel = items.find((item) => (item.kind ?? item.channel ?? '') === 'widget')

  const openChannelForm = (channel: ChatChannel) => {
    const channelKind = String(channel.kind ?? channel.channel ?? '')
    const cleaned = sanitizeFormFields(channel.form_fields)
    setFormTarget({
      kind: 'channel',
      id: channel.id,
      name: channel.name.replace(/\s*\(demo\)/gi, ''),
      fields: cleaned,
      allowReorder: channelKind !== 'widget',
    })
  }
  const openPlacementForm = (placement: WidgetPlacement) => {
    const cleaned = sanitizeFormFields(placement.form_fields)
    setFormTarget({
      kind: 'placement',
      id: placement.id,
      name: `Виджет · ${placement.name.replace(/\s*\(demo\)/gi, '')}`,
      fields: cleaned,
      allowReorder: false,
    })
  }
  const saveFormFields = async () => {
    if (!formTarget) return
    const target = formTarget
    const mapped = sanitizeFormFields(target.fields)
    // Close first so a slow/partial refresh cannot leave the modal stuck open.
    setFormTarget(null)
    const ok = await perform(async () => {
      if (target.kind === 'channel') {
        // Only form_fields — never rewrite config from the masked list payload.
        await channelsApi.update(target.id, { form_fields: mapped } as Partial<ChatChannel>)
      } else {
        await placementsApi.update(target.id, {
          form_fields: mapped,
          require_phone: mapped.some((field) => field.key === 'phone' && field.required),
        })
      }
    }, `Поля формы для «${target.name}» сохранены.`)
    if (!ok) setFormTarget(target)
  }

  return (
    <>
      <section className="chat-management__card" aria-labelledby="channels-heading">
        <h2 id="channels-heading">Каналы платформы</h2>
        <ul className="chat-management__list chat-management__channel-list">
          {placements.map((placement) => {
            const active = placement.is_active !== false
            const health = healthLabel(widgetChannel?.health_status)
            const counters = placement.counters
            return (
              <li className="chat-management__list-item" key={`placement-${placement.id}`}>
                <header>
                  <div>
                    <strong>Виджет · {placement.name}</strong>
                    <div className="chat-management__muted">{placement.code}</div>
                  </div>
                  <span className={`chat-management__pill chat-management__pill--lg ${active ? 'is-success' : 'is-error'}`}>
                    {active ? 'активен' : 'выключен'}
                  </span>
                </header>
                <div className="chat-management__channel-meta">
                  <span className={`chat-management__pill ${health.tone}`}>{health.text}</span>
                  {widgetChannel?.last_health_check_at ? (
                    <span className="chat-management__muted">
                      проверка: {new Date(widgetChannel.last_health_check_at).toLocaleString('ru-RU')}
                    </span>
                  ) : null}
                </div>
                <dl className="chat-management__channel-counters">
                  <div><dt>В очереди</dt><dd>{counters?.waiting ?? 0}</dd></div>
                  <div><dt>Активные</dt><dd>{counters?.active ?? 0}</dd></div>
                  <div><dt>Сегодня</dt><dd>{counters?.today ?? 0}</dd></div>
                  <div><dt>Закрыто сегодня</dt><dd>{counters?.closed_today ?? 0}</dd></div>
                </dl>
                <div className="chat-management__actions">
                  <button className="is-secondary" disabled={disabled} onClick={() => openPlacementForm(placement)}>
                    Настроить
                  </button>
                  <button
                    className="is-secondary"
                    disabled={disabled}
                    onClick={() => void perform(async () => {
                      const channel = widgetChannel ?? await channelsApi.create({
                        name: 'Виджет сайта',
                        kind: 'widget',
                        is_active: true,
                        account: 'channel-widget',
                      })
                      await channelsApi.checkHealth(channel.id)
                    }, `Проверка виджета «${placement.name}» выполнена.`)}
                  >
                    Проверить соединение
                  </button>
                  <button
                    className={active ? 'is-danger' : 'is-secondary'}
                    disabled={disabled}
                    onClick={() => void perform(
                      () => placementsApi.update(placement.id, { is_active: !active }),
                      active ? `Виджет «${placement.name}» выключен.` : `Виджет «${placement.name}» включён.`,
                    )}
                  >
                    {active ? 'Выключить' : 'Включить'}
                  </button>
                </div>
              </li>
            )
          })}
          {!placements.length && widgetChannel ? (
            <li className="chat-management__list-item">
              <header>
                <div><strong>Виджет сайта</strong></div>
                <span className={`chat-management__pill chat-management__pill--lg ${widgetChannel.is_active ? 'is-success' : 'is-error'}`}>
                  {widgetChannel.is_active ? 'активен' : 'выключен'}
                </span>
              </header>
              <div className="chat-management__actions">
                <button className="is-secondary" disabled={disabled} onClick={() => openChannelForm(widgetChannel)}>
                  Настроить
                </button>
              </div>
            </li>
          ) : null}
          {messengerRows.map((row) => {
            const active = row.existing?.is_active === true
            const health = healthLabel(row.existing?.health_status)
            const counters = row.existing?.counters
            return (
              <li className="chat-management__list-item" key={row.kind}>
                <header>
                  <div>
                    <strong>{row.name}</strong>
                  </div>
                  <span className={`chat-management__pill chat-management__pill--lg ${active ? 'is-success' : 'is-error'}`}>
                    {active ? 'активен' : 'выключен'}
                  </span>
                </header>
                <div className="chat-management__channel-meta">
                  <span className={`chat-management__pill ${health.tone}`}>{health.text}</span>
                  {row.existing?.last_health_check_at ? (
                    <span className="chat-management__muted">
                      проверка: {new Date(row.existing.last_health_check_at).toLocaleString('ru-RU')}
                    </span>
                  ) : null}
                </div>
                <dl className="chat-management__channel-counters">
                  <div>
                    <dt>В очереди</dt>
                    <dd>{counters?.waiting ?? 0}</dd>
                  </div>
                  <div>
                    <dt>Активные</dt>
                    <dd>{counters?.active ?? 0}</dd>
                  </div>
                  <div>
                    <dt>Сегодня</dt>
                    <dd>{counters?.today ?? 0}</dd>
                  </div>
                  <div>
                    <dt>Закрыто сегодня</dt>
                    <dd>{counters?.closed_today ?? 0}</dd>
                  </div>
                </dl>
                <div className="chat-management__actions">
                  <button
                    className="is-secondary"
                    disabled={disabled || !row.existing}
                    onClick={() => row.existing && openChannelForm(row.existing)}
                  >
                    Настроить
                  </button>
                  <button
                    className="is-secondary"
                    disabled={disabled || !row.existing}
                    onClick={() => void perform(async () => {
                      if (!row.existing) return
                      await channelsApi.checkHealth(row.existing.id)
                    }, `Проверка канала «${row.name}» выполнена.`, {
                      title: 'Проверить соединение?',
                      description: `Запустить проверку канала «${row.name}»?`,
                    })}
                  >
                    Проверить соединение
                  </button>
                  <button
                    className={active ? 'is-danger' : 'is-secondary'}
                    disabled={disabled}
                    onClick={() => void perform(async () => {
                      if (row.existing) {
                        await channelsApi.update(row.existing.id, { is_active: !active })
                        return
                      }
                      await channelsApi.create({
                        name: row.name,
                        kind: row.kind,
                        is_active: true,
                        account: `channel-${row.kind}`,
                      })
                    }, active ? `Канал «${row.name}» выключен.` : `Канал «${row.name}» включён.`, {
                      title: active ? 'Выключить канал?' : 'Включить канал?',
                      description: `Канал «${row.name}» будет ${active ? 'выключен' : 'включён'}.`,
                    })}
                  >
                    {active ? 'Выключить' : 'Включить'}
                  </button>
                </div>
              </li>
            )
          })}
        </ul>
      </section>

      {formTarget ? (
        <div className="chat-management__modal-backdrop" role="dialog" aria-modal="true">
          <div className="chat-management__card chat-management__modal">
            <h2>Поля формы · {formTarget.name.replace(/\s*\(demo\)/gi, '')}</h2>
            <FormFieldsPicker
              value={formTarget.fields}
              allowReorder={formTarget.allowReorder}
              onChange={(fields) => setFormTarget((current) => (current ? { ...current, fields } : current))}
            />
            <div className="chat-management__actions">
              <button type="button" className="is-secondary" onClick={() => setFormTarget(null)}>Отмена</button>
              <button type="button" disabled={disabled} onClick={() => void saveFormFields()}>Сохранить</button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}

function RoutingTab({
  items,
  departments,
  channels,
  disabled,
  perform,
}: TabProps & { items: RoutingRule[]; departments: Department[]; channels: ChatChannel[] }) {
  const [name, setName] = useState('')
  const [priority, setPriority] = useState(100)
  const [departmentId, setDepartmentId] = useState('')
  const [channelId, setChannelId] = useState('')
  const [maxLoad, setMaxLoad] = useState(5)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!departmentId) {
      window.alert('Выберите отдел для правила маршрутизации.')
      return
    }
    await perform(
      async () => {
        await routingRulesApi.create({
          name,
          priority,
          department_id: departmentId,
          channel_id: channelId || null,
          max_load: maxLoad,
          is_active: true,
        })
        setName('')
      },
      'Правило создано.',
      {
        title: 'Создать правило?',
        description: `Будет создано правило маршрутизации «${name}».`,
      },
    )
  }

  return (
    <div className="chat-management__split">
      <form className="chat-management__card" onSubmit={(event) => void submit(event)}>
        <h2>Новое правило</h2>
        <div className="chat-management__form-grid">
          <label>Название<input required value={name} onChange={(event) => setName(event.target.value)} /></label>
          <label>Приоритет<input type="number" min="1" value={priority} onChange={(event) => setPriority(event.target.valueAsNumber)} /></label>
          <label>
            Отдел
            <select required value={departmentId} onChange={(event) => setDepartmentId(event.target.value)}>
              <option value="">Выберите отдел</option>
              {departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label>
            Канал
            <select value={channelId} onChange={(event) => setChannelId(event.target.value)}>
              <option value="">Любой</option>
              {channels.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label>
            Максимальная нагрузка
            <input type="number" min="1" max="50" value={maxLoad} onChange={(event) => setMaxLoad(event.target.valueAsNumber)} />
          </label>
        </div>
        <div className="chat-management__actions">
          <button disabled={disabled}>Создать правило</button>
        </div>
      </form>
      <section className="chat-management__card">
        <h2>Правила маршрутизации</h2>
        <ul className="chat-management__list">
          {[...items].sort((a, b) => a.priority - b.priority).map((item) => (
            <li className="chat-management__list-item" key={item.id}>
              <header>
                <div><strong>{item.priority}. {item.name}</strong></div>
                <span className={`chat-management__pill ${item.is_active ? 'is-success' : 'is-error'}`}>
                  {item.is_active ? 'активно' : 'выключено'}
                </span>
              </header>
              <p className="chat-management__muted">
                {departmentName(entityDepartmentId(item), departments)} ·{' '}
                {channels.find((channel) => String(channel.id) === String(item.channel_id ?? item.channel))?.name ?? 'Любой канал'}
                {item.max_load ? ` · лимит ${item.max_load}` : ''}
              </p>
              <div className="chat-management__actions">
                <button
                  className="is-secondary"
                  disabled={disabled}
                  onClick={() => void perform(
                    () => routingRulesApi.update(item.id, { is_active: !item.is_active }),
                    'Правило обновлено.',
                    {
                      title: item.is_active ? 'Выключить правило?' : 'Включить правило?',
                      description: `Правило «${item.name}» будет ${item.is_active ? 'выключено' : 'включено'}.`,
                    },
                  )}
                >
                  {item.is_active ? 'Выключить' : 'Включить'}
                </button>
                <button
                  className="is-danger"
                  disabled={disabled}
                  onClick={() => void perform(
                    () => routingRulesApi.remove(item.id),
                    'Правило удалено.',
                    {
                      title: 'Удалить правило?',
                      description: `Правило «${item.name}» будет удалено.`,
                    },
                  )}
                >
                  Удалить
                </button>
              </div>
            </li>
          ))}
        </ul>
        {!items.length && <div className="chat-management__empty">Правил пока нет.</div>}
      </section>
    </div>
  )
}

type BotTriggerRow = { id: string; trigger: string; response: string }

function BotsTab({
  items,
  disabled,
  perform,
}: TabProps & { items: BotConfiguration[] }) {
  const [name, setName] = useState('')
  const [handoff, setHandoff] = useState('Подключаю оператора. Пожалуйста, ожидайте.')
  const [maxTurns, setMaxTurns] = useState(3)
  const [triggerRows, setTriggerRows] = useState<BotTriggerRow[]>([
    { id: '1', trigger: 'карт', response: 'Уточните, пожалуйста, вопрос по карте.' },
    { id: '2', trigger: 'вклад', response: 'Какой вклад вас интересует?' },
  ])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const triggerResponses = Object.fromEntries(
      triggerRows
        .map((row) => [row.trigger.trim(), row.response.trim()] as const)
        .filter(([trigger, response]) => trigger && response),
    )
    await perform(
      async () => {
        await botsApi.create({
          name,
          is_active: false,
          fallback_message: handoff,
          handoff_message: handoff,
          trigger_responses: triggerResponses,
          max_bot_turns: maxTurns,
        })
        setName('')
      },
      'Бот создан.',
      {
        title: 'Создать бота?',
        description: `Бот «${name}» будет создан выключенным с ${Object.keys(triggerResponses).length} ветками ответов.`,
      },
    )
  }

  return (
    <div className="chat-management__split">
      <form className="chat-management__card" onSubmit={(event) => void submit(event)}>
        <h2>Новый бот первой линии</h2>
        <div className="chat-management__form-grid">
          <label>Название<input required value={name} onChange={(event) => setName(event.target.value)} /></label>
          <label>
            Максимум ходов
            <input type="number" min="1" value={maxTurns} onChange={(event) => setMaxTurns(event.target.valueAsNumber || 1)} />
          </label>
          <label className="is-wide">Передача оператору<textarea value={handoff} onChange={(event) => setHandoff(event.target.value)} /></label>
          <div className="chat-management__field-picker is-wide">
            <div className="chat-management__field-picker-head">
              <strong>Автоответы</strong>
              <span>Ключевые слова и текст ответа бота</span>
            </div>
            <ul className="chat-management__trigger-list">
              {triggerRows.map((row) => (
                <li key={row.id}>
                  <label>
                    Ключ
                    <input
                      value={row.trigger}
                      placeholder="карт"
                      onChange={(event) => setTriggerRows((current) => current.map((item) => (
                        item.id === row.id ? { ...item, trigger: event.target.value } : item
                      )))}
                    />
                  </label>
                  <label>
                    Ответ
                    <input
                      value={row.response}
                      placeholder="Уточните вопрос…"
                      onChange={(event) => setTriggerRows((current) => current.map((item) => (
                        item.id === row.id ? { ...item, response: event.target.value } : item
                      )))}
                    />
                  </label>
                  <button
                    type="button"
                    className="chat-management__icon-x"
                    aria-label="Удалить автоответ"
                    onClick={() => setTriggerRows((current) => current.filter((item) => item.id !== row.id))}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
            <button
              type="button"
              className="is-secondary"
              onClick={() => setTriggerRows((current) => [
                ...current,
                { id: `${Date.now()}`, trigger: '', response: '' },
              ])}
            >
              Добавить ответ
            </button>
          </div>
        </div>
        <p className="chat-management__muted">Новый бот создаётся выключенным. Включите его после проверки сценариев.</p>
        <div className="chat-management__actions">
          <button disabled={disabled}>Создать бота</button>
        </div>
      </form>
      <section className="chat-management__card">
        <h2>Боты</h2>
        <ul className="chat-management__list">
          {items.map((item) => (
            <li className="chat-management__list-item" key={item.id}>
              <header>
                <div><strong>{item.name}</strong></div>
                <span className={`chat-management__pill ${item.is_active ? 'is-success' : 'is-error'}`}>
                  {item.is_active ? 'включён' : 'выключен'}
                </span>
              </header>
              <p className="chat-management__muted">
                Веток: {Object.keys(item.trigger_responses ?? {}).length} · до {item.max_bot_turns} ходов
              </p>
              <div className="chat-management__actions">
                <button
                  className="is-secondary"
                  disabled={disabled}
                  onClick={() => void perform(
                    () => botsApi.update(item.id, { is_active: !item.is_active }),
                    'Статус бота обновлён.',
                    {
                      title: item.is_active ? 'Выключить бота?' : 'Включить бота?',
                      description: `Бот «${item.name}» будет ${item.is_active ? 'выключен' : 'включён'}.`,
                    },
                  )}
                >
                  {item.is_active ? 'Выключить' : 'Включить'}
                </button>
                <button
                  className="is-danger"
                  disabled={disabled}
                  onClick={() => void perform(
                    () => botsApi.remove(item.id),
                    'Бот удалён.',
                    {
                      title: 'Удалить бота?',
                      description: `Бот «${item.name}» будет удалён без возможности восстановления.`,
                    },
                  )}
                >
                  Удалить
                </button>
              </div>
            </li>
          ))}
        </ul>
        {!items.length && <div className="chat-management__empty">Ботов пока нет.</div>}
      </section>
    </div>
  )
}

const SEND_PHASE_OPTIONS = [
  { value: 'before_bot', label: 'До бота' },
  { value: 'after_bot', label: 'После бота / при эскалации' },
  { value: 'mid_dialog', label: 'В середине диалога' },
  { value: 'hold', label: 'Ожидание ответа оператора (hold)' },
  { value: 'offline', label: 'Вне графика' },
] as const

function BaseMessagesTab({
  items,
  placements,
  channels,
  disabled,
  perform,
}: TabProps & {
  items: BaseMessage[]
  placements: WidgetPlacement[]
  channels: ChatChannel[]
}) {
  const [sendPhase, setSendPhase] = useState<BaseMessage['send_phase']>('before_bot')
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [delaySeconds, setDelaySeconds] = useState(0)
  const [selectedChannels, setSelectedChannels] = useState<string[] | null>(null)

  const channelOptions = [
    ...placements.map((placement) => ({
      value: `widget:${placement.id}`,
      label: `Виджет · ${placement.name}`,
    })),
    ...CANONICAL_CHANNELS
      .filter((canonical) => canonical.kind !== 'widget')
      .map((canonical) => ({
        value: canonical.kind,
        label: channels.find(
          (channel) => (channel.kind ?? channel.channel) === canonical.kind,
        )?.name ?? canonical.name,
      })),
  ]
  if (!placements.length && channels.some((channel) => (channel.kind ?? channel.channel) === 'widget')) {
    channelOptions.unshift({ value: 'widget', label: 'Виджет сайта' })
  }
  const selected = selectedChannels ?? channelOptions.map((option) => option.value)
  const allSelected = channelOptions.length > 0 && selected.length === channelOptions.length
  const orderedItems = [...items].sort(
    (left, right) => (left.sort_order ?? 100) - (right.sort_order ?? 100),
  )

  const toggleChannel = (value: string) => {
    setSelectedChannels((current) => {
      const active = current ?? channelOptions.map((option) => option.value)
      return active.includes(value)
        ? active.filter((item) => item !== value)
        : [...active, value]
    })
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!selected.length) {
      window.alert('Выберите хотя бы один канал.')
      return
    }
    await perform(
      async () => {
        await baseMessagesApi.create({
          title: title.trim() || SEND_PHASE_OPTIONS.find((item) => item.value === sendPhase)?.label || '',
          text,
          channels: allSelected ? [] : selected,
          send_phase: sendPhase,
          delay_seconds: delaySeconds,
          sort_order: Math.max(0, ...items.map((item) => item.sort_order ?? 0)) + 10,
          is_active: true,
        })
        setTitle('')
        setText('')
        setDelaySeconds(0)
      },
      'Базовое сообщение создано.',
      {
        title: 'Создать сообщение?',
        description: 'Клиенты выбранного канала получат этот текст без участия оператора (если сообщение активно).',
      },
    )
  }

  const moveMessage = (index: number, delta: -1 | 1) => {
    const targetIndex = index + delta
    if (targetIndex < 0 || targetIndex >= orderedItems.length) return
    const reordered = [...orderedItems]
    ;[reordered[index], reordered[targetIndex]] = [reordered[targetIndex], reordered[index]]
    void perform(
      () => Promise.all(reordered.map((message, position) => (
        baseMessagesApi.update(message.id, { sort_order: (position + 1) * 10 })
      ))),
      'Приоритет сообщений обновлён.',
    )
  }

  return (
    <div className="chat-management__split">
      <form className="chat-management__card" onSubmit={(event) => void submit(event)}>
        <h2>Новое базовое сообщение</h2>
        <p className="chat-management__muted">
          Приветствия, сообщения вне графика и срочные оповещения
        </p>
        <div className="chat-management__form-grid">
          <label>
            Этап отправки
            <select
              value={sendPhase}
              onChange={(event) => setSendPhase(event.target.value as BaseMessage['send_phase'])}
            >
              {SEND_PHASE_OPTIONS.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
          </label>
          <label>Название<input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Например: Сбой оплаты" /></label>
          <label>
            Задержка, сек
            <input
              type="number"
              min="0"
              max="3600"
              value={delaySeconds}
              onChange={(event) => setDelaySeconds(event.target.valueAsNumber || 0)}
              title="Для mid_dialog / hold / автозакрытия по словам"
            />
          </label>
          <div className="chat-management__field-picker is-wide">
            <div className="chat-management__field-picker-head">
              <strong>Каналы</strong>
            </div>
            <label className="chat-management__check">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={() => setSelectedChannels(allSelected
                  ? []
                  : channelOptions.map((option) => option.value))}
              />
              Все каналы
            </label>
            {channelOptions.map((option) => (
              <label className="chat-management__check" key={option.value}>
                <input
                  type="checkbox"
                  checked={selected.includes(option.value)}
                  onChange={() => toggleChannel(option.value)}
                />
                {option.label}
              </label>
            ))}
          </div>
          <label className="is-wide">
            Текст
            <textarea required value={text} onChange={(event) => setText(event.target.value)} rows={4} />
          </label>
        </div>
        <div className="chat-management__actions">
          <button disabled={disabled}>Создать сообщение</button>
        </div>
      </form>
      <section className="chat-management__card">
        <h2>Базовые сообщения</h2>
        <ul className="chat-management__list">
          {orderedItems.map((item, index) => (
            <li className="chat-management__list-item" key={item.id}>
              <header>
                <div>
                  <strong>{item.title || SEND_PHASE_OPTIONS.find((option) => option.value === item.send_phase)?.label}</strong>
                  <br />
                  <small>
                    {SEND_PHASE_OPTIONS.find((option) => option.value === item.send_phase)?.label ?? item.send_phase}
                    {item.delay_seconds ? ` · задержка ${item.delay_seconds}с` : ''}
                    {' · '}
                    {(item.channels?.length
                      ? item.channels.map((value) => (
                        channelOptions.find((option) => option.value === value)?.label ?? value
                      )).join(', ')
                      : 'Все каналы')}
                  </small>
                </div>
                <span className={`chat-management__pill ${item.is_active ? 'is-success' : 'is-error'}`}>
                  {item.is_active ? 'активно' : 'выключено'}
                </span>
              </header>
              <p>{item.text}</p>
              <div className="chat-management__actions">
                <button
                  type="button"
                  className="is-secondary"
                  disabled={disabled || index === 0}
                  aria-label={`Повысить приоритет ${item.title}`}
                  onClick={() => moveMessage(index, -1)}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="is-secondary"
                  disabled={disabled || index === orderedItems.length - 1}
                  aria-label={`Понизить приоритет ${item.title}`}
                  onClick={() => moveMessage(index, 1)}
                >
                  ↓
                </button>
                <button
                  className="is-secondary"
                  disabled={disabled}
                  onClick={() => void perform(
                    () => baseMessagesApi.update(item.id, { is_active: !item.is_active }),
                    'Статус сообщения обновлён.',
                    {
                      title: item.is_active ? 'Выключить сообщение?' : 'Включить сообщение?',
                      description: `Сообщение «${item.title || item.send_phase}» будет ${item.is_active ? 'выключено' : 'включено'}.`,
                    },
                  )}
                >
                  {item.is_active ? 'Выключить' : 'Включить'}
                </button>
                <button
                  className="is-danger"
                  disabled={disabled}
                  onClick={() => void perform(
                    () => baseMessagesApi.remove(item.id),
                    'Сообщение удалено.',
                    {
                      title: 'Удалить сообщение?',
                      description: 'Сообщение будет удалено без восстановления.',
                    },
                  )}
                >
                  Удалить
                </button>
              </div>
            </li>
          ))}
        </ul>
        {!items.length && <div className="chat-management__empty">Базовых сообщений пока нет.</div>}
      </section>
    </div>
  )
}
