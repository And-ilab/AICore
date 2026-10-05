export interface QuPreviewDocument {
  rank: number
  article_id: number
  chunk_index: number
  kb_slug?: string
  title: string
  permalink: string
  snippet: string
  relevance_score: number
  relevance_percent: number
  meets_min_relevance: boolean
  matched_example_id: number | null
  matched_example: string
}

export interface QuPreviewHint {
  text: string
  title: string
  permalink: string
  article_id: number
  relevance_percent: number
}

export interface QuPreviewResult {
  query: string
  kb_id: string
  min_relevance: number
  min_relevance_percent: number
  documents: QuPreviewDocument[]
  hint?: QuPreviewHint | null
}

interface ApiErrorPayload {
  error?: string
  details?: Record<string, string[]>
}

export class QuPreviewApiError extends Error {
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

export async function previewQuQuery(
  query: string,
): Promise<QuPreviewResult> {
  const response = await fetch('/api/admin/qu/preview/', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
    },
    body: JSON.stringify({ query, limit: 5 }),
  })
  const body = await response.json() as QuPreviewResult | ApiErrorPayload
  if (!response.ok) {
    const error = body as ApiErrorPayload
    throw new QuPreviewApiError(
      error.error ?? `Request failed with status ${response.status}`,
      error.details ?? {},
    )
  }
  return body as QuPreviewResult
}
