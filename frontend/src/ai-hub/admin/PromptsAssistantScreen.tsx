import { useEffect, useMemo, useState } from 'react'
import { ensureDevSession } from '../../auth/ensureDevSession'
import { Button, Card, StatusBadge } from '../../components'
import {
  createAssistantPrompt,
  deleteAssistantPrompt,
  listAssistantKbs,
  listAssistantPrompts,
  updateAssistantPrompt,
  type AssistantKb,
  type AssistantPrompt,
  type PromptStatus,
  type PromptType,
} from './api/assistantAdmin'
import './AssistantAdminScreens.css'

interface PromptsAssistantScreenProps {
  canEdit?: boolean
}

const TYPE_LABEL: Record<PromptType, string> = {
  system: 'Системный',
  task: 'Рабочий',
  scope: 'Область',
}

export function PromptsAssistantScreen({
  canEdit = true,
}: PromptsAssistantScreenProps) {
  const [prompts, setPrompts] = useState<AssistantPrompt[]>([])
  const [kbs, setKbs] = useState<AssistantKb[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [filter, setFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState<PromptType | ''>('')
  const [name, setName] = useState('')
  const [body, setBody] = useState('')
  const [promptType, setPromptType] = useState<PromptType>('task')
  const [scope, setScope] = useState('bank')
  const [kbSlug, setKbSlug] = useState('assistant_hr')
  const [previewQuery, setPreviewQuery] = useState('Как оформить отпуск?')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const selected = prompts.find((item) => item.id === selectedId) ?? null

  const filtered = useMemo(() => {
    return prompts.filter((item) => {
      if (typeFilter && item.prompt_type !== typeFilter) return false
      if (!filter.trim()) return true
      const q = filter.toLocaleLowerCase('ru-RU')
      return (
        item.name.toLocaleLowerCase('ru-RU').includes(q)
        || item.body.toLocaleLowerCase('ru-RU').includes(q)
      )
    })
  }, [prompts, filter, typeFilter])

  const load = async (preferId?: number | null) => {
    await ensureDevSession()
    const [nextPrompts, nextKbs] = await Promise.all([
      listAssistantPrompts(),
      listAssistantKbs(),
    ])
    setPrompts(nextPrompts)
    setKbs(nextKbs)
    const target = preferId ?? selectedId ?? nextPrompts[0]?.id ?? null
    setSelectedId(target)
    const current = nextPrompts.find((item) => item.id === target)
    if (current) {
      setName(current.name)
      setBody(current.body)
      setPromptType(current.prompt_type)
      setScope(current.scope)
      setKbSlug(current.kb_slug || nextKbs[0]?.slug || 'assistant_hr')
    }
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

  const selectPrompt = (item: AssistantPrompt) => {
    setSelectedId(item.id)
    setName(item.name)
    setBody(item.body)
    setPromptType(item.prompt_type)
    setScope(item.scope)
    setKbSlug(item.kb_slug || kbs[0]?.slug || '')
    setMessage('')
    setError('')
  }

  const saveDraft = async () => {
    if (!canEdit || !selected || busy) return
    setBusy(true)
    setError('')
    try {
      const updated = await updateAssistantPrompt(selected.id, {
        name,
        body,
        prompt_type: promptType,
        scope,
        kb_slug: kbSlug,
        status: 'draft',
      })
      setMessage(`Черновик сохранён · v${updated.version}`)
      await load(updated.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка сохранения')
    } finally {
      setBusy(false)
    }
  }

  const publish = async () => {
    if (!canEdit || !selected || busy) return
    setBusy(true)
    setError('')
    try {
      await updateAssistantPrompt(selected.id, {
        name,
        body,
        prompt_type: promptType,
        scope,
        kb_slug: kbSlug,
      })
      const published = await updateAssistantPrompt(selected.id, {
        status: 'published',
      })
      setMessage(`Опубликовано · v${published.version}`)
      await load(published.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка публикации')
    } finally {
      setBusy(false)
    }
  }

  const createPrompt = async () => {
    if (!canEdit || busy) return
    setBusy(true)
    setError('')
    try {
      const created = await createAssistantPrompt({
        name: 'Новый промпт',
        body: 'Опишите задачу ассистента…\n\nКонтекст: {{kb}}, {{user}}, {{dept}}',
        prompt_type: 'task',
        scope: 'bank',
        kb_slug: kbs[0]?.slug || 'assistant_hr',
      })
      setMessage('Промпт создан')
      await load(created.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка создания')
    } finally {
      setBusy(false)
    }
  }

  const removePrompt = async () => {
    if (!canEdit || !selected || busy) return
    setBusy(true)
    setError('')
    try {
      await deleteAssistantPrompt(selected.id)
      setMessage('Промпт удалён')
      await load(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка удаления')
    } finally {
      setBusy(false)
    }
  }

  const statusBadge = (status: PromptStatus) =>
    status === 'published' ? 'success' : 'warning'

  return (
    <section className="asst-admin-prompts" data-testid="prompts-assistant-screen">
      <div className="asst-admin-prompts__layout">
        <aside className="asst-admin-library" data-testid="prompt-library">
          <header>
            <strong>Библиотека</strong>
            <Button type="button" disabled={!canEdit || busy} onClick={() => void createPrompt()}>
              + Промпт
            </Button>
          </header>
          <input
            type="search"
            placeholder="Фильтр…"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            data-testid="prompt-filter"
          />
          <select
            value={typeFilter}
            onChange={(event) => setTypeFilter(event.target.value as PromptType | '')}
            aria-label="Тип промпта"
          >
            <option value="">Все типы</option>
            <option value="system">{TYPE_LABEL.system}</option>
            <option value="task">{TYPE_LABEL.task}</option>
            <option value="scope">{TYPE_LABEL.scope}</option>
          </select>
          <ul>
            {filtered.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className={item.id === selectedId ? 'is-active' : ''}
                  onClick={() => selectPrompt(item)}
                  data-testid={`prompt-item-${item.id}`}
                >
                  <span>{item.name}</span>
                  <small>
                    {TYPE_LABEL[item.prompt_type]} · v{item.version}
                  </small>
                </button>
              </li>
            ))}
          </ul>
          <p className="asst-admin-note">
            KB namespace: <code>assistant_*</code> · изолировано от <code>cc_production</code>
          </p>
        </aside>

        <div className="asst-admin-editor" data-testid="prompt-editor">
          <header>
            <div>
              <h2>Редактор</h2>
              <p>assistant_bank · плейсхолдеры {'{{kb}}'}, {'{{user}}'}, {'{{dept}}'}</p>
            </div>
            {selected ? (
              <StatusBadge status={statusBadge(selected.status)}>
                {selected.status} · v{selected.version}
              </StatusBadge>
            ) : null}
          </header>
          {!selected ? (
            <Card><p className="app-muted">Выберите промпт в библиотеке</p></Card>
          ) : (
            <div className="asst-admin-form">
              <label>
                Название
                <input
                  value={name}
                  disabled={!canEdit}
                  onChange={(event) => setName(event.target.value)}
                  data-testid="prompt-name"
                />
              </label>
              <div className="asst-admin-form__row">
                <label>
                  Тип
                  <select
                    value={promptType}
                    disabled={!canEdit}
                    onChange={(event) => setPromptType(event.target.value as PromptType)}
                  >
                    <option value="system">{TYPE_LABEL.system}</option>
                    <option value="task">{TYPE_LABEL.task}</option>
                    <option value="scope">{TYPE_LABEL.scope}</option>
                  </select>
                </label>
                <label>
                  Область
                  <select
                    value={scope}
                    disabled={!canEdit}
                    onChange={(event) => setScope(event.target.value)}
                  >
                    <option value="bank">Весь банк</option>
                    <option value="department">Подразделение</option>
                    <option value="security">ИБ</option>
                  </select>
                </label>
                <label>
                  KB (assistant_*)
                  <select
                    value={kbSlug}
                    disabled={!canEdit}
                    onChange={(event) => setKbSlug(event.target.value)}
                    data-testid="prompt-kb"
                  >
                    {kbs.map((kb) => (
                      <option key={kb.slug} value={kb.slug}>
                        {kb.slug}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <label>
                Текст промпта
                <textarea
                  rows={12}
                  value={body}
                  disabled={!canEdit}
                  onChange={(event) => setBody(event.target.value)}
                  data-testid="prompt-body"
                />
              </label>
              <div className="asst-admin-actions">
                <Button type="button" variant="secondary" disabled={!canEdit || busy} onClick={() => void saveDraft()}>
                  Сохранить черновик
                </Button>
                <Button type="button" disabled={!canEdit || busy} onClick={() => void publish()}>
                  Опубликовать
                </Button>
                <Button type="button" variant="ghost" disabled={!canEdit || busy} onClick={() => void removePrompt()}>
                  Удалить
                </Button>
              </div>
            </div>
          )}
        </div>

        <aside className="asst-admin-preview" data-testid="prompt-preview">
          <header>
            <strong>Просмотр</strong>
            <StatusBadge status="info">stub</StatusBadge>
          </header>
          <label>
            KB
            <select value={kbSlug} disabled>
              {kbs.map((kb) => (
                <option key={kb.slug} value={kb.slug}>{kb.slug}</option>
              ))}
            </select>
          </label>
          <label>
            Тестовый запрос
            <textarea
              rows={3}
              value={previewQuery}
              onChange={(event) => setPreviewQuery(event.target.value)}
            />
          </label>
          <Card>
            <p className="app-muted">Ответ (preview stub)</p>
            <p>
              По промпту «{selected?.name ?? '—'}» и KB <code>{kbSlug || 'assistant_*'}</code>:
              запрос принят. Источники только из namespace assistant_*.
            </p>
            <StatusBadge status="success">Регламент · 92%</StatusBadge>
          </Card>
          <Button type="button" variant="ghost" disabled>
            Отправить тест
          </Button>
        </aside>
      </div>
      {error ? <p className="asst-admin-error" role="alert">{error}</p> : null}
      {message ? <p className="asst-admin-ok" role="status">{message}</p> : null}
    </section>
  )
}
