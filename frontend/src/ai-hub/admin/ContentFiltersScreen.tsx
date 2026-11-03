import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useState,
} from 'react'
import {
  ensureDevSession,
  isAuthErrorMessage,
  resetDevSessionCache,
} from '../../auth/ensureDevSession'
import { Button, Card } from '../../components'
import {
  ContentFiltersApiError,
  loadContentFilters,
  saveContentFilters,
  type ContentFilterCatalog,
  type ContentFilterItem,
  type ContentFilterPayload,
} from './api/contentFilters'

export interface ContentFiltersScreenHandle {
  save: () => Promise<boolean>
  reset: () => void
}

interface ContentFiltersScreenProps {
  canEdit: boolean
  onStateChange: (state: {
    dirty: boolean
    valid: boolean
    saving: boolean
    message: string
  }) => void
}

interface FilterFormItem {
  code: string
  name: string
  enabled: boolean
  keywords: string
  exceptions: string
  refusal_text: string
}

type FieldErrors = Record<string, string>

const DEFAULT_REFUSAL = 'Не могу ответить на этот запрос: тема ограничена фильтром контента.'

function splitLines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
}

function joinLines(values: readonly string[]): string {
  return values.join('\n')
}

function toForm(items: readonly ContentFilterItem[]): FilterFormItem[] {
  return items.map((item) => ({
    code: item.code,
    name: item.name,
    enabled: item.enabled,
    keywords: joinLines(item.keywords),
    exceptions: joinLines(item.exceptions),
    refusal_text: item.refusal_text,
  }))
}

function toPayload(items: readonly FilterFormItem[]): ContentFilterPayload {
  return {
    items: items.map((item, index) => ({
      code: item.code.trim().toLowerCase(),
      name: item.name.trim(),
      enabled: item.enabled,
      keywords: splitLines(item.keywords),
      exceptions: splitLines(item.exceptions),
      refusal_text: item.refusal_text.trim(),
      sort_order: index * 10,
    })),
  }
}

function validate(items: readonly FilterFormItem[]): FieldErrors {
  const errors: FieldErrors = {}
  const seen = new Set<string>()
  items.forEach((item, index) => {
    const code = item.code.trim().toLowerCase()
    if (!/^[a-z][a-z0-9_]{0,31}$/.test(code)) {
      errors[`items.${index}.code`] = 'Код: латиница, цифры и _, с буквы'
    } else if (seen.has(code)) {
      errors[`items.${index}.code`] = 'Код категории повторяется'
    }
    seen.add(code)
    if (!item.name.trim() || item.name.trim().length > 80) {
      errors[`items.${index}.name`] = 'Название: от 1 до 80 символов'
    }
    if (item.enabled && splitLines(item.keywords).length === 0) {
      errors[`items.${index}.keywords`] = 'Добавьте хотя бы одно слово или фразу'
    }
    if (!item.refusal_text.trim()) {
      errors[`items.${index}.refusal_text`] = 'Укажите текст отказа'
    }
  })
  return errors
}

function formatLoadError(error: unknown): string {
  const message = error instanceof Error
    ? error.message
    : 'Не удалось загрузить фильтры контента'
  if (isAuthErrorMessage(message)) {
    return 'Нет сессии авторизации. В DEV выполняется вход как dev-role-01; проверьте, что API доступен.'
  }
  return message
}

async function withDevSession<T>(action: () => Promise<T>): Promise<T> {
  await ensureDevSession()
  try {
    return await action()
  } catch (error) {
    const message = error instanceof Error ? error.message : ''
    if (!isAuthErrorMessage(message)) throw error
    resetDevSessionCache()
    const ok = await ensureDevSession()
    if (!ok) throw error
    return action()
  }
}

export const ContentFiltersScreen = forwardRef<
  ContentFiltersScreenHandle,
  ContentFiltersScreenProps
