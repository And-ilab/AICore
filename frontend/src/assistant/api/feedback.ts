import type { FeedbackKind } from '../types'

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as {
      details?: { request?: string[] }
      error?: string
    }
    return payload.details?.request?.[0] || payload.error || `Ошибка ${response.status}`
  } catch {
    return `Ошибка ${response.status}`
  }
}

export async function submitAssistantFeedback(payload: {
  messageId: string
  sessionId: string
  choice: FeedbackKind
  question: string
  answer: string
  relevancePercent?: number | null
  articleId?: number | null
  articleTitle?: string
}): Promise<void> {
  const response = await fetch('/api/v1/assistant/feedback/', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
    },
    body: JSON.stringify({
      message_id: payload.messageId,
      session_id: payload.sessionId,
      choice: payload.choice,
      question: payload.question,
      answer: payload.answer,
      relevance_percent: payload.relevancePercent ?? null,
      article_id: payload.articleId ?? null,
      article_title: payload.articleTitle ?? '',
    }),
  })
  if (!response.ok) throw new Error(await parseError(response))
}
