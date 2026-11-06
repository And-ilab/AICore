import { useCallback, useEffect, useState } from 'react'
import { Button, Card, StatusBadge, type StatusBadgeStatus } from '../../components'
import {
  checkLlmConfig,
  loadLlmConfig,
  LlmConfigApiError,
  type LlmConfigCheckResult,
  type LlmConfigLayer,
  type LlmConfigLayerStatus,
  type LlmConfigProfile,
} from './api/llmConfig'

interface LlmConfigScreenProps {
  profile: LlmConfigProfile
  canEdit: boolean
  onOpen: (href: string) => void
  /** Storybook layout. The live admin always loads the dashboard from the API. */
  previewLayers?: readonly LlmConfigLayer[]
}

const STATUS_LABEL: Record<LlmConfigLayerStatus, string> = {
  ok: 'Готово',
  attention: 'Внимание',
  not_configured: 'Не настроено',
  not_run: 'Не запускалась',
}

function badgeStatus(status: LlmConfigLayerStatus): StatusBadgeStatus {
  if (status === 'ok') return 'success'
  if (status === 'attention') return 'warning'
  if (status === 'not_configured') return 'danger'
  return 'neutral'
}

function errorText(error: unknown): { message: string; requestId: string } {
  if (error instanceof LlmConfigApiError) {
    return { message: error.message, requestId: error.requestId }
  }
  return { message: 'Не удалось выполнить запрос. Попробуйте ещё раз.', requestId: '' }
}

export function LlmConfigScreen({
  profile,
  canEdit,
  onOpen,
  previewLayers,
}: LlmConfigScreenProps) {
  const [layers, setLayers] = useState<readonly LlmConfigLayer[]>(previewLayers ?? [])
  const [loading, setLoading] = useState(!previewLayers)
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState('')
  const [requestId, setRequestId] = useState('')
  const [result, setResult] = useState<LlmConfigCheckResult | null>(null)

  const load = useCallback(async () => {
    if (previewLayers) {
      setLayers(previewLayers)
      setLoading(false)
      return
    }
    setLoading(true)
    setError('')
    setRequestId('')
    try {
      const dashboard = await loadLlmConfig(profile)
      setLayers(dashboard.layers)
    } catch (caught) {
      const parsed = errorText(caught)
      setError(parsed.message)
      setRequestId(parsed.requestId)
    } finally {
      setLoading(false)
    }
  }, [previewLayers, profile])

  useEffect(() => {
    setResult(null)
    void load()
  }, [load])

  const runCheck = async () => {
    if (previewLayers) {
      setError('В макете запрос к модели не отправляется.')
      return
    }
    setChecking(true)
    setError('')
    setRequestId('')
    try {
      const check = await checkLlmConfig(profile)
      setResult(check)
      setLayers(check.layers)
    } catch (caught) {
      const parsed = errorText(caught)
      setError(parsed.message)
      setRequestId(parsed.requestId)
      setResult(null)
    } finally {
      setChecking(false)
    }
  }

  return (
    <section className="llm-config" data-testid="llm-config-screen">
      {loading ? <p>Загрузка конфигурации…</p> : null}
      {error ? (
        <p className="llm-config__error" role="alert">
          {error}
          {requestId ? <small> Код запроса: {requestId}</small> : null}
        </p>
      ) : null}
      <div className="llm-config-layers">
        {layers.map((layer) => (
          <Card key={layer.id} className="llm-config-layer">
            <div>
              <strong>{layer.index}. {layer.title}</strong>
              <p>{layer.summary}</p>
            </div>
            <div className="llm-config-layer__aside">
              <StatusBadge status={badgeStatus(layer.status)}>
                {STATUS_LABEL[layer.status] ?? layer.status}
              </StatusBadge>
              {layer.href ? (
                <Button
                  variant="ghost"
                  onClick={() => onOpen(layer.href)}
                >
                  Настроить
                </Button>
              ) : null}
            </div>
          </Card>
        ))}
      </div>
      <div className="llm-config-actions">
        <Button
          disabled={!canEdit || loading || checking}
          onClick={() => { void runCheck() }}
        >
          {checking ? 'Проверка…' : 'Проверить конфигурацию'}
        </Button>
      </div>
      {result ? (
        <Card className="llm-config-result">
          <StatusBadge status={result.passed ? 'success' : 'warning'}>
            {result.passed ? 'Проверка пройдена' : 'Конфигурация ещё не готова'}
          </StatusBadge>
          {result.model ? <p>Модель: {result.model}</p> : null}
          {result.answer ? <p className="llm-config-answer">{result.answer}</p> : null}
        </Card>
      ) : null}
    </section>
  )
}

export const LLM_CONFIG_PREVIEW_LAYERS: readonly LlmConfigLayer[] = [
  {
    id: 'model_params',
    index: 0,
    title: 'Параметры модели',
    status: 'ok',
    summary: 'Параметры профиля сохранены.',
    href: '/ai-hub/admin/model_params',
  },
  {
    id: 'prompts',
    index: 1,
    title: 'Промпты',
    status: 'ok',
    summary: 'Есть опубликованный промпт.',
    href: '/ai-hub/admin/prompts_assistant',
  },
  {
    id: 'capabilities',
    index: 2,
    title: 'Навыки',
    status: 'attention',
    summary: 'Все навыки выключены.',
    href: '/ai-hub/admin/capabilities',
  },
  {
    id: 'knowledge',
    index: 3,
    title: 'Базы знаний',
    status: 'ok',
    summary: 'Есть готовая база знаний.',
    href: '/ai-hub/admin/kb_admin',
  },
  {
    id: 'understanding',
    index: 4,
    title: 'Понимание запросов',
    status: 'ok',
    summary: 'Есть активный пример.',
    href: '/ai-hub/admin/qu_admin',
  },
  {
    id: 'guardrails',
    index: 5,
    title: 'Фильтры контента',
    status: 'ok',
    summary: 'Есть включённый фильтр.',
    href: '/ai-hub/admin/content_filters',
  },
  {
    id: 'test',
    index: 6,
    title: 'Проверка',
    status: 'not_run',
    summary: 'Проверка ещё не запускалась.',
    href: '',
  },
]
