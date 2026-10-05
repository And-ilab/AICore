import { useEffect, useMemo, useState } from 'react'
import {
  controlWorkDay,
  getWorkScheduleStatus,
  resetSimulation,
  seedSimulation,
  type SeedResult,
} from '../api/managementApi'
import '../shell/Management.css'

const SIM_SEED_STORAGE_KEY = 'online-chat-simulator-seed-v1'

const presets = [
  {
    name: '1 оператор · 10 клиентов',
    description: 'Один оператор принимает поток из десяти обращений',
    operators: 1,
    clients: 10,
    messages: 2,
    autoAssign: true,
  },
  { name: 'Тихая смена', description: 'Небольшой поток, запас операторов', operators: 5, clients: 8, messages: 2, autoAssign: true },
  { name: 'Пик очереди', description: 'Много одновременных клиентов', operators: 4, clients: 30, messages: 4, autoAssign: true },
  { name: 'Перегрузка', description: 'Нагрузка значительно выше вместимости', operators: 2, clients: 60, messages: 8, autoAssign: false },
]

type SeedClient = {
  id: string
  dialog_id?: string
  name?: string
  phone?: string
  widget_url?: string
  status?: string
  operator_name?: string
}

type StoredSeed = {
  result: SeedResult
  operators: number
  clients: number
  messages: number
  autoAssign: boolean
}

