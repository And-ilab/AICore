export type AssistantKbKind = 'article' | 'website'

export interface AssistantKbOption {
  id: string
  slug: string
  label: string
  documentCount: number
  /** article = файлы и статьи, website = обход сайта */
  kind: AssistantKbKind
}

interface AssistantKbApiItem {
  id: number | string
  name: string
  slug: string
  description?: string
  document_count?: number
  load_kind?: string
}

export async function fetchAssistantKnowledgeBases(): Promise<AssistantKbOption[]> {
  const response = await fetch('/api/v1/assistant/kbs/', {
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`KB catalog failed: ${response.status}`)
  }
  const body = (await response.json()) as { items?: AssistantKbApiItem[] }
  return (body.items ?? []).map((item) => ({
    id: String(item.id),
    slug: (item.slug || String(item.id)).trim(),
    label: (item.name || item.slug || String(item.id)).trim(),
    documentCount: item.document_count ?? 0,
    kind: item.load_kind === 'website' ? 'website' : 'article',
  }))
}
