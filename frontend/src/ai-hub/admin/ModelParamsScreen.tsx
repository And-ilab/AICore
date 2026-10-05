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
import { Button, Card, StatusBadge } from '../../components'
import {
  loadModelParams,
  ModelParamsApiError,
  saveModelParams,
  type ModelParamsData,
  type ModelParamsPayload,
  type ModelParamsPreset,
  type ModelParamsProfile,
} from './api/modelRegistry'
import type { AdminProfile } from './adminNav'

export interface ModelParamsScreenHandle {
  save: () => Promise<boolean>
  reset: () => void
}

interface ModelParamsScreenProps {
  profile: AdminProfile
  canEdit: boolean
  initialData?: ModelParamsData
  onStateChange: (state: {
    dirty: boolean
    valid: boolean
    saving: boolean
    message: string
  }) => void
}

type FieldErrors = Record<string, string>

const PRESET_LABELS: Record<ModelParamsPreset, string> = {
  short: 'Краткий',
  standard: 'По умолчанию',
  long: 'Подробнее',
}

const ASSISTANT_PRESETS: ModelParamsPreset[] = ['standard', 'long']

function apiProfile(profile: AdminProfile): ModelParamsProfile {
  return profile === 'cc' ? 'sufler_cc' : 'assistant_bank'
}

