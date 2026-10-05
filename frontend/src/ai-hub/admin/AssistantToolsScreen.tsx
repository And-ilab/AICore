import { useEffect, useMemo, useState } from 'react'
import { ensureDevSession } from '../../auth/ensureDevSession'
import { Button, Card, StatusBadge } from '../../components'
import {
  createAssistantDocTemplate,
  deleteAssistantDocTemplate,
  listAssistantDocTemplates,
  updateAssistantDocTemplate,
  createRpaScenario,
  deleteRpaScenario,
  listRpaScenarios,
  updateRpaScenario,
  createSqlAccess,
  deleteSqlAccess,
  listSqlAccess,
  updateSqlAccess,
  type RpaScenario,
  type SqlAccess,
  type AssistantDocTemplate,
  type DocTemplateField,
  type DocTemplateFormat,
} from './api/assistantAdmin'
import './AssistantAdminScreens.css'

interface AssistantToolsScreenProps {
  canEdit?: boolean
}

type ToolsTab = 'templates' | 'rpa' | 'sql'

const FORMAT_OPTIONS: { value: DocTemplateFormat; label: string }[] = [
  { value: 'docx', label: 'Word' },
  { value: 'pdf', label: 'PDF' },
  { value: 'xlsx', label: 'Excel' },
  { value: 'pptx', label: 'PowerPoint' },
  { value: 'bpmn', label: 'BPMN' },
  { value: 'txt', label: 'Текст' },
  { value: 'mmd', label: 'Схема / ER' },
]

const EMPTY_FIELD = (): DocTemplateField => ({
  id: '',
  label: '',
  required: true,
})

