export type RelevanceTone = 'success' | 'warning' | 'danger'

export interface TestDialogSource {
  title: string
  scenario?: string
  permalink?: string
}

export interface TestDialogTurn {
  id: string
  userText: string
  userTime: string
  llmText: string
  relevance: string
  relevanceTone: RelevanceTone
  sources: TestDialogSource[]
  etalon?: string
}

export interface TestDialogPromptResult {
  query: string
  scenario_id: string
  prompt_profile: string
  llm_text: string
  relevance_percent: number
  relevance_tone: RelevanceTone
  sources: TestDialogSource[]
  etalon?: string
  stub?: boolean
  request_id?: string
}

interface ApiErrorPayload {
  error?: string
  details?: Record<string, string[]>
}

export class TestDialogApiError extends Error {
  readonly details: Record<string, string[]>

  constructor(message: string, details: Record<string, string[]> = {}) {
    super(message)
    this.details = details
  }
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

export async function requestTestDialogPrompt(input: {
  text: string
  scenarioId: string
  usePipeline?: boolean
}): Promise<TestDialogPromptResult> {
  const response = await fetch('/api/v1/sufler/test-dialog', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
    },
    body: JSON.stringify({
      text: input.text,
      scenario_id: input.scenarioId,
      use_pipeline: input.usePipeline ?? true,
    }),
  })
  const body = (await response.json()) as TestDialogPromptResult | ApiErrorPayload
  if (!response.ok) {
    const error = body as ApiErrorPayload
    throw new TestDialogApiError(
      error.error || `HTTP ${response.status}`,
      error.details || {},
    )
  }
  return body as TestDialogPromptResult
}