function formatLoadError(error: unknown): string {
  const message = error instanceof Error
    ? error.message
    : 'Не удалось загрузить настройки'
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

function editablePayload(data: ModelParamsData): ModelParamsPayload {
  return {
    generation: {
      temperature: data.generation.temperature,
      top_p: data.generation.top_p,
      max_tokens: data.generation.max_tokens,
      response_chars_max: data.generation.response_chars_max,
      preset: data.generation.preset === 'short' && data.profile === 'assistant_bank'
        ? 'standard'
        : (data.generation.preset || 'standard'),
    },
    rag: { ...data.rag },
  }
}

function validate(
  form: ModelParamsPayload,
  data: ModelParamsData,
): FieldErrors {
  const errors: FieldErrors = {}
  const temperature = data.constraints.temperature
  if (
    form.generation.temperature < temperature.min
    || form.generation.temperature > temperature.max
  ) {
    errors.temperature = `Допустимо: ${temperature.min}–${temperature.max}`
  }
  if (form.generation.top_p <= 0 || form.generation.top_p > 1) {
    errors.top_p = 'Значение должно быть больше 0 и не больше 1'
  }
  if (
    form.generation.max_tokens < 1
    || form.generation.max_tokens > data.constraints.max_tokens.max
  ) {
    errors.max_tokens = `Допустимо: 1–${data.constraints.max_tokens.max}`
  }
  const minChars = data.constraints.response_chars_max.min
  if (
    form.generation.response_chars_max < minChars
    || form.generation.response_chars_max > data.constraints.response_chars_max.max
  ) {
    errors.response_chars_max = `Допустимо: ${minChars}–${data.constraints.response_chars_max.max} символов`
  }
  if (!['short', 'standard', 'long'].includes(form.generation.preset)) {
    errors.preset = 'Выберите режим'
  }
  if (form.rag.chunk_size_tokens <= 0) {
    errors.chunk_size_tokens = 'Размер фрагмента должен быть положительным'
  }
  if (
    form.rag.chunk_overlap_tokens < 0
    || form.rag.chunk_overlap_tokens >= form.rag.chunk_size_tokens
  ) {
    errors.chunk_overlap_tokens = 'Overlap должен быть меньше chunk size'
  }
  for (const [field, value] of [
    ['context_inclusion', form.rag.context_inclusion],
    ['deterministic_answer', form.rag.deterministic_answer],
  ] as const) {
    if (value < 0 || value > 1) {
      errors[field] = 'Порог должен быть от 0 до 100%'
    }
  }
  if (form.rag.context_inclusion > form.rag.deterministic_answer) {
    errors.deterministic_answer = 'Не может быть ниже порога включения'
  }
  return errors
}

function openAdminScreen(path: string) {
  window.history.pushState({}, '', path)
  window.dispatchEvent(new PopStateEvent('popstate'))
  window.location.assign(path)
}

function toPercent(ratio: number): number {
  return Math.round(ratio * 100)
}

function fromPercent(percent: number): number {
  return Math.min(1, Math.max(0, percent / 100))
}

export const ModelParamsScreen = forwardRef<
  ModelParamsScreenHandle,
  ModelParamsScreenProps
>(({ profile, canEdit, initialData, onStateChange }, ref) => {
  const selectedProfile = apiProfile(profile)
  const [data, setData] = useState<ModelParamsData | null>(null)
  const [form, setForm] = useState<ModelParamsPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [serverErrors, setServerErrors] = useState<FieldErrors>({})
  const [message, setMessage] = useState('')

  const loadSettings = useCallback(async () => {
    if (initialData && initialData.profile === selectedProfile) {
      setData(initialData)
      setForm(editablePayload(initialData))
      setLoading(false)
      setLoadError('')
      return
    }
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
      const loaded = await withDevSession(() => loadModelParams(selectedProfile))
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
  }, [initialData, selectedProfile])

  useEffect(() => {
    void loadSettings()
  }, [loadSettings])

  const clientErrors = useMemo(
    () => form && data ? validate(form, data) : {},
    [data, form],
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
      const saved = await withDevSession(
        () => saveModelParams(selectedProfile, form),
      )
      setData(saved)
      setForm(editablePayload(saved))
      setMessage(`Сохранено · ревизия ${saved.revision}`)
      return true
    } catch (error) {
      if (error instanceof ModelParamsApiError) {
        if (isAuthErrorMessage(error.message)) {
          setMessage(formatLoadError(error))
        } else {
          setServerErrors(
            Object.fromEntries(
              Object.entries(error.details).map(([field, values]) => [
                field.replace('_threshold', ''),
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

  const resetToPlatform = async () => {
    if (!data || !canEdit) return
    const defaults = data.platform_defaults
    if (!defaults) {
      setMessage('Дефолты платформы недоступны')
      return
    }
    setServerErrors({})
    setForm({
      generation: {
        temperature: defaults.temperature,
        top_p: defaults.top_p,
        max_tokens: defaults.max_tokens,
        response_chars_max: defaults.response_chars_max,
        preset: defaults.preset || 'standard',
      },
      rag: {
        chunk_size_tokens: defaults.chunk_size_tokens,
        chunk_overlap_tokens: defaults.chunk_overlap_tokens,
        context_inclusion: defaults.context_inclusion_threshold,
        deterministic_answer: defaults.deterministic_answer_threshold,
      },
    })
    setMessage('Подставлены дефолты платформы — нажмите «Сохранить»')
  }

  useImperativeHandle(ref, () => ({ save, reset }))

  if (loading) {
    return <Card className="model-params-loading" aria-busy="true">Загрузка параметров модели…</Card>
  }
  if (loadError || !data || !form) {
    return (
      <Card className="model-params-error" role="alert">
        <strong>Реестр моделей недоступен</strong>
        <span>{loadError || 'Пустой ответ API'}</span>
        <div>
          <Button variant="ghost" onClick={() => void loadSettings()}>
            Повторить
          </Button>
        </div>
      </Card>
    )
  }

  const setGeneration = <K extends keyof ModelParamsPayload['generation']>(
    field: K,
    value: ModelParamsPayload['generation'][K],
  ) => {
    setServerErrors({})
    setForm((current) => current && ({
      ...current,
      generation: { ...current.generation, [field]: value },
    }))
  }

  const setRag = (
    field: keyof ModelParamsPayload['rag'],
    value: number,
  ) => {
    setServerErrors({})
    setForm((current) => current && ({
      ...current,
      rag: { ...current.rag, [field]: value },
    }))
  }

  const applyPreset = (preset: ModelParamsPreset) => {
    const values = data.presets?.[preset]?.values
    setServerErrors({})
    setForm((current) => {
      if (!current) return current
      return {
        ...current,
        generation: {
          ...current.generation,
          preset,
          temperature: values?.temperature ?? current.generation.temperature,
          top_p: values?.top_p ?? current.generation.top_p,
          max_tokens: values?.max_tokens ?? current.generation.max_tokens,
          response_chars_max:
            values?.response_chars_max ?? current.generation.response_chars_max,
        },
      }
    })
  }

  const isCc = selectedProfile === 'sufler_cc'

  return (
    <div className="model-params" data-testid="model-params-form">
      <div className="model-params__profile-switch" role="tablist" aria-label="Профиль параметров">
        <button
          type="button"
          role="tab"
          aria-selected={!isCc}
          className={!isCc ? 'is-active' : undefined}
          onClick={() => openAdminScreen('/ai-hub/admin/model_params')}
        >
          Ассистент
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={isCc}
          className={isCc ? 'is-active' : undefined}
          onClick={() => openAdminScreen('/ai-hub/admin/model_params/cc')}
        >
          КЦ (sufler_cc)
        </button>
        <StatusBadge status="info">
          {isCc ? 'Профиль sufler_cc' : 'Профиль assistant_bank'}
        </StatusBadge>
      </div>

      <div className="model-params__columns">
        <section className="model-params__column" aria-label="Генерация">
          <h2>Генерация</h2>
          <label className={errors.temperature ? 'model-params__row model-params__row--error' : 'model-params__row'}>
            <span>Температура</span>
            <input
              type="number"
              aria-label="Температура"
              min={data.constraints.temperature.min}
              max={data.constraints.temperature.max}
              step={data.constraints.temperature.step}
              value={form.generation.temperature}
              disabled={!canEdit}
              onChange={(event) => setGeneration('temperature', Number(event.target.value))}
            />
            {errors.temperature && <small role="alert">{errors.temperature}</small>}
          </label>
          <label className={errors.response_chars_max ? 'model-params__row model-params__row--max model-params__row--error' : 'model-params__row model-params__row--max'}>
            <span>Max ответа</span>
            <div className="model-params__max-field">
              <input
                type="number"
                aria-label="Max ответа"
                min={data.constraints.response_chars_max.min}
                max={data.constraints.response_chars_max.max}
                step={1}
                value={form.generation.response_chars_max}
                disabled={!canEdit}
                data-testid="model-params-max-response"
                onChange={(event) => setGeneration('response_chars_max', Number(event.target.value))}
              />
              <button
                type="button"
                className="model-params__default-btn"
                disabled={!canEdit}
                data-testid="model-params-max-default"
                onClick={() => {
                  const fallback = (
                    data.presets?.standard?.values?.response_chars_max
                    ?? data.platform_defaults?.response_chars_max
                    ?? 1200
                  )
                  setGeneration('response_chars_max', fallback)
                }}
              >
                По умолчанию
              </button>
            </div>
            {errors.response_chars_max && <small role="alert">{errors.response_chars_max}</small>}
          </label>
          <div className={errors.preset ? 'model-params__row model-params__row--preset model-params__row--error' : 'model-params__row model-params__row--preset'}>
            <span>Preset</span>
            {isCc ? (
              <select
                aria-label="Preset параметров"
                value={form.generation.preset}
                disabled={!canEdit}
                data-testid="model-params-preset"
                onChange={(event) => applyPreset(event.target.value as ModelParamsPreset)}
              >
                {(Object.keys(PRESET_LABELS) as ModelParamsPreset[]).map((key) => (
                  <option key={key} value={key}>
                    {data.presets?.[key]?.label ?? PRESET_LABELS[key]}
                  </option>
                ))}
              </select>
            ) : (
              <div className="model-params__preset" role="group" aria-label="Preset параметров">
                {ASSISTANT_PRESETS.map((key) => {
                  const active = (
                    key === 'standard'
                      ? form.generation.preset !== 'long'
                      : form.generation.preset === 'long'
                  )
                  return (
                    <button
                      key={key}
                      type="button"
                      className={active ? 'is-active' : undefined}
                      disabled={!canEdit}
                      data-testid={`model-params-preset-${key}`}
                      onClick={() => setGeneration('preset', key)}
                    >
                      {data.presets?.[key]?.label ?? PRESET_LABELS[key]}
                    </button>
                  )
                })}
              </div>
            )}
            {errors.preset && <small role="alert">{errors.preset}</small>}
          </div>
        </section>

        <section className="model-params__column" aria-label="RAG / индексация">
          <h2>RAG / индексация</h2>
          <label className={errors.chunk_size_tokens ? 'model-params__row model-params__row--error' : 'model-params__row'}>
            <span>Chunk size</span>
            <input
              type="number"
              aria-label="Chunk size"
              value={form.rag.chunk_size_tokens}
              disabled={!canEdit}
              onChange={(event) => setRag('chunk_size_tokens', Number(event.target.value))}
            />
            {errors.chunk_size_tokens && <small role="alert">{errors.chunk_size_tokens}</small>}
          </label>
          <label className={errors.chunk_overlap_tokens ? 'model-params__row model-params__row--error' : 'model-params__row'}>
            <span>Overlap</span>
            <input
              type="number"
              aria-label="Overlap"
              value={form.rag.chunk_overlap_tokens}
              disabled={!canEdit}
              onChange={(event) => setRag('chunk_overlap_tokens', Number(event.target.value))}
            />
            {errors.chunk_overlap_tokens && <small role="alert">{errors.chunk_overlap_tokens}</small>}
          </label>
          <label className={errors.context_inclusion ? 'model-params__row model-params__row--error' : 'model-params__row'}>
            <span>Порог в контекст</span>
            <input
              type="number"
              aria-label="Порог в контекст"
              min={0}
              max={100}
              step={1}
              value={toPercent(form.rag.context_inclusion)}
              disabled={!canEdit}
              data-testid="model-params-context-threshold"
              onChange={(event) => setRag('context_inclusion', fromPercent(Number(event.target.value)))}
            />
            <em>%</em>
            {errors.context_inclusion && <small role="alert">{errors.context_inclusion}</small>}
          </label>
          <label className={errors.deterministic_answer ? 'model-params__row model-params__row--error' : 'model-params__row'}>
            <span>Детерм. из БЗ</span>
            <input
              type="number"
              aria-label="Детерминированный ответ из БЗ"
              min={0}
              max={100}
              step={1}
              value={toPercent(form.rag.deterministic_answer)}
              disabled={!canEdit}
              data-testid="model-params-deterministic"
              onChange={(event) => setRag('deterministic_answer', fromPercent(Number(event.target.value)))}
            />
            <em>%</em>
            {errors.deterministic_answer && <small role="alert">{errors.deterministic_answer}</small>}
          </label>
        </section>

        <section className="model-params__column model-params__column--readonly" aria-label="Read-only">
          <h2>Read-only</h2>
          <Card>
            <span>Контекстное окно</span>
            <strong>{data.read_only.context_window ?? '≥8200'}</strong>
          </Card>
          <Card>
            <span>Модель LLM</span>
            <strong>{data.read_only.llm_model_label ?? data.read_only.dev_model ?? '—'}</strong>
          </Card>
        </section>
      </div>

      <Card className="model-params__callout" role="note">
        Порог понимания запросов настраивается в разделе «Понимание запросов».
      </Card>

      <div className="model-params__actions">
        <Button
          type="button"
          variant="secondary"
          disabled={!canEdit || saving}
          onClick={() => void resetToPlatform()}
          data-testid="model-params-reset-platform"
        >
          Сброс к дефолту платформы
        </Button>
        <Button
          type="button"
          disabled={!canEdit || saving || !dirty || !valid}
          onClick={() => void save()}
          data-testid="model-params-save"
        >
          {saving ? 'Сохранение…' : 'Сохранить'}
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={() => openAdminScreen('/ai-hub/admin/qu_admin')}
          data-testid="model-params-test"
        >
          Тест с параметрами
        </Button>
      </div>

      {message && (
        <p className="model-params__message" role="status">{message}</p>
      )}
    </div>
  )
})

ModelParamsScreen.displayName = 'ModelParamsScreen'
