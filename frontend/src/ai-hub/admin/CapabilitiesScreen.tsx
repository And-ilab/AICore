import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ensureDevSession,
  isAuthErrorMessage,
  resetDevSessionCache,
} from '../../auth/ensureDevSession'
import { Button, Card, StatusBadge } from '../../components'
import {
  AssistantAdminApiError,
  TASK_EVENT_TRIGGERS,
  createAssistantPrompt,
  createAssistantSkill,
  deleteAssistantPrompt,
  deleteAssistantSkill,
  listAssistantCapabilities,
  listAssistantPrompts,
  listAssistantSkills,
  setCapabilityEnabled,
  updateAssistantPrompt,
  updateAssistantSkill,
  type AssistantCapability,
  type AssistantPrompt,
  type AssistantSkill,
  type PromptStatus,
} from './api/assistantAdmin'
import './AssistantAdminScreens.css'

interface CapabilitiesScreenProps {
  canEdit?: boolean
}

function formatAdminError(error: unknown, fallback: string): string {
  if (error instanceof AssistantAdminApiError) {
    const detail =
      error.details.request?.[0] ||
      Object.values(error.details).flat()[0]
    if (detail) return detail
  }
  const message = error instanceof Error ? error.message : ''
  if (message === 'authentication_required') {
    return 'Нет сессии Django. Нажмите «Обновить» — в DEV выполнится вход как dev-role-01.'
  }
  if (message === 'csrf_failed') {
    return 'Сбой CSRF после входа. Нажмите «Обновить» — токен обновится автоматически.'
  }
  if (message === 'permission_denied') {
    return 'Недостаточно прав для этой операции.'
  }
  if (message && isAuthErrorMessage(message)) {
    return 'Нет сессии Django. Нажмите «Обновить» — в DEV выполнится вход как dev-role-01.'
  }
  return message || fallback
}

function openAdminScreen(screenId: string) {
  window.history.pushState({}, '', `/ai-hub/admin/${screenId}`)
  window.dispatchEvent(new PopStateEvent('popstate'))
  window.location.assign(`/ai-hub/admin/${screenId}`)
}

function statusLabel(status: PromptStatus): string {
  return status === 'published' ? 'опубликован' : 'черновик'
}

