export type DocTemplateFormat = 'docx' | 'pdf' | 'xlsx' | 'pptx' | 'bpmn' | 'txt' | 'mmd'

export interface ChatDocTemplateField {
  id: string
  label: string
  required?: boolean
}

export interface ChatDocTemplate {
  id: number
  name: string
  category: string
  output_format: DocTemplateFormat
  format_label: string
  fields: ChatDocTemplateField[]
  active: boolean
}

export interface DocDraftResult {
  mode: 'draft'
  template_id: number
  template_name: string
  output_format: DocTemplateFormat
  format_label?: string
  filename: string
  text: string
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as {
      details?: { request?: string[]; mode?: string[] }
      error?: string
    }
    return (
      payload.details?.request?.[0]
      || payload.details?.mode?.[0]
      || payload.error
      || `HTTP ${response.status}`
    )
  } catch {
    return `HTTP ${response.status}`
  }
}

export async function fetchChatDocTemplates(): Promise<ChatDocTemplate[]> {
  const response = await fetch('/api/v1/assistant/doc-templates/', {
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(await parseError(response))
  }
  const body = (await response.json()) as { items: ChatDocTemplate[] }
  return body.items || []
}

export async function generateDocDraft(
  templateId: number,
  fields: Record<string, string>,
  prompt = '',
  kbSlugs: readonly string[] = [],
): Promise<DocDraftResult> {
  const response = await fetch(
    `/api/v1/assistant/doc-templates/${templateId}/generate/`,
    {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
      },
      body: JSON.stringify({ mode: 'draft', fields, prompt, kb_slugs: kbSlugs }),
    },
  )
  if (!response.ok) {
    throw new Error(await parseError(response))
  }
  return (await response.json()) as DocDraftResult
}

export interface ContentFromPromptResult {
  kind: 'text' | 'slides' | 'diagram'
  mode: 'draft'
  template_id: number
  template_name: string
  output_format: DocTemplateFormat
  format_label?: string
  filename: string
  text: string
  fields: Record<string, string>
}

export async function generateFromPrompt(
  message: string,
): Promise<ContentFromPromptResult> {
  const response = await fetch('/api/v1/assistant/content/from-prompt/', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
    },
    body: JSON.stringify({ message }),
  })
  if (!response.ok) {
    throw new Error(await parseError(response))
  }
  return (await response.json()) as ContentFromPromptResult
}

export function looksLikeContentPrompt(message: string): boolean {
  const text = message.trim()
  if (!text) return false
  // Questions about how to file a report/memo must go to the knowledge base.
  if (
    /^(как|какой|какая|какие|какое|что|чем|зачем|почему|когда|где|кто|можно ли|нужно ли|за чей|есть ли)\b/i.test(
      text,
    )
  ) {
    return false
  }
  const hasKind =
    /записк|справк|отч[её]т|докладн|инструкц|презентац|слайд|\bppt\b|bpmn|диаграмм|блок-?схем|er[\s-]?диаграмм/i.test(
      text,
    )
  const hasVerb =
    /подготов|сделай|сгенерир|напиши|создай|нужн[аоы]|нарисуй|собери/i.test(text)
  return hasKind && hasVerb
}

export async function downloadGeneratedDocument(
  templateId: number,
  fields: Record<string, string>,
  prompt = '',
  kbSlugs: readonly string[] = [],
): Promise<void> {
  const response = await fetch(
    `/api/v1/assistant/doc-templates/${templateId}/generate/`,
    {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
      },
      body: JSON.stringify({ mode: 'download', fields, prompt, kb_slugs: kbSlugs }),
    },
  )
  if (!response.ok) {
    throw new Error(await parseError(response))
  }
  const blob = await response.blob()
  const header = response.headers.get('content-disposition') || ''
  const utfMatch = header.match(/filename\*=UTF-8''([^;]+)/i)
  const asciiMatch = header.match(/filename="([^"]+)"/i)
  const filename = decodeURIComponent(
    utfMatch?.[1] || asciiMatch?.[1] || 'document',
  )
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