function readStoredSeed(): StoredSeed | null {
  try {
    const raw = sessionStorage.getItem(SIM_SEED_STORAGE_KEY)
      ?? localStorage.getItem(SIM_SEED_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as StoredSeed
    if (!parsed?.result?.ok) return null
    return parsed
  } catch {
    return null
  }
}

function writeStoredSeed(payload: StoredSeed | null) {
  try {
    if (!payload) {
      sessionStorage.removeItem(SIM_SEED_STORAGE_KEY)
      localStorage.removeItem(SIM_SEED_STORAGE_KEY)
      return
    }
    const raw = JSON.stringify(payload)
    sessionStorage.setItem(SIM_SEED_STORAGE_KEY, raw)
    localStorage.setItem(SIM_SEED_STORAGE_KEY, raw)
  } catch {
    /* ignore quota / private mode */
  }
}

export function ChatSimulatorApp() {
  const stored = useMemo(() => readStoredSeed(), [])
  const [operators, setOperators] = useState(stored?.operators ?? 1)
  const [clients, setClients] = useState(stored?.clients ?? 10)
  const [messages, setMessages] = useState(stored?.messages ?? 2)
  const [autoAssign, setAutoAssign] = useState(stored?.autoAssign ?? true)
  const [resetBeforeSeed, setResetBeforeSeed] = useState(true)
  const [result, setResult] = useState<SeedResult | null>(stored?.result ?? null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState(
    stored?.result ? 'Восстановлен последний сценарий симулятора.' : '',
  )
  // Test-only online/offline toggle. In production there is no such button —
  // the line switches automatically by the admin-configured work schedule.
  const [lineOpen, setLineOpen] = useState<boolean | null>(null)
  const [scheduleLoading, setScheduleLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    const syncSchedule = () => {
      void getWorkScheduleStatus()
        .then((status) => {
          if (!cancelled) setLineOpen(status.is_open)
        })
        .catch(() => undefined)
    }
    syncSchedule()
    const timer = window.setInterval(syncSchedule, 5000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  const toggleLine = async () => {
    setScheduleLoading(true)
    setError('')
    try {
      const nextAction = lineOpen ? 'stop' : 'start'
      const response = await controlWorkDay(nextAction)
      setLineOpen(response.is_open)
      setNotice(
        response.is_open
          ? 'Линия переведена в онлайн. Диалоги из общей очереди распределяются операторам.'
          : 'Линия переведена в офлайн. Текущие диалоги вернулись в общую очередь, операторы офлайн.',
      )
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Не удалось переключить режим линии')
    } finally {
      setScheduleLoading(false)
    }
  }

  useEffect(() => {
    if (!result) {
      writeStoredSeed(null)
      return
    }
    writeStoredSeed({
      result,
      operators,
      clients,
      messages,
      autoAssign,
    })
  }, [result, operators, clients, messages, autoAssign])

  const operatorNames = useMemo(() => {
    const fromResult = result?.operator_names
      ?? result?.operators?.map((operator) => operator.name).filter(Boolean)
    if (fromResult?.length) return fromResult
    return result ? Array.from({ length: operators }, (_, index) => `Оператор ${index + 1}`) : []
  }, [operators, result])

  const seedClients = useMemo((): SeedClient[] => {
    const fromResult = (result?.clients ?? []) as SeedClient[]
    if (fromResult.length) return fromResult
    const ids = result?.client_ids ?? []
    return ids.map((id, index) => ({
      id: String(id),
      name: `Клиент ${index + 1}`,
      widget_url: `/widget/sample.html?sim_client=${encodeURIComponent(String(id))}`,
    }))
  }, [result])

  const seed = async () => {
    setLoading(true)
    setError('')
    setNotice('')
    try {
      const response = await seedSimulation({
        operators,
        clients,
        messages_per_dialog: messages,
        auto_assign: autoAssign,
        reset: resetBeforeSeed,
      })
      setResult(response)
      setNotice(
        'Сценарий создан. Откройте отдельные окна операторов и клиентов ниже — '
        + 'каждый клиент подхватит уже созданный диалог.',
      )
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Не удалось создать сценарий')
    } finally {
      setLoading(false)
    }
  }

  const reset = async () => {
    if (!window.confirm('Удалить тестовые данные симулятора?')) return
    setLoading(true)
    setError('')
    setNotice('')
    try {
      await resetSimulation()
      setResult(null)
      writeStoredSeed(null)
      setNotice('Тестовые данные удалены.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Не удалось сбросить данные')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="chat-management">
      <div className="chat-management__inner">
        <div className="chat-management__heading">
          <div>
            <h1>Симулятор онлайн-чата</h1>
            <p className="chat-management__muted">
              Тестовый стенд: создайте клиентов здесь — в АРМ появятся только реальные диалоги симулятора (без заглушек).
            </p>
          </div>
          <button
            type="button"
            className={lineOpen ? 'is-danger' : undefined}
            onClick={() => void toggleLine()}
            disabled={scheduleLoading || lineOpen === null}
            title="Только для теста/демо — в проде режим переключается автоматически по расписанию"
          >
            {lineOpen === null
              ? 'Проверка режима линии…'
              : scheduleLoading
                ? 'Переключение…'
                : lineOpen
                  ? '🟢 Линия онлайн · перевести в офлайн'
                  : '⚪ Линия офлайн · перевести в онлайн'}
          </button>
        </div>
        <p className="chat-management__muted">
          Переключатель выше — только для демо/теста в симуляторе. В проде онлайн/офлайн управляется
          автоматически по рабочему расписанию (настраивается администратором), без кнопки.
        </p>
        <p className="chat-management__notice">
          1) Создайте сценарий → 2) Откройте оператора (режим работы, не просмотр) и виджеты клиентов → 3) Пишите с обеих сторон.
          При автоназначении часть диалогов сразу уходит операторам (лимит нагрузки), остальные — в «Общую очередь».
          Не открывайте двух участников в одной вкладке. Виджет: <code>site-belarusbank</code>.
        </p>
        {error && <p className="chat-management__error" role="alert">{error}</p>}
        {notice && <p className="chat-management__success" role="status">{notice}</p>}

        <section className="chat-management__section" aria-labelledby="preset-heading">
          <h2 id="preset-heading">Готовые сценарии</h2>
          <div className="chat-management__preset-grid">
            {presets.map((preset) => (
              <article className="chat-management__card" key={preset.name}>
                <h3>{preset.name}</h3>
                <p className="chat-management__muted">{preset.description}</p>
                <p>{preset.operators} операторов · {preset.clients} клиентов · {preset.messages} сообщений</p>
                <button
                  className="is-secondary"
                  onClick={() => {
                    setOperators(preset.operators)
                    setClients(preset.clients)
                    setMessages(preset.messages)
                    setAutoAssign(preset.autoAssign)
                  }}
                >
                  Выбрать
                </button>
              </article>
            ))}
          </div>
        </section>

        <section className="chat-management__card chat-management__section" aria-labelledby="scenario-heading">
          <h2 id="scenario-heading">Параметры сценария</h2>
          <div className="chat-management__form-grid">
            <label>
              Операторы: <output className="chat-management__range-output">{operators}</output>
              <input
                aria-label="Количество операторов"
                type="range"
                min="1"
                max="20"
                value={operators}
                onChange={(event) => setOperators(event.target.valueAsNumber)}
              />
            </label>
            <label>
              Клиенты: <output className="chat-management__range-output">{clients}</output>
              <input
                aria-label="Количество клиентов"
                type="range"
                min="1"
                max="100"
                value={clients}
                onChange={(event) => setClients(event.target.valueAsNumber)}
              />
            </label>
            <label>
              Сообщений в диалоге
              <input
                type="number"
                min="0"
                max="100"
                value={messages}
                onChange={(event) => setMessages(event.target.valueAsNumber)}
              />
            </label>
            <div>
              <label className="chat-management__check">
                <input type="checkbox" checked={autoAssign} onChange={(event) => setAutoAssign(event.target.checked)} />
                Автоматически распределить диалоги
              </label>
              <label className="chat-management__check">
                <input type="checkbox" checked={resetBeforeSeed} onChange={(event) => setResetBeforeSeed(event.target.checked)} />
                Сбросить предыдущий сценарий перед запуском
              </label>
            </div>
          </div>
          <div className="chat-management__actions">
            <button onClick={() => void seed()} disabled={loading}>
              {loading ? 'Выполняется…' : 'Создать сценарий'}
            </button>
            <button className="is-danger" onClick={() => void reset()} disabled={loading}>Сбросить данные</button>
          </div>
        </section>

        {result && (
          <>
            <section className="chat-management__grid" aria-label="Результат симуляции">
              <article className="chat-management__card chat-management__kpi">
                <span>Операторы</span><strong>{operatorNames.length}</strong>
              </article>
              <article className="chat-management__card chat-management__kpi">
                <span>Клиенты</span><strong>{seedClients.length}</strong>
              </article>
              {Object.entries(result.summary ?? {}).map(([key, value]) => (
                <article className="chat-management__card chat-management__kpi" key={key}>
                  <span>{key.replaceAll('_', ' ')}</span><strong>{String(value)}</strong>
                </article>
              ))}
            </section>

            <section className="chat-management__launch-grid" aria-label="Окна участников">
              <div className="chat-management__card">
                <div className="chat-management__toolbar">
                  <h2>АРМ операторов</h2>
                </div>
                <ul className="chat-management__list">
                  {operatorNames.map((name) => (
                    <li key={name}>
                      <a
                        className="chat-button is-secondary"
                        href={`/online-chat?mode=operate&operator=${encodeURIComponent(name)}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {name}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="chat-management__card">
                <div className="chat-management__toolbar">
                  <h2>Виджеты клиентов</h2>
                </div>
                <ul className="chat-management__list">
                  {seedClients.map((client, index) => (
                    <li key={client.id}>
                      <a
                        className="chat-button is-secondary"
                        href={client.widget_url || `/widget/sample.html?sim_client=${encodeURIComponent(client.id)}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {client.name || `Клиент ${index + 1}`}
                        {client.status ? ` · ${client.status}` : ''}
                        {client.operator_name ? ` → ${client.operator_name}` : ''}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            </section>
          </>
        )}
      </div>
    </main>
  )
}
