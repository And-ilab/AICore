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
  loadSuflerPolicies,
  saveSuflerPolicies,
  SuflerPoliciesApiError,
  type SuflerPolicyData,
  type SuflerPolicyMode,
  type SuflerPolicyPayload,
} from './api/suflerPolicies'

export interface SuflerPoliciesScreenHandle {
  save: () => Promise<boolean>
  reset: () => void
}

interface SuflerPoliciesScreenProps {
  canEdit: boolean
  onStateChange: (state: {
    dirty: boolean
    valid: boolean
    saving: boolean
    message: string
  }) => void
}

type FieldErrors = Record<string, string>

function formatLoadError(error: unknown): string {
  const message = error instanceof Error
    ? error.message
    : 'Не удалось загрузить политики суфлёра'
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

function editablePayload(data: SuflerPolicyData): SuflerPolicyPayload {
  return {
    telephony_min_relevance_percent: data.telephony_min_relevance_percent,
    clarify_min_relevance_percent: data.clarify_min_relevance_percent,
    max_hints: data.max_hints,
    default_mode: data.default_mode,
  }
}

function validate(form: SuflerPolicyPayload): FieldErrors {
  const errors: FieldErrors = {}
  for (const [field, label] of [
    ['telephony_min_relevance_percent', 'Порог подсказки'],
    ['clarify_min_relevance_percent', 'Порог уточнения'],
  ] as const) {
    const value = form[field]
    if (!Number.isFinite(value) || value < 0 || value > 100) {
      errors[field] = `${label}: допустимо 0–100%`
    }
  }
  if (!Number.isInteger(form.max_hints) || form.max_hints < 1 || form.max_hints > 5) {
    errors.max_hints = 'На реплику допускается от 1 до 5 подсказок'
  }
  if (form.default_mode !== 'consultation' && form.default_mode !== 'service') {
    errors.default_mode = 'Выберите консультацию или услугу'
  }
  if (form.clarify_min_relevance_percent > form.telephony_min_relevance_percent) {
    errors.clarify_min_relevance_percent =
      'Порог уточнения не может быть выше порога подсказки'
  }
  return errors
}

export const SuflerPoliciesScreen = forwardRef<
  SuflerPoliciesScreenHandle,
  SuflerPoliciesScreenProps
>(({ canEdit, onStateChange }, ref) => {
  const [data, setData] = useState<SuflerPolicyData | null>(null)
  const [form, setForm] = useState<SuflerPolicyPayload | null>(null)
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
      const loaded = await withDevSession(() => loadSuflerPolicies())
      setData(loaded)
      setForm(editablePayload(loaded))
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
    data && form && JSON.stringify(form) !== JSON.stringify(editablePayload(data)),
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
      const saved = await withDevSession(() => saveSuflerPolicies(form))
      setData(saved)
      setForm(editablePayload(saved))
      setMessage('Политики суфлёра сохранены')
      return true
    } catch (error) {
      if (error instanceof SuflerPoliciesApiError) {
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
    setForm(editablePayload(data))
    setServerErrors({})
    setMessage('')
  }

  useImperativeHandle(ref, () => ({ save, reset }))

  if (loading) {
    return (
      <Card className="model-params-loading" aria-busy="true">
        Загрузка политик суфлёра…
      </Card>
    )
  }
  if (loadError || !data || !form) {
    return (
      <Card className="model-params-error" role="alert">
        <strong>Политики суфлёра недоступны</strong>
        <span>{loadError || 'Пустой ответ API'}</span>
        <div>
          <Button variant="ghost" onClick={() => void loadSettings()}>
            Повторить
          </Button>
        </div>
      </Card>
    )
  }

  const setField = <K extends keyof SuflerPolicyPayload>(
    field: K,
    value: SuflerPolicyPayload[K],
  ) => {
    setServerErrors({})
    setForm((current) => current && ({ ...current, [field]: value }))
  }

  const percentRow = (
    field: 'telephony_min_relevance_percent' | 'clarify_min_relevance_percent',
    label: string,
    hint: string,
  ) => (
    <label
      className={errors[field] ? 'model-params__row model-params__row--error' : 'model-params__row'}
      title={hint}
    >
      <span>{label}</span>
      <input
        type="number"
        aria-label={label}
        min={0}
        max={100}
        step={1}
        value={form[field]}
        disabled={!canEdit}
        onChange={(event) => setField(field, Number(event.target.value))}
      />
      <em>%</em>
      {errors[field] && <small role="alert">{errors[field]}</small>}
    </label>
  )

  return (
    <div className="sufler-policies model-params" data-testid="sufler-policies-form">
      <div className="model-params__columns sufler-policies__columns">
        <section className="model-params__column" aria-label="Пороги релевантности">
          <h2>Пороги подсказки</h2>
          {percentRow(
            'telephony_min_relevance_percent',
            'Порог подсказки',
            'Минимальная релевантность карточки для оператора',
          )}
          {percentRow(
            'clarify_min_relevance_percent',
            'Уточняющие варианты',
            'Не выше порога подсказки',
          )}
        </section>

        <section className="model-params__column" aria-label="Выдача и режим">
          <h2>Выдача оператору</h2>
          <label className={errors.max_hints ? 'model-params__row model-params__row--error' : 'model-params__row'}>
            <span>Макс. карточек</span>
            <select
              aria-label="Макс. карточек"
              value={form.max_hints}
              disabled={!canEdit}
              onChange={(event) => setField('max_hints', Number(event.target.value))}
            >
              <option value={1}>1</option>
              <option value={2}>2</option>
              <option value={3}>3</option>
              <option value={4}>4</option>
              <option value={5}>5</option>
            </select>
            {errors.max_hints && <small role="alert">{errors.max_hints}</small>}
          </label>
          <label className={errors.default_mode ? 'model-params__row model-params__row--error' : 'model-params__row'}>
            <span>Режим по умолчанию</span>
            <select
              aria-label="Режим по умолчанию"
              value={form.default_mode}
              disabled={!canEdit}
              onChange={(event) => setField('default_mode', event.target.value as SuflerPolicyMode)}
            >
              <option value="consultation">Консультация</option>
              <option value="service">Услуга</option>
            </select>
            {errors.default_mode && <small role="alert">{errors.default_mode}</small>}
          </label>
        </section>
      </div>

      {message && (
        <p className="model-params__message" role="status">{message}</p>
      )}
    </div>
  )
})

SuflerPoliciesScreen.displayName = 'SuflerPoliciesScreen'
