function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

export interface LocalLlmModel {
  id: string
  label: string
  description?: string
  available?: boolean
}

export interface LocalLlmStatus {
  active_model_id: string | null
  switching: boolean
  llama_running: boolean
  manager_reachable?: boolean
  openai_alias?: string
  models: LocalLlmModel[]
  last_error?: string | null
}

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as {
      details?: string | { model_id?: string[] }
      error?: string
    }
    if (typeof payload.details === 'string') return payload.details
    if (payload.details && typeof payload.details === 'object') {
      const first = payload.details.model_id?.[0]
      if (first) return first
    }
    return payload.error || `HTTP ${response.status}`
  } catch {
    return `HTTP ${response.status}`
  }
}

/** Hide vendor names in the toolbar; routing still uses the real model id. */
export function displayModelLabel(id: string, label: string): string {
  if (`${id} ${label}`.toLowerCase().includes('deepseek')) return 'модель 1'
  return label
}

function withPublicModelLabels(payload: LocalLlmStatus): LocalLlmStatus {
  return {
    ...payload,
    models: (payload.models || []).map((model) => ({
      ...model,
      label: displayModelLabel(model.id, model.label),
    })),
  }
}

/** Active chat model catalog (DeepSeek or local Ollama). */
export async function fetchLocalLlmModels(): Promise<LocalLlmStatus> {
  const response = await fetch('/api/v1/assistant/models/', {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) {
    throw new Error(await parseError(response))
  }
  return withPublicModelLabels((await response.json()) as LocalLlmStatus)
}

/** Select active chat model for subsequent requests (no container restart). */
export async function selectLocalLlmModel(modelId: string): Promise<LocalLlmStatus> {
  const response = await fetch('/api/v1/assistant/models/', {
    method: 'PUT',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
    },
    body: JSON.stringify({ model_id: modelId }),
  })
  if (!response.ok) {
    throw new Error(await parseError(response))
  }
  return withPublicModelLabels((await response.json()) as LocalLlmStatus)
}