function SkillTaskPromptsPanel({ canEdit }: { canEdit: boolean }) {
  const [prompts, setPrompts] = useState<AssistantPrompt[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [body, setBody] = useState('')
  const [eventTrigger, setEventTrigger] = useState<string>(TASK_EVENT_TRIGGERS[0])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)

  const taskPrompts = useMemo(
    () => prompts.filter((item) => item.prompt_type === 'task'),
    [prompts],
  )
  const selected = taskPrompts.find((item) => item.id === selectedId) ?? null

  const applySelected = (item: AssistantPrompt | null) => {
    if (!item) {
      setSelectedId(null)
      setName('')
      setBody('')
      setEventTrigger(TASK_EVENT_TRIGGERS[0])
      return
    }
    setSelectedId(item.id)
    setName(item.name)
    setBody(item.body)
    setEventTrigger(item.event_trigger || TASK_EVENT_TRIGGERS[0])
  }

  const load = useCallback(async (preferId?: number | null) => {
    setLoading(true)
    setError('')
    try {
      await ensureDevSession()
      const items = await listAssistantPrompts()
      setPrompts(items)
      const tasks = items.filter((item) => item.prompt_type === 'task')
      const target =
        preferId
        ?? selectedId
        ?? tasks.find((item) => item.name.includes('перевод en'))?.id
        ?? tasks[0]?.id
        ?? null
      const current = tasks.find((item) => item.id === target) ?? null
      applySelected(current)
    } catch (err) {
      setError(formatAdminError(err, 'Не удалось загрузить Task-промпты'))
      setPrompts([])
      applySelected(null)
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const runAction = async (action: () => Promise<void>, fallback: string) => {
    if (busy) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await action()
    } catch (err) {
      if (isAuthErrorMessage(err instanceof Error ? err.message : '')) {
        resetDevSessionCache()
        try {
          await ensureDevSession()
          await action()
          return
        } catch (retryErr) {
          setError(formatAdminError(retryErr, fallback))
          return
        }
      }
      setError(formatAdminError(err, fallback))
    } finally {
      setBusy(false)
    }
  }

  const createTask = async () => {
    if (!canEdit) return
    await runAction(async () => {
      const created = await createAssistantPrompt({
        name: 'новый навык',
        body: 'Опишите инструкцию для события.',
        prompt_type: 'task',
        scope: 'bank',
        event_trigger: 'Начало диалога',
      })
      setNotice('Черновик Task-промпта создан')
      await load(created.id)
    }, 'Не удалось создать Task-промпт')
  }

  const saveDraft = async () => {
    if (!canEdit || !selected) return
    await runAction(async () => {
      const updated = await updateAssistantPrompt(selected.id, {
        name: name.trim() || selected.name,
        body: body.trim() || selected.body,
        prompt_type: 'task',
        event_trigger: eventTrigger,
        status: 'draft',
      })
      setNotice(`Черновик сохранён · v${updated.version}`)
      await load(updated.id)
    }, 'Не удалось сохранить черновик')
  }

  const publish = async () => {
    if (!canEdit || !selected) return
    await runAction(async () => {
      await updateAssistantPrompt(selected.id, {
        name: name.trim() || selected.name,
        body: body.trim() || selected.body,
        prompt_type: 'task',
        event_trigger: eventTrigger,
        status: 'draft',
      })
      const published = await updateAssistantPrompt(selected.id, {
        status: 'published',
      })
      setNotice(`Опубликовано · v${published.version}`)
      await load(published.id)
    }, 'Не удалось опубликовать')
  }

  const remove = async () => {
    if (!canEdit || !selected || selected.status === 'published') return
    await runAction(async () => {
      await deleteAssistantPrompt(selected.id)
      setNotice('Task-промпт удалён')
      await load(null)
    }, 'Не удалось удалить')
  }

  const triggerOptions = useMemo(() => {
    const known = new Set<string>([...TASK_EVENT_TRIGGERS])
    for (const item of taskPrompts) {
      if (item.event_trigger) known.add(item.event_trigger)
    }
    if (eventTrigger) known.add(eventTrigger)
    return [...known]
  }, [taskPrompts, eventTrigger])

  if (loading) {
    return <Card className="kb-admin-loading">Загрузка промптов типа Task…</Card>
  }

  return (
    <div className="asst-admin-task-skills" data-testid="skill-task-prompts">
      {error && (
        <Card className="kb-admin__error" role="alert">
          <div className="kb-admin__error-main">
            <strong>Уведомление</strong>
            <span>{error}</span>
          </div>
          <Button type="button" variant="ghost" onClick={() => void load()}>
            Обновить
          </Button>
        </Card>
      )}
      {notice && !error && (
        <p className="asst-admin-ok" role="status">{notice}</p>
      )}

      <div className="asst-admin-task-skills__layout">
        <aside className="asst-admin-library" data-testid="task-prompt-list">
          <Button
            type="button"
            variant="secondary"
            disabled={!canEdit || busy}
            onClick={() => void createTask()}
            data-testid="task-prompt-add"
          >
            + Добавить
          </Button>
          <ul>
            {taskPrompts.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className={item.id === selectedId ? 'is-active' : ''}
                  onClick={() => applySelected(item)}
                  data-testid={`task-prompt-${item.id}`}
                >
                  <span className="asst-admin-task-skills__row">
                    <span>{item.name}</span>
                    <StatusBadge status={item.status === 'published' ? 'success' : 'warning'}>
                      {statusLabel(item.status)}
                    </StatusBadge>
                  </span>
                </button>
              </li>
            ))}
            {!taskPrompts.length && (
              <li className="asst-admin-note">Нет Task-промптов — нажмите «+ Добавить».</li>
            )}
          </ul>
          {selected && selected.status !== 'published' ? (
            <Button
              type="button"
              variant="secondary"
              disabled={!canEdit || busy}
              onClick={() => void remove()}
              data-testid="task-prompt-delete"
            >
              Удалить
            </Button>
          ) : null}
        </aside>

        <div className="asst-admin-editor" data-testid="task-prompt-editor">
          {!selected ? (
            <p className="app-muted">Выберите Task-промпт слева или создайте новый.</p>
          ) : (
            <>
              <header>
                <StatusBadge status={selected.status === 'published' ? 'success' : 'neutral'}>
                  {selected.status === 'published' ? 'Опубликован' : 'Черновик'}
                </StatusBadge>
                <div className="asst-admin-actions">
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={!canEdit || busy}
                    onClick={() => void saveDraft()}
                    data-testid="task-prompt-save"
                  >
                    Сохранить черновик
                  </Button>
                  <Button
                    type="button"
                    variant="primary"
                    disabled={!canEdit || busy}
                    onClick={() => void publish()}
                    data-testid="task-prompt-publish"
                  >
                    Опубликовать
                  </Button>
                </div>
              </header>

              <div className="asst-admin-form">
                <label>
                  Название
                  <input
                    value={name}
                    disabled={!canEdit || busy}
                    onChange={(event) => setName(event.target.value)}
                    data-testid="task-prompt-name"
                  />
                </label>
                <div className="asst-admin-form__row">
                  <label>
                    Тип промпта
                    <select value="task" disabled>
                      <option value="task">Task — задание</option>
                    </select>
                  </label>
                  <label>
                    Событие (триггер)
                    <select
                      value={eventTrigger}
                      disabled={!canEdit || busy}
                      onChange={(event) => setEventTrigger(event.target.value)}
                      data-testid="task-prompt-trigger"
                    >
                      {triggerOptions.map((trigger) => (
                        <option key={trigger} value={trigger}>
                          {trigger}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <label>
                  Текст промпта
                  <textarea
                    rows={7}
                    value={body}
                    disabled={!canEdit || busy}
                    onChange={(event) => setBody(event.target.value)}
                    data-testid="task-prompt-body"
                  />
                </label>
              </div>

              <div className="asst-admin-preview asst-admin-task-skills__preview">
                <header>
                  <strong>Preview · тест</strong>
                </header>
                <Card>
                  <p>{body || '—'}</p>
                </Card>
                <Button type="button" disabled>
                  Запустить тест на событии
                </Button>
                <p className="asst-admin-note">
                  Переменные {'{{kb}}'}, {'{{user}}'}, {'{{dept}}'} подставляются при test-run
                  на выбранном событии.
                </p>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function OrgSkillsPanel({ canEdit }: { canEdit: boolean }) {
  const [items, setItems] = useState<AssistantSkill[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [alias, setAlias] = useState('')
  const [instruction, setInstruction] = useState('')
  const [departmentScope, setDepartmentScope] = useState('')
  const [needsAttachment, setNeedsAttachment] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)

  const selected = items.find((item) => item.id === selectedId) ?? null

  const applySelected = (item: AssistantSkill | null) => {
    if (!item) {
      setSelectedId(null)
      setName('')
      setAlias('')
      setInstruction('')
      setDepartmentScope('')
      setNeedsAttachment(false)
      return
    }
    setSelectedId(item.id)
    setName(item.name)
    setAlias(item.alias)
    setInstruction(item.instruction)
    setDepartmentScope(item.department_scope)
    setNeedsAttachment(item.needs_attachment)
  }

  const load = useCallback(async (preferId?: number | null) => {
    setLoading(true)
    setError('')
    try {
      await ensureDevSession()
      const rows = await listAssistantSkills()
      setItems(rows)
      const target =
        preferId != null
          ? rows.find((item) => item.id === preferId)
          : rows.find((item) => item.id === selectedId) ?? rows[0] ?? null
      applySelected(target ?? null)
    } catch (err) {
      setItems([])
      applySelected(null)
      setError(formatAdminError(err, 'Ошибка загрузки навыков'))
    } finally {
      setLoading(false)
    }
  }, [selectedId])

  useEffect(() => {
    void load()
    // initial catalog load
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const run = async (action: () => Promise<void>, ok: string) => {
    if (!canEdit || busy) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await action()
      setNotice(ok)
    } catch (err) {
      setError(formatAdminError(err, 'Ошибка сохранения'))
    } finally {
      setBusy(false)
    }
  }

  const save = () => {
    if (!selected) return
    void run(async () => {
      const updated = await updateAssistantSkill(selected.id, {
        name,
        alias,
        instruction,
        needs_attachment: needsAttachment,
        department_scope: departmentScope,
      })
      setItems((current) =>
        current.map((row) => (row.id === updated.id ? updated : row)),
      )
      applySelected(updated)
    }, 'Навык сохранён')
  }

  const toggleEnabled = () => {
    if (!selected) return
    void run(async () => {
      const updated = await updateAssistantSkill(selected.id, {
        enabled: !selected.enabled,
      })
      setItems((current) =>
        current.map((row) => (row.id === updated.id ? updated : row)),
      )
      applySelected(updated)
    }, selected.enabled ? 'Навык выключен' : 'Навык включён')
  }

  const createSkill = () => {
    void run(async () => {
      const created = await createAssistantSkill({
        name: 'Новый навык',
        alias: `navyk-${Date.now().toString(36)}`,
        instruction: 'Опишите, как модель должна отвечать.',
      })
      setItems((current) => [...current, created])
      applySelected(created)
    }, 'Навык создан')
  }

  const remove = () => {
    if (!selected) return
    void run(async () => {
      await deleteAssistantSkill(selected.id)
      const next = items.filter((item) => item.id !== selected.id)
      setItems(next)
      applySelected(next[0] ?? null)
    }, 'Навык удалён')
  }

  if (loading) {
    return <Card className="kb-admin-loading">Загрузка навыков…</Card>
  }

  return (
    <div className="asst-admin-task-skills" data-testid="org-skills-panel">
      <h2>Навыки</h2>
      <p className="asst-admin-note">
        Слой «Банк»: слэш-алиас и промпт. Выключенный навык не виден в /.
      </p>
      {error && (
        <Card className="kb-admin__error" role="alert">
          <div className="kb-admin__error-main">
            <strong>Уведомление</strong>
            <span>{error}</span>
          </div>
          <Button type="button" variant="ghost" onClick={() => void load()}>
            Обновить
          </Button>
        </Card>
      )}
      {notice && !error && (
        <p className="asst-admin-ok" role="status">{notice}</p>
      )}

      <div className="asst-admin-task-skills__layout">
        <aside className="asst-admin-library" data-testid="org-skill-list">
          <Button
            type="button"
            variant="secondary"
            disabled={!canEdit || busy}
            onClick={() => void createSkill()}
            data-testid="org-skill-add"
          >
            + Добавить
          </Button>
          <ul>
            {items.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className={item.id === selectedId ? 'is-active' : ''}
                  onClick={() => applySelected(item)}
                  data-testid={`org-skill-${item.code || item.id}`}
                >
                  <span className="asst-admin-task-skills__row">
                    <span>{item.name}</span>
                    <StatusBadge status={item.enabled ? 'success' : 'neutral'}>
                      {item.enabled ? 'Вкл' : 'Выкл'}
                    </StatusBadge>
                  </span>
                  <small>/{item.alias}{item.code ? ` · ${item.code}` : ''}</small>
                </button>
              </li>
            ))}
            {!items.length && (
              <li className="asst-admin-note">Нет навыков банка.</li>
            )}
          </ul>
        </aside>

        <div className="asst-admin-editor" data-testid="org-skill-editor">
          {!selected ? (
            <p className="app-muted">Выберите навык слева или создайте новый.</p>
          ) : (
            <>
              <header>
                <StatusBadge status={selected.enabled ? 'success' : 'neutral'}>
                  {selected.enabled ? 'Включён' : 'Выключен'}
                </StatusBadge>
                <div className="asst-admin-actions">
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={!canEdit || busy}
                    onClick={() => void toggleEnabled()}
                    data-testid="org-skill-toggle"
                  >
                    {selected.enabled ? 'Выключить' : 'Включить'}
                  </Button>
                  <Button
                    type="button"
                    variant="primary"
                    disabled={!canEdit || busy}
                    onClick={() => void save()}
                    data-testid="org-skill-save"
                  >
                    Сохранить
                  </Button>
                  {!selected.code ? (
                    <Button
                      type="button"
                      variant="ghost"
                      disabled={!canEdit || busy}
                      onClick={() => void remove()}
                      data-testid="org-skill-delete"
                    >
                      Удалить
                    </Button>
                  ) : null}
                </div>
              </header>

              <div className="asst-admin-form">
                <label>
                  Название
                  <input
                    value={name}
                    disabled={!canEdit || busy}
                    onChange={(event) => setName(event.target.value)}
                    data-testid="org-skill-name"
                  />
                </label>
                <div className="asst-admin-form__row">
                  <label>
                    Алиас
                    <input
                      value={alias}
                      disabled={!canEdit || busy}
                      onChange={(event) => setAlias(event.target.value)}
                      data-testid="org-skill-alias"
                    />
                  </label>
                  <label>
                    Подразделение (AD)
                    <input
                      value={departmentScope}
                      disabled={!canEdit || busy}
                      onChange={(event) => setDepartmentScope(event.target.value)}
                      placeholder="необязательно"
                      data-testid="org-skill-dept"
                    />
                  </label>
                </div>
                <label className="asst-admin-form__check">
                  <input
                    type="checkbox"
                    checked={needsAttachment}
                    disabled={!canEdit || busy}
                    onChange={(event) => setNeedsAttachment(event.target.checked)}
                    data-testid="org-skill-attach"
                  />
                  Желательно вложение
                </label>
                <label>
                  Текст промпта
                  <textarea
                    rows={8}
                    value={instruction}
                    disabled={!canEdit || busy}
                    onChange={(event) => setInstruction(event.target.value)}
                    data-testid="org-skill-instruction"
                  />
                </label>
              </div>

              <div className="asst-admin-preview asst-admin-task-skills__preview">
                <header>
                  <strong>Превью промпта</strong>
                </header>
                <Card data-testid="org-skill-preview">
                  <p>{instruction || '—'}</p>
                </Card>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export function CapabilitiesScreen({ canEdit = true }: CapabilitiesScreenProps) {
  const [items, setItems] = useState<AssistantCapability[]>([])
  const [busyCode, setBusyCode] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async (forceRelogin = false) => {
    setLoading(true)
    setError('')
    try {
      if (forceRelogin) resetDevSessionCache()
      let ok = await ensureDevSession()
      if (!ok) {
        resetDevSessionCache()
        ok = await ensureDevSession()
      }
      if (!ok) {
        setItems([])
        setError(formatAdminError(
          new Error('authentication_required'),
          'Нет сессии',
        ))
        return
      }
      setItems(await listAssistantCapabilities())
    } catch (err) {
      setItems([])
      setError(formatAdminError(err, 'Ошибка загрузки'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh(false)
  }, [refresh])

  const toggle = async (item: AssistantCapability) => {
    if (!canEdit || busyCode) return
    setBusyCode(item.code)
    setError('')
    try {
      const updated = await setCapabilityEnabled(item.code, !item.enabled)
      setItems((current) =>
        current.map((row) => (row.code === updated.code ? updated : row)),
      )
    } catch (err) {
      if (isAuthErrorMessage(err instanceof Error ? err.message : '')) {
        resetDevSessionCache()
        try {
          const updated = await setCapabilityEnabled(item.code, !item.enabled)
          setItems((current) =>
            current.map((row) => (row.code === updated.code ? updated : row)),
          )
          return
        } catch (retryErr) {
          setError(formatAdminError(retryErr, 'Ошибка сохранения'))
          return
        }
      }
      setError(formatAdminError(err, 'Ошибка сохранения'))
    } finally {
      setBusyCode('')
    }
  }

  return (
    <section className="asst-admin-caps" data-testid="capabilities-screen">
      <p className="asst-admin-note">
        Навыки и инструменты ассистента · отдельно от skill-групп чата.
        Выключенный capability не показывается в панели ассистента.
      </p>

      <OrgSkillsPanel canEdit={canEdit} />

      {error && (
        <Card className="kb-admin__error" role="alert">
          <div className="kb-admin__error-main">
            <strong>Уведомление</strong>
            <span>{error}</span>
          </div>
          <div className="kb-admin__error-actions">
            <Button type="button" variant="ghost" onClick={() => void refresh(true)}>
              Обновить
            </Button>
            <Button type="button" variant="ghost" onClick={() => setError('')}>
              Скрыть
            </Button>
          </div>
        </Card>
      )}

      {loading ? (
        <Card className="kb-admin-loading">Загрузка навыков…</Card>
      ) : (
        <div className="asst-admin-caps__grid" data-testid="capabilities-grid">
          {items.map((item) => (
            <Card key={item.code} className="asst-admin-cap-card" data-testid={`cap-${item.code}`}>
              <header>
                <div>
                  <strong>{item.name}</strong>
                  <p>{item.description}</p>
                </div>
                <StatusBadge status={item.enabled ? 'success' : 'neutral'}>
                  {item.enabled ? 'Вкл' : 'Выкл'}
                </StatusBadge>
              </header>
              <div className="asst-admin-cap-card__meta">
                <code>{item.code}</code>
                <span>→ {item.deep_link || '—'}</span>
              </div>
              <div className="asst-admin-actions">
                <Button
                  type="button"
                  variant={item.enabled ? 'secondary' : 'primary'}
                  disabled={!canEdit || busyCode === item.code}
                  data-testid={`cap-toggle-${item.code}`}
                  onClick={() => void toggle(item)}
                >
                  {item.enabled ? 'Выключить' : 'Включить'}
                </Button>
                {item.deep_link && item.deep_link !== 'capabilities' && (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => openAdminScreen(item.deep_link)}
                  >
                    Настроить →
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      <div className="asst-admin-task-skills__section">
        <h2>Навыки · промпты типа Task</h2>
        <p className="asst-admin-note">
          Capabilities с текстовыми инструкциями. Остальные — deep link на детальные экраны.
        </p>
        <SkillTaskPromptsPanel canEdit={canEdit} />
      </div>
    </section>
  )
}
