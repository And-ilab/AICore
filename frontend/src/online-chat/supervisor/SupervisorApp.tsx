import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getSupervisorOverview,
  runRouting,
  type SupervisorOverview,
} from '../api/managementApi'
import '../shell/Management.css'

interface SupervisorAppProps {
  demoMode?: boolean
}

const PRESENCE_LABELS: Record<string, string> = {
  online: 'В сети',
  busy: 'Занят',
  break: 'Перерыв',
  lunch: 'Обед',
  training: 'Обучение',
  meeting: 'Совещание',
  tech_issue: 'Техпроблема',
  offline: 'Не в сети',
}

function formatSeconds(value?: number | null) {
  if (value == null) return '—'
  const minutes = Math.floor(value / 60)
  return `${minutes}:${String(Math.floor(value % 60)).padStart(2, '0')}`
}

function presenceLabel(presence: string) {
  return PRESENCE_LABELS[presence] ?? presence
}

function isStaffRole(role?: string) {
  return role === 'supervisor' || role === 'admin'
}

function operatorDepartment(operator: SupervisorOverview['operators'][number]) {
  if (isStaffRole(operator.role)) return '—'
  if (operator.department_name) return operator.department_name
  if (operator.department && typeof operator.department === 'object') return operator.department.name
  return operator.department ? String(operator.department) : 'Без отдела'
}

function operatorRoleLabel(role?: string) {
  if (role === 'supervisor') return 'Супервизор'
  if (role === 'admin') return 'Админ'
  return null
}

const CHANNEL_LABELS: Record<string, string> = {
  widget: 'Виджет сайта',
  web: 'Виджет сайта',
  telegram: 'Telegram',
  viber: 'Viber',
  vk: 'ВКонтакте',
  ok: 'Одноклассники',
  whatsapp: 'WhatsApp',
  api: 'API',
  email: 'Эл. почта',
  phone: 'Телефон',
}

function channelLabel(channel: string) {
  return CHANNEL_LABELS[channel] ?? channel
}

function openOperatorArm(operatorName: string) {
  const params = new URLSearchParams()
  params.set('mode', 'view')
  params.set('operator', operatorName)
  params.set('transfer', '1')
  // Carry the active demo role so the view-only ARM keeps supervisor rights in
  // the new tab (otherwise it falls back to base roles and returns 403).
  const demoRole = new URLSearchParams(window.location.search).get('demo_role')
  if (demoRole) params.set('demo_role', demoRole)
  window.open(`/online-chat/operators?${params.toString()}`, '_blank', 'noopener,noreferrer')
}

