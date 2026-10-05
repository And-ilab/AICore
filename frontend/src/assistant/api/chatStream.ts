import type { ChatAttachmentPayload } from './attachments'
import { DEMO_STUB_ANSWER } from '../types'

export interface ChatSource {
  id?: string
  title?: string
  permalink?: string
  relevance_percent?: number
  snippet?: string
  kb_slug?: string
  article_id?: number | string
}

export interface ChatStreamChunk {
  content: string
  done: boolean
  sources?: ChatSource[]
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

function parseSseBlock(block: string): ChatStreamChunk | null {
  const lines = block.split('\n')
  let data = ''
  for (const line of lines) {
    if (line.startsWith(':')) continue
    if (line.startsWith('data:')) {
      data += line.slice(5).trimStart()
    }
  }
  if (!data) return null
  if (data === '[DONE]') return { content: '', done: true }
  try {
    const payload = JSON.parse(data) as {
      choices?: Array<{ delta?: { content?: string | null } }>
      sources?: ChatSource[]
      error?: string
      details?: string
    }
    if (payload.error) {
      const detail = payload.details || payload.error
      const content =
        payload.choices?.[0]?.delta?.content ||
        `Ошибка модели: ${detail}`
      return {
        content: content || '',
        done: false,
        sources: Array.isArray(payload.sources) ? payload.sources : undefined,
      }
    }
    const content = payload.choices?.[0]?.delta?.content ?? ''
    return {
      content: content || '',
      done: false,
      sources: Array.isArray(payload.sources) ? payload.sources : undefined,
    }
  } catch {
    return null
  }
}

/** Consume OpenAI-compatible SSE from POST /api/v1/assistant/chat. */
export async function* streamAssistantChat(input: {
  message: string
  sessionId?: string
  kbSlugs?: string[]
  attachments?: ChatAttachmentPayload[]
  expand?: boolean
  skillId?: number
  signal?: AbortSignal
}): AsyncGenerator<ChatStreamChunk> {
  let response: Response
  try {
    response = await fetch('/api/v1/assistant/chat', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        'X-CSRFToken': csrfToken(),
      },
      body: JSON.stringify({
        message: input.message,
        session_id: input.sessionId,
        kb_slugs: input.kbSlugs ?? [],
        attachments: input.attachments?.length ? input.attachments : undefined,
        expand: input.expand || undefined,
        skill_id: input.skillId && input.skillId > 0 ? input.skillId : undefined,
        stream: true,
      }),
      signal: input.signal,
    })
  } catch (err) {
    const raw = err instanceof Error ? err.message : String(err)
    // Browser TypeError "Failed to fetch" = no HTTP response (down / TLS / proxy / CORS).
    if (/failed to fetch|networkerror|load failed/i.test(raw)) {
      throw new Error(
        'Нет связи с API (Failed to fetch). Откройте DevTools → Network: '
        + 'есть ли POST /api/v1/assistant/chat? На сервере проверьте, что '
        + 'backend/edge запущены, /api/ проксируется на Django, в .env заданы '
        + 'DJANGO_ALLOWED_HOSTS и DJANGO_CSRF_TRUSTED_ORIGINS = URL сайта '
        + '(https://ваш-хост), и что вы залогинены (cookie сессии).',
      )
    }
    throw err instanceof Error ? err : new Error(raw)
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const body = (await response.json()) as { error?: string; detail?: string }
      if (body.error) detail = body.error
      else if (body.detail) detail = body.detail
    } catch {
      /* ignore */
    }
    if (response.status === 401) {
      detail = 'Нужна авторизация (войдите в систему) — ' + detail
    } else if (response.status === 403) {
      detail =
        'Доступ запрещён (CSRF или права). Добавьте URL сайта в '
        + 'DJANGO_CSRF_TRUSTED_ORIGINS и перезапустите backend — ' + detail
    }
    throw new Error(detail)
  }

  if (!response.body) {
    throw new Error('Streaming body unavailable')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''
    for (const part of parts) {
      const chunk = parseSseBlock(part)
      if (!chunk) continue
      yield chunk
      if (chunk.done) return
    }
  }

  if (buffer.trim()) {
    const chunk = parseSseBlock(buffer)
    if (chunk) yield chunk
  }
}

/** Deterministic token stream for Storybook / offline demo. */
export async function* streamDemoChat(
  _message: string,
  signal?: AbortSignal,
  expand = false,
): AsyncGenerator<ChatStreamChunk> {
  const text = expand
    ? `${DEMO_STUB_ANSWER} Подробнее: условия, кому подходит продукт и как его оформить — по подтверждённым банковским источникам. Срок, ставка и пакет документов указаны в карточке продукта. Заявку принимает отделение или канал дистанционного обслуживания.`
    : DEMO_STUB_ANSWER
  const step = 18
  for (let index = 0; index < text.length; index += step) {
    if (signal?.aborted) {
      throw new DOMException('Aborted', 'AbortError')
    }
    yield { content: text.slice(index, index + step), done: false }
    await new Promise((resolve) => setTimeout(resolve, 20))
  }
  yield { content: '', done: true }
}
