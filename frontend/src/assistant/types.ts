export type FeedbackKind = 'useful' | 'incomplete' | 'incorrect'

export type ToolId = 'code' | 'sql' | 'rpa' | 'document' | 'text' | 'diagram' | 'translate'

export type GeneratedDraftKind = 'text' | 'slides' | 'diagram'

export interface AssistantGeneratedDraft {
  kind: GeneratedDraftKind
  templateId: number
  templateName: string
  filename: string
  outputFormat: string
  formatLabel?: string
  text: string
  fields: Record<string, string>
  prompt?: string
  kbSlugs?: string[]
}

export type ToolRunState = 'idle' | 'ready' | 'running' | 'done' | 'blocked'

export interface AssistantSource {
  id: string
  title: string
  relevance_percent: number
  permalink?: string
  snippet?: string
  kb_slug?: string
  article_id?: number | string
}

export interface AssistantAttachmentRef {
  name: string
  type?: string
  text?: string
  mediaKind?: string
}

export interface AssistantOcrField {
  id: string
  label: string
  value: string
  confidence: number | null
}

export interface AssistantOcrResult {
  jobId: string
  documentId: string
  documentType: string
  validationStatus?: string | null
  fields: AssistantOcrField[]
}

export interface AssistantCodeBlock {
  label: string
  text: string
  tool: 'sql' | 'code'
}

export interface AssistantMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  pending?: boolean
  sources?: AssistantSource[]
  feedback?: FeedbackKind | null
  tools?: ToolId[]
  attachments?: AssistantAttachmentRef[]
  skill?: { alias: string }
  ocr?: AssistantOcrResult
  shortContent?: string
  detailContent?: string
  expanded?: boolean
  draft?: AssistantGeneratedDraft
  codeBlock?: AssistantCodeBlock
}

export interface AssistantToolState {
  id: ToolId
  label: string
  state: ToolRunState
  detail?: string
}

/** @deprecated Stub catalog — UI loads live KBs from `/api/v1/assistant/kbs/`. */
export const KNOWLEDGE_BASES: readonly { id: string; label: string }[] = []

export type KbId = string

export const DEFAULT_KB_SELECTION: Record<string, boolean> = {}

export const DEFAULT_TOOLS: AssistantToolState[] = [
  { id: 'code', label: 'Код', state: 'ready' },
  { id: 'sql', label: 'SQL', state: 'ready', detail: 'read-only' },
  { id: 'translate', label: 'RU↔EN', state: 'idle' },
  { id: 'rpa', label: 'RPA', state: 'idle', detail: 'confirm' },
  { id: 'document', label: 'Документ', state: 'idle' },
  { id: 'text', label: 'Текст', state: 'idle' },
  { id: 'diagram', label: 'Схема', state: 'idle' },
]

export const FEEDBACK_LABELS: Record<FeedbackKind, { label: string; title: string }> = {
  useful: { label: 'Полезно', title: 'Воспользовался' },
  incomplete: { label: 'Неполный ответ', title: 'Неполный ответ' },
  incorrect: { label: 'Неверно', title: 'Не воспользовался' },
}

export const SEED_MESSAGES: AssistantMessage[] = [
  {
    id: 'seed-user-1',
    role: 'user',
    content: 'Как оформить отпуск?',
  },
  {
    id: 'seed-asst-1',
    role: 'assistant',
    content:
      'Для оформления отпуска подайте заявление в HR-портале не позднее чем за 5 рабочих дней. При необходимости приложите согласование руководителя.',
    sources: [
      {
        id: 'src-1',
        title: 'Регламент HR-12',
        relevance_percent: 94,
        permalink: 'https://suz.local/articles/hr-12',
      },
      {
        id: 'src-2',
        title: 'Положение об отпусках',
        relevance_percent: 87,
        permalink: 'https://suz.local/articles/leave-policy',
      },
    ],
    feedback: null,
  },
]

export const DEMO_STUB_ANSWER =
  'Ответ ассистента: запрос принят. Используйте подтверждённые банковские источники.'