export function SupervisorApp({ demoMode: _demoMode = false }: SupervisorAppProps) {
  const [overview, setOverview] = useState<SupervisorOverview | null>(null)
  const [presence, setPresence] = useState('all')
  const [department, setDepartment] = useState('all')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [routing, setRouting] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)

  const refresh = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      const result = await getSupervisorOverview()
      setOverview(result)
      setUpdatedAt(new Date())
      setError('')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Не удалось загрузить оперативные данные')
    } finally {
      if (!quiet) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => void refresh(true), 10_000)
    return () => window.clearInterval(timer)
  }, [refresh])

  const departments = useMemo(
    () => Array.from(
      new Set(
        (overview?.operators ?? [])
          .filter((operator) => !isStaffRole(operator.role))
          .map(operatorDepartment)
          .filter((name) => name !== '—'),
      ),
    ).sort(),
    [overview],
  )
  const operators = useMemo(() => {
    const query = search.trim().toLowerCase()
    return (overview?.operators ?? []).filter((operator) => {
      const matchesPresence = presence === 'all' || operator.presence === presence
      const matchesDepartment = department === 'all' || operatorDepartment(operator) === department
      const matchesSearch = !query || operator.name.toLowerCase().includes(query)
      return matchesPresence && matchesDepartment && matchesSearch
    })
  }, [department, overview, presence, search])
  const kpis = overview?.kpis ?? {}
  const queues = overview?.queues ?? []

  const handleRouting = async () => {
    setRouting(true)
    setNotice('')
    try {
      await runRouting()
      setNotice('Маршрутизация выполнена: свободные диалоги распределены по операторам.')
      await refresh(true)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Не удалось запустить маршрутизацию')
    } finally {
      setRouting(false)
    }
  }

  return (
    <main className="chat-management">
      <div className="chat-management__inner">
        <div className="chat-management__heading">
          <div>
            <h1>Панель супервизора</h1>
            <p className="chat-management__muted">
              Очереди, нагрузка операторов и ручной запуск автоназначения
            </p>
          </div>
          <div className="chat-management__actions">
            <button className="is-secondary" onClick={() => void refresh()} disabled={loading}>
              {loading ? 'Обновляем…' : 'Обновить'}
            </button>
            <button onClick={() => void handleRouting()} disabled={routing}>
              {routing ? 'Распределяем…' : 'Запустить маршрутизацию'}
            </button>
          </div>
        </div>

        {error && <p className="chat-management__error" role="alert">{error}</p>}
        {notice && <p className="chat-management__success" role="status">{notice}</p>}

        <section className="chat-management__grid" aria-label="Ключевые показатели">
          {[
            ['В очереди (онлайн)', kpis.waiting_online ?? kpis.waiting ?? 0],
            ['В очереди (офлайн)', kpis.waiting_offline ?? 0],
            ['Активные диалоги', kpis.active ?? 0],
            ['Операторы онлайн', kpis.online_operators ?? 0],
            ['Ср. ожидание online', formatSeconds(kpis.average_wait_online_seconds ?? kpis.average_wait_seconds)],
            ['Ср. ожидание offline', formatSeconds(kpis.average_wait_offline_seconds)],
            ['SLA первого ответа', kpis.sla_percent == null ? '—' : `${kpis.sla_percent}%`],
            ['Закрыто сегодня', kpis.closed_today ?? 0],
          ].map(([label, value]) => (
            <article className="chat-management__card chat-management__kpi" key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
            </article>
          ))}
        </section>

        <section className="chat-management__section chat-management__card" aria-labelledby="operators-heading">
          <div className="chat-management__toolbar">
            <h2 id="operators-heading">Операторы</h2>
            <div className="chat-management__actions chat-management__actions--grow">
              <label className="chat-management__search">
                Поиск
                <input
                  type="search"
                  placeholder="ФИО оператора"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </label>
              <label>
                Статус
                <select value={presence} onChange={(event) => setPresence(event.target.value)}>
                  <option value="all">Все</option>
                  <option value="online">В сети</option>
                  <option value="busy">Занят</option>
                  <option value="break">Перерыв</option>
                  <option value="lunch">Обед</option>
                  <option value="training">Обучение</option>
                  <option value="meeting">Совещание</option>
                  <option value="tech_issue">Техпроблема</option>
                  <option value="offline">Не в сети</option>
                </select>
              </label>
              <label>
                Отдел
                <select value={department} onChange={(event) => setDepartment(event.target.value)}>
                  <option value="all">Все отделы</option>
                  {departments.map((item) => <option key={item}>{item}</option>)}
                </select>
              </label>
            </div>
          </div>
          <div className="chat-management__table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Оператор</th>
                  <th>Статус</th>
                  <th>Нагрузка</th>
                  <th>Закрыто сегодня</th>
                  <th>Ср. первый ответ</th>
                  <th>Время в диалогах</th>
                  <th>Ср. на диалог</th>
                  <th>Каналы сейчас</th>
                  <th>Отдел</th>
                </tr>
              </thead>
              <tbody>
                {operators.map((operator) => {
                  const load = operator.active_dialogs ?? operator.load ?? 0
                  return (
                    <tr
                      key={operator.id}
                      className="chat-management__row-link"
                      tabIndex={0}
                      role="link"
                      aria-label={`Открыть АРМ оператора ${operator.name}`}
                      onClick={() => openOperatorArm(operator.name)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          openOperatorArm(operator.name)
                        }
                      }}
                    >
                      <td>
                        <span className="chat-management__operator-name">
                          <strong>{operator.name}</strong>
                          {operatorRoleLabel(operator.role) && (
                            <span className="chat-management__pill chat-management__role-badge">
                              {operatorRoleLabel(operator.role)}
                            </span>
                          )}
                        </span>
                      </td>
                      <td>
                        <span className={`chat-management__pill is-${operator.presence}`}>
                          {presenceLabel(operator.presence)}
                        </span>
                      </td>
                      <td>{load} / {operator.capacity}</td>
                      <td>{operator.closed_today ?? 0}</td>
                      <td>{formatSeconds(operator.avg_first_response_seconds)}</td>
                      <td>{formatSeconds(operator.time_in_dialogs_seconds)}</td>
                      <td>{formatSeconds(operator.avg_dialog_seconds)}</td>
                      <td>
                        {operator.channels_breakdown && Object.keys(operator.channels_breakdown).length
                          ? Object.entries(operator.channels_breakdown)
                              .map(([channel, count]) => `${channelLabel(channel)}: ${count}`)
                              .join(', ')
                          : '—'}
                      </td>
                      <td>{operatorDepartment(operator)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {!loading && operators.length === 0 && <div className="chat-management__empty">Операторы не найдены.</div>}
          </div>
        </section>

        <section aria-labelledby="queues-heading">
          <div className="chat-management__toolbar">
            <h2 id="queues-heading">Очереди по отделам</h2>
            {updatedAt && <small className="chat-management__muted">Обновлено {updatedAt.toLocaleTimeString('ru-RU')}</small>}
          </div>
          <div className="chat-management__queue-grid">
            {queues.map((queue, index) => {
              const waiting = queue.waiting ?? 0
              const active = queue.active ?? 0
              const tone = waiting >= 5 ? 'is-critical' : waiting > 0 ? 'is-warn' : 'is-ok'
              return (
                <article
                  className={`chat-management__card chat-management__queue-card ${tone}`}
                  key={queue.id ?? `${queue.name}-${index}`}
                >
                  <header>
                    <h3>{queue.name}</h3>
                    <span className={`chat-management__pill ${tone === 'is-ok' ? 'is-success' : tone === 'is-warn' ? 'is-warn' : 'is-error'}`}>
                      {waiting === 0 ? 'пусто' : `${waiting} в очереди`}
                    </span>
                  </header>
                  <div className="chat-management__queue-metrics">
                    <div>
                      <span>Online</span>
                      <strong>{queue.waiting_online ?? waiting}</strong>
                    </div>
                    <div>
                      <span>Offline</span>
                      <strong>{queue.waiting_offline ?? 0}</strong>
                    </div>
                    <div>
                      <span>В работе</span>
                      <strong>{active}</strong>
                    </div>
                    <div>
                      <span>Макс. ожидание</span>
                      <strong>{formatSeconds(queue.longest_wait_seconds)}</strong>
                    </div>
                  </div>
                  <div className="chat-management__queue-bar" aria-hidden>
                    <span style={{ width: `${Math.min(100, waiting * 12)}%` }} />
                  </div>
                </article>
              )
            })}
          </div>
          {!loading && queues.length === 0 && (
            <div className="chat-management__card chat-management__empty">
              Активных отделов нет — создайте отделы в разделе «Управление».
            </div>
          )}
        </section>
      </div>
    </main>
  )
}