>(({ canEdit, onStateChange }, ref) => {
  const [data, setData] = useState<ContentFilterCatalog | null>(null)
  const [form, setForm] = useState<FilterFormItem[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [serverErrors, setServerErrors] = useState<FieldErrors>({})
  const [message, setMessage] = useState('')

  const loadSettings = useCallback(async () => {
    setLoading(true)
    setLoadError('')
    try {
      resetDevSessionCache()
      const ok = await ensureDevSession()
      if (!ok) {
        setLoadError(
          'Нет сессии авторизации. В DEV выполняется вход как dev-role-01; проверьте, что API доступен.',
        )
        setData(null)
        setForm(null)
        return
      }
      const loaded = await withDevSession(() => loadContentFilters())
      setData(loaded)
      setForm(toForm(loaded.items))
      setMessage('')
    } catch (error: unknown) {
      setLoadError(formatLoadError(error))
      setData(null)
      setForm(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadSettings()
  }, [loadSettings])

  const clientErrors = useMemo(
    () => (form ? validate(form) : {}),
    [form],
  )
  const errors = { ...serverErrors, ...clientErrors }
  const dirty = Boolean(
    data
    && form
    && JSON.stringify(toPayload(form)) !== JSON.stringify(toPayload(toForm(data.items))),
  )
  const valid = Boolean(form && data && Object.keys(errors).length === 0)

  useEffect(() => {
    onStateChange({ dirty, valid, saving, message })
  }, [dirty, message, onStateChange, saving, valid])

  const save = async (): Promise<boolean> => {
    if (!form || !data || !canEdit || !valid) return false
    setSaving(true)
    setServerErrors({})
    setMessage('')
    try {
      const saved = await withDevSession(() => saveContentFilters(toPayload(form)))
      setData(saved)
      setForm(toForm(saved.items))
      setMessage('Фильтры контента сохранены')
      return true
    } catch (error) {
      if (error instanceof ContentFiltersApiError) {
        if (isAuthErrorMessage(error.message)) {
          setMessage(formatLoadError(error))
        } else {
          setServerErrors(
            Object.fromEntries(
              Object.entries(error.details).map(([field, values]) => [
                field,
                values.join(' '),
              ]),
            ),
          )
          setMessage('Исправьте ошибки формы')
        }
      } else {
        setMessage(formatLoadError(error))
      }
      return false
    } finally {
      setSaving(false)
    }
  }

  const reset = () => {
    if (!data) return
    setForm(toForm(data.items))
    setServerErrors({})
    setMessage('')
  }

  useImperativeHandle(ref, () => ({ save, reset }))

  if (loading) {
    return (
      <Card className="model-params-loading" aria-busy="true">
        Загрузка фильтров контента…
      </Card>
    )
  }
  if (loadError || !data || !form) {
    return (
      <Card className="model-params-error" role="alert">
        <strong>Фильтры контента недоступны</strong>
        <span>{loadError || 'Пустой ответ API'}</span>
        <div>
          <Button variant="ghost" onClick={() => void loadSettings()}>
            Повторить
          </Button>
        </div>
      </Card>
    )
  }

  const update = (index: number, patch: Partial<FilterFormItem>) => {
    setServerErrors({})
    setForm((current) => current?.map((item, itemIndex) => (
      itemIndex === index ? { ...item, ...patch } : item
    )) ?? null)
  }

  return (
    <div className="content-filters" data-testid="content-filters-form">
      <p className="content-filters__intro">
        Словарь срабатывает до поиска по базе знаний и отвечает готовой фразой.
        Если слова нет, ассистент всё равно получает список включённых тем.
        Вопросы про кредитную или тарифную политику банка в исключениях и не блокируются.
        Суфлёр эти фильтры не использует.
      </p>
      {form.map((item, index) => (
        <Card key={`${item.code || 'new'}-${index}`} className="content-filters__card">
          <div className="content-filters__head">
            <label>
              <input
                type="checkbox"
                checked={item.enabled}
                disabled={!canEdit}
                aria-label={`Включено: ${item.name || 'новая категория'}`}
                onChange={(event) => update(index, { enabled: event.target.checked })}
              />
              <span>{item.name || 'Новая категория'}</span>
            </label>
            <Button
              variant="ghost"
              disabled={!canEdit}
              onClick={() => setForm((current) => current?.filter((_, itemIndex) => itemIndex !== index) ?? null)}
            >
              Удалить
            </Button>
          </div>
          <div className="content-filters__grid">
            <label>
              <span>Название</span>
              <input
                aria-label={`Название ${index + 1}`}
                value={item.name}
                disabled={!canEdit}
                onChange={(event) => update(index, { name: event.target.value })}
              />
              {errors[`items.${index}.name`] && (
                <small className="content-filters__error" role="alert">
                  {errors[`items.${index}.name`]}
                </small>
              )}
            </label>
            <label>
              <span>Код</span>
              <input
                aria-label={`Код ${index + 1}`}
                value={item.code}
                disabled={!canEdit}
                onChange={(event) => update(index, { code: event.target.value })}
              />
              {errors[`items.${index}.code`] && (
                <small className="content-filters__error" role="alert">
                  {errors[`items.${index}.code`]}
                </small>
              )}
            </label>
            <label>
              <span>Слова и фразы</span>
              <textarea
                aria-label={`Слова ${index + 1}`}
                rows={5}
                value={item.keywords}
                disabled={!canEdit}
                onChange={(event) => update(index, { keywords: event.target.value })}
              />
              {errors[`items.${index}.keywords`] && (
                <small className="content-filters__error" role="alert">
                  {errors[`items.${index}.keywords`]}
                </small>
              )}
            </label>
            <label>
              <span>Исключения</span>
              <textarea
                aria-label={`Исключения ${index + 1}`}
                rows={5}
                value={item.exceptions}
                disabled={!canEdit}
                onChange={(event) => update(index, { exceptions: event.target.value })}
              />
              {errors[`items.${index}.exceptions`] && (
                <small className="content-filters__error" role="alert">
                  {errors[`items.${index}.exceptions`]}
                </small>
              )}
            </label>
            <label className="content-filters__wide">
              <span>Текст отказа</span>
              <textarea
                aria-label={`Отказ ${index + 1}`}
                rows={2}
                value={item.refusal_text}
                disabled={!canEdit}
                onChange={(event) => update(index, { refusal_text: event.target.value })}
              />
              {errors[`items.${index}.refusal_text`] && (
                <small className="content-filters__error" role="alert">
                  {errors[`items.${index}.refusal_text`]}
                </small>
              )}
            </label>
          </div>
        </Card>
      ))}
      <div>
        <Button
          variant="ghost"
          disabled={!canEdit}
          onClick={() => setForm((current) => [
            ...(current ?? []),
            {
              code: '',
              name: '',
              enabled: true,
              keywords: '',
              exceptions: '',
              refusal_text: DEFAULT_REFUSAL,
            },
          ])}
        >
          Добавить
        </Button>
      </div>
      {message && (
        <p className="model-params__message" role="status">{message}</p>
      )}
    </div>
  )
})

ContentFiltersScreen.displayName = 'ContentFiltersScreen'