function RpaWhitelistPanel({ canEdit }: { canEdit: boolean }) {
  const [items, setItems] = useState<RpaScenario[]>([])
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')

  const load = async () => {
    await ensureDevSession()
    setItems(await listRpaScenarios())
    setLoaded(true)
  }

  useEffect(() => {
    void load().catch((err: unknown) => {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить белый список')
    })
  }, [])

  const add = async () => {
    setBusy(true)
    setError('')
    try {
      await createRpaScenario({ name, code, description, active: true })
      setName('')
      setCode('')
      setDescription('')
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось добавить сценарий')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card data-testid="tools-rpa-whitelist">
      <header>
        <div>
          <h2>Сценарии и белый список</h2>
          <p>Это не бланки документов. Здесь сценарии робота: галочка «в списке» пускает сценарий в чат, без галочки оператор его не видит.</p>
        </div>
      </header>
      {error ? <p className="asst-admin-error" role="alert">{error}</p> : null}
      {!loaded && !error ? (
        <p className="asst-admin-note">Загрузка списка…</p>
      ) : null}
      {loaded && !items.length && !error ? (
        <p className="asst-admin-note">Список пуст. Добавьте сценарий ниже — он попадёт в белый список.</p>
      ) : null}
      <ul className="asst-rpa-admin__list">
        {items.map((item) => (
          <li key={item.id}>
            <label>
              <input
                type="checkbox"
                checked={item.active}
                disabled={!canEdit || busy}
                onChange={(event) => {
                  void updateRpaScenario(item.id, { active: event.target.checked })
                    .then(load)
                    .catch((err: unknown) => {
                      setError(err instanceof Error ? err.message : 'Не удалось обновить список')
                    })
                }}
              />
              в списке
            </label>
            <strong>{item.name}</strong>
            <span>{item.code}</span>
            <span>{item.description}</span>
            {canEdit ? (
              <Button
                type="button"
                variant="ghost"
                disabled={busy}
                onClick={() => {
                  void deleteRpaScenario(item.id).then(load).catch((err: unknown) => {
                    setError(err instanceof Error ? err.message : 'Не удалось убрать сценарий')
                  })
                }}
              >
                Убрать
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
      {canEdit ? (
        <div className="asst-rpa-admin__form">
          <input value={name} placeholder="Название" onChange={(event) => setName(event.target.value)} />
          <input value={code} placeholder="Код, например card-request" onChange={(event) => setCode(event.target.value)} />
          <input value={description} placeholder="Что делает робот" onChange={(event) => setDescription(event.target.value)} />
          <Button type="button" disabled={busy || !name.trim() || !code.trim()} onClick={() => void add()}>
            Добавить в белый список
          </Button>
        </div>
      ) : null}
    </Card>
  )
}

function SqlAccessPanel({ canEdit }: { canEdit: boolean }) {
  const [items, setItems] = useState<SqlAccess[]>([])
  const [name, setName] = useState('')
  const [objectName, setObjectName] = useState('')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')

  const load = async () => {
    await ensureDevSession()
    setItems(await listSqlAccess())
    setLoaded(true)
  }

  useEffect(() => {
    void load().catch((err: unknown) => {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить список доступов')
    })
  }, [])

  const add = async () => {
    setBusy(true)
    setError('')
    try {
      await createSqlAccess({
        name,
        object_name: objectName,
        description,
        active: true,
      })
      setName('')
      setObjectName('')
      setDescription('')
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось добавить доступ')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card data-testid="tools-sql-access">
      <header>
        <div>
          <h2>Доступ к витринам</h2>
          <p>
            Галочка «разрешено» пускает имя витрины в текст SQL-запроса. Запрос в базу банка не уходит: список только говорит, какие имена можно писать.
          </p>
        </div>
      </header>
      {error ? <p className="asst-admin-error" role="alert">{error}</p> : null}
      {!loaded && !error ? (
        <p className="asst-admin-note">Загрузка списка…</p>
      ) : null}
      {loaded && !items.length && !error ? (
        <p className="asst-admin-note">Список пуст. Добавьте витрину ниже.</p>
      ) : null}
      <ul className="asst-rpa-admin__list">
        {items.map((item) => (
          <li key={item.id}>
            <label>
              <input
                type="checkbox"
                checked={item.active}
                disabled={!canEdit || busy}
                onChange={(event) => {
                  void updateSqlAccess(item.id, { active: event.target.checked })
                    .then(load)
                    .catch((err: unknown) => {
                      setError(err instanceof Error ? err.message : 'Не удалось обновить доступ')
                    })
                }}
              />
              разрешено
            </label>
            <strong>{item.name}</strong>
            <span>{item.object_name}</span>
            <span>{item.description}</span>
            {canEdit ? (
              <Button
                type="button"
                variant="ghost"
                disabled={busy}
                onClick={() => {
                  void deleteSqlAccess(item.id).then(load).catch((err: unknown) => {
                    setError(err instanceof Error ? err.message : 'Не удалось убрать доступ')
                  })
                }}
              >
                Убрать
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
      {canEdit ? (
        <div className="asst-rpa-admin__form">
          <input value={name} placeholder="Название, например Карты клиентов" onChange={(event) => setName(event.target.value)} />
          <input value={objectName} placeholder="Витрина, например cards" onChange={(event) => setObjectName(event.target.value)} />
          <input value={description} placeholder="Что можно читать" onChange={(event) => setDescription(event.target.value)} />
          <Button type="button" disabled={busy || !name.trim() || !objectName.trim()} onClick={() => void add()}>
            Добавить доступ
          </Button>
        </div>
      ) : null}
    </Card>
  )
}

export function AssistantToolsScreen({
  canEdit = true,
}: AssistantToolsScreenProps) {
  const [tab, setTab] = useState<ToolsTab>('templates')
  const [items, setItems] = useState<AssistantDocTemplate[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [category, setCategory] = useState('Общее')
  const [outputFormat, setOutputFormat] = useState<DocTemplateFormat>('docx')
  const [body, setBody] = useState('')
  const [fields, setFields] = useState<DocTemplateField[]>([EMPTY_FIELD()])
  const [active, setActive] = useState(true)
  const [filter, setFilter] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const selected = items.find((item) => item.id === selectedId) ?? null

  const filtered = useMemo(() => {
    const q = filter.trim().toLocaleLowerCase('ru-RU')
    if (!q) return items
    return items.filter((item) =>
      `${item.name} ${item.category} ${item.format_label}`
        .toLocaleLowerCase('ru-RU')
        .includes(q),
    )
  }, [items, filter])

  const applyItem = (item: AssistantDocTemplate | null) => {
    setSelectedId(item?.id ?? null)
    setName(item?.name ?? '')
    setCategory(item?.category ?? 'Общее')
    setOutputFormat(item?.output_format ?? 'docx')
    setBody(item?.body ?? '')
    setFields(item?.fields?.length ? item.fields : [EMPTY_FIELD()])
    setActive(item?.active ?? true)
    setError('')
  }

  const load = async (preferId?: number | null) => {
    await ensureDevSession()
    const next = await listAssistantDocTemplates()
    setItems(next)
    const target = preferId ?? selectedId ?? next[0]?.id ?? null
    applyItem(next.find((item) => item.id === target) ?? next[0] ?? null)
  }

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        await load()
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Ошибка загрузки')
        }
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const createTemplate = async () => {
    if (!canEdit || busy) return
    setBusy(true)
    setError('')
    try {
      const created = await createAssistantDocTemplate({
        name: 'Новый шаблон',
        category: 'Общее',
        output_format: 'docx',
        body: 'Заявление\n\nЯ, {{full_name}}, прошу…',
        fields: [{ id: 'full_name', label: 'ФИО', required: true }],
        active: true,
      })
      setMessage('Шаблон создан')
      await load(created.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка создания')
    } finally {
      setBusy(false)
    }
  }

  const saveTemplate = async () => {
    if (!canEdit || !selected || busy) return
    setBusy(true)
    setError('')
    try {
      const updated = await updateAssistantDocTemplate(selected.id, {
        name,
        category,
        output_format: outputFormat,
        body,
        fields: fields.filter((field) => field.id.trim()),
        active,
      })
      setMessage('Шаблон сохранён')
      await load(updated.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка сохранения')
    } finally {
      setBusy(false)
    }
  }

  const removeTemplate = async () => {
    if (!canEdit || !selected || busy) return
    setBusy(true)
    setError('')
    try {
      await deleteAssistantDocTemplate(selected.id)
      setMessage('Шаблон удалён')
      await load(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка удаления')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="asst-admin-tools" data-testid="assistant-tools-screen">
      <div className="asst-admin-tools__tabs" role="tablist" aria-label="Инструменты">
        <button
          type="button"
          role="tab"
          className={tab === 'templates' ? 'is-active' : ''}
          aria-selected={tab === 'templates'}
          data-testid="tools-tab-templates"
          onClick={() => setTab('templates')}
        >
          Шаблоны
        </button>
        <button
          type="button"
          role="tab"
          className={tab === 'rpa' ? 'is-active' : ''}
          aria-selected={tab === 'rpa'}
          data-testid="tools-tab-rpa"
          onClick={() => setTab('rpa')}
        >
          RPA
        </button>
        <button
          type="button"
          role="tab"
          className={tab === 'sql' ? 'is-active' : ''}
          aria-selected={tab === 'sql'}
          data-testid="tools-tab-sql"
          onClick={() => setTab('sql')}
        >
          SQL
        </button>
      </div>

      {tab === 'rpa' ? <RpaWhitelistPanel canEdit={canEdit} /> : null}

      {tab === 'sql' ? <SqlAccessPanel canEdit={canEdit} /> : null}

      {tab === 'templates' ? (
        <div className="asst-admin-prompts__layout" data-testid="admin-doc-templates">
          <aside className="asst-admin-library">
            <header>
              <strong>Бланки банка</strong>
              <Button
                type="button"
                disabled={!canEdit || busy}
                onClick={() => void createTemplate()}
                data-testid="admin-doc-template-create"
              >
                + Шаблон
              </Button>
            </header>
            <input
              type="search"
              placeholder="Фильтр…"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              data-testid="admin-doc-template-filter"
            />
            <ul>
              {filtered.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className={item.id === selectedId ? 'is-active' : ''}
                    onClick={() => {
                      applyItem(item)
                      setMessage('')
                    }}
                    data-testid={`admin-doc-template-${item.id}`}
                  >
                    <span>{item.name}</span>
                    <small>
                      {item.format_label} · {item.category}
                      {item.active ? '' : ' · скрыт'}
                    </small>
                  </button>
                </li>
              ))}
              {!filtered.length ? (
                <li className="asst-admin-note">Нет шаблонов — нажмите «+ Шаблон».</li>
              ) : null}
            </ul>
          </aside>

          <div className="asst-admin-editor">
            <header>
              <div>
                <strong>Редактор бланка</strong>
                <p className="asst-admin-note">
                  В тексте используйте плейсхолдеры <code>{'{{field_id}}'}</code>.
                </p>
              </div>
              {selected ? (
                <StatusBadge status={active ? 'success' : 'neutral'}>
                  {active ? 'В чате' : 'Скрыт'}
                </StatusBadge>
              ) : null}
            </header>

            {error ? (
              <p className="asst-admin-error" role="alert">{error}</p>
            ) : null}
            {message && !error ? (
              <p className="asst-admin-ok" role="status">{message}</p>
            ) : null}

            {selected ? (
              <div className="asst-admin-form">
                <div className="asst-admin-form__row">
                  <label>
                    Название
                    <input
                      value={name}
                      disabled={!canEdit}
                      onChange={(event) => setName(event.target.value)}
                      data-testid="admin-doc-template-name"
                    />
                  </label>
                  <label>
                    Категория
                    <input
                      value={category}
                      disabled={!canEdit}
                      onChange={(event) => setCategory(event.target.value)}
                    />
                  </label>
                  <label>
                    Формат
                    <select
                      value={outputFormat}
                      disabled={!canEdit}
                      onChange={(event) =>
                        setOutputFormat(event.target.value as DocTemplateFormat)
                      }
                      data-testid="admin-doc-template-format"
                    >
                      {FORMAT_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <label>
                  Текст бланка
                  <textarea
                    rows={10}
                    value={body}
                    disabled={!canEdit}
                    onChange={(event) => setBody(event.target.value)}
                    data-testid="admin-doc-template-body"
                  />
                </label>
                <div className="asst-admin-fields" data-testid="admin-doc-template-fields">
                  <strong>Поля формы</strong>
                  {fields.map((field, index) => (
                    <div className="asst-admin-fields__row" key={index}>
                      <input
                        placeholder="id (full_name)"
                        value={field.id}
                        disabled={!canEdit}
                        onChange={(event) => {
                          const next = [...fields]
                          next[index] = { ...field, id: event.target.value }
                          setFields(next)
                        }}
                      />
                      <input
                        placeholder="Подпись"
                        value={field.label}
                        disabled={!canEdit}
                        onChange={(event) => {
                          const next = [...fields]
                          next[index] = { ...field, label: event.target.value }
                          setFields(next)
                        }}
                      />
                      <label className="asst-admin-fields__req">
                        <input
                          type="checkbox"
                          checked={Boolean(field.required)}
                          disabled={!canEdit}
                          onChange={(event) => {
                            const next = [...fields]
                            next[index] = { ...field, required: event.target.checked }
                            setFields(next)
                          }}
                        />
                        обяз.
                      </label>
                      <Button
                        type="button"
                        variant="ghost"
                        disabled={!canEdit || fields.length <= 1}
                        onClick={() => setFields(fields.filter((_, i) => i !== index))}
                      >
                        ×
                      </Button>
                    </div>
                  ))}
                  <Button
                    type="button"
                    variant="ghost"
                    disabled={!canEdit}
                    onClick={() => setFields([...fields, EMPTY_FIELD()])}
                  >
                    + Поле
                  </Button>
                </div>
                <label className="asst-admin-fields__req">
                  <input
                    type="checkbox"
                    checked={active}
                    disabled={!canEdit}
                    onChange={(event) => setActive(event.target.checked)}
                  />
                  Показывать в чате (Инструменты → Документ)
                </label>
                <div className="asst-admin-actions">
                  <Button
                    type="button"
                    disabled={!canEdit || busy}
                    onClick={() => void saveTemplate()}
                    data-testid="admin-doc-template-save"
                  >
                    Сохранить
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    disabled={!canEdit || busy}
                    onClick={() => void removeTemplate()}
                    data-testid="admin-doc-template-delete"
                  >
                    Удалить
                  </Button>
                </div>
              </div>
            ) : (
              <p className="asst-admin-note">Выберите шаблон слева или создайте новый.</p>
            )}
          </div>
        </div>
      ) : null}
    </section>
  )
}
