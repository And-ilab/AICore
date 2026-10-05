import { useCallback, useEffect, useRef, useState } from 'react'
import {
  fieldConfidencePercent,
  fieldDisplayValue,
  type ChatAttachmentPayload,
} from './api/attachments'
import {
  generateFromPrompt,
  looksLikeContentPrompt,
} from './api/docTemplates'
import { streamAssistantChat, streamDemoChat } from './api/chatStream'
import { compactChatText } from './compactChatText'
import { finishLastSentence } from './finishLastSentence'
import {
  createDialogInHistory,
  deleteDialogFromHistory,
  listDialogSummaries,
  loadChatHistory,
  openDialogInHistory,
  savePersistedChat,
  type ChatDialogSummary,
} from './chatPersistence'
import { filterOcrFields } from '../ai-hub/ocr/fieldQuality'
import {
  DEFAULT_TOOLS,
  SEED_MESSAGES,
  type AssistantCodeBlock,
  type AssistantGeneratedDraft,
  type AssistantMessage,
  type AssistantOcrResult,
  type AssistantToolState,
  type FeedbackKind,
  type ToolId,
} from './types'

const OCR_FIELD_LABELS: Record<string, string> = {
  full_name: 'ФИО',
  surname: 'Фамилия',
  given_name: 'Имя',
  patronymic: 'Отчество',
  series: 'Серия',
  number: 'Номер',
  issue_date: 'Дата выдачи',
  birth_date: 'Дата рождения',
  document_number: 'Номер документа',
  date: 'Дата',
  payer: 'Плательщик',
  beneficiary: 'Получатель',
  amount: 'Сумма',
  purpose: 'Назначение',
  currency: 'Валюта',
  address: 'Адрес',
  issued_by: 'Кем выдан',
  birth_place: 'Место рождения',
  personal_number: 'Личный номер',
  nationality: 'Гражданство',
}

function toAssistantOcr(attachment: ChatAttachmentPayload): AssistantOcrResult | null {
  const ocr = attachment.ocr
  if (!ocr?.job_id) return null
  const fields = filterOcrFields(Object.entries(ocr.fields || {}).map(([id, raw]) => {
    const explicit = (
      raw && typeof raw === 'object' && raw !== null && 'label' in raw
        ? String((raw as { label?: unknown }).label || '').trim()
        : ''
    )
    return {
      id,
      label: OCR_FIELD_LABELS[id] || explicit || id,
      value: fieldDisplayValue(raw),
      confidence: fieldConfidencePercent(raw),
    }
  }))
  return {
    jobId: ocr.job_id,
    documentId: ocr.document_id,
    documentType: ocr.document_type || 'unknown',
    validationStatus: ocr.validation_status,
    fields,
  }
}

function uid(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

export interface UseAssistantChatOptions {
  demoMode?: boolean
  initialMessages?: AssistantMessage[]
  sessionId?: string
  /** Selected assistant_* KB slugs for RAG. */
  getKbSlugs?: () => string[]
  /** Active slash skill for this send (org or personal). */
  getSkillId?: () => number | null
  getSkillAlias?: () => string | null
  /** Persist chat across remounts / full-page open (localStorage history). */
  persist?: boolean
}

export function useAssistantChat({
  demoMode = false,
  initialMessages,
  sessionId: sessionIdProp,
  getKbSlugs,
  getSkillId,
  getSkillAlias,
  persist = true,
}: UseAssistantChatOptions = {}) {
  const history = persist && !demoMode ? loadChatHistory() : null
  const initialActive =
    history?.dialogs.find((item) => item.id === history.activeId)
    || history?.dialogs[0]
  const [sessionId, setSessionId] = useState(
    () => sessionIdProp || initialActive?.id || `sess-${Date.now()}`,
  )
  const [messages, setMessages] = useState<AssistantMessage[]>(() => {
    if (initialMessages) return initialMessages
    if (demoMode) return SEED_MESSAGES
    if (initialActive?.messages?.length) return initialActive.messages
    return []
  })
  const [dialogs, setDialogs] = useState<ChatDialogSummary[]>(() =>
    persist && !demoMode ? listDialogSummaries() : [],
  )
  const [tools, setTools] = useState<AssistantToolState[]>(DEFAULT_TOOLS)
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState('')
  const [toolsOpen, setToolsOpen] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const messagesRef = useRef(messages)
  messagesRef.current = messages

  const refreshDialogs = useCallback(() => {
    if (!persist || demoMode) {
      setDialogs([])
      return
    }
    setDialogs(listDialogSummaries())
  }, [demoMode, persist])

  useEffect(() => {
    if (!persist || demoMode || streaming) return
    savePersistedChat(sessionId, messages)
    refreshDialogs()
  }, [demoMode, messages, persist, refreshDialogs, sessionId, streaming])

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setStreaming(false)
  }, [])

  const setFeedback = useCallback((messageId: string, feedback: FeedbackKind) => {
    setMessages((current) =>
      current.map((item) =>
        item.id === messageId && item.role === 'assistant' && !item.feedback
          ? { ...item, feedback }
          : item,
      ),
    )
  }, [])

  const runTool = useCallback((toolId: ToolId) => {
    setTools((current) =>
      current.map((tool) => {
        if (tool.id !== toolId) return tool
        if (tool.state === 'running') return tool
        if (toolId === 'sql') {
          return { ...tool, state: 'running', detail: 'read-only · executing' }
        }
        if (toolId === 'rpa') {
          return { ...tool, state: 'running', detail: 'awaiting confirm' }
        }
        return { ...tool, state: 'running' }
      }),
    )
    window.setTimeout(() => {
      setTools((current) =>
        current.map((tool) =>
          tool.id === toolId
            ? {
                ...tool,
                state: toolId === 'rpa' ? 'blocked' : 'done',
                detail:
                  toolId === 'sql'
                    ? 'read-only · ok'
                    : toolId === 'rpa'
                      ? 'confirm required'
                      : tool.detail,
              }
            : tool,
        ),
      )
    }, 450)
  }, [])

  const setToolState = useCallback((
    toolId: ToolId,
    patch: Partial<AssistantToolState>,
  ) => {
    setTools((current) =>
      current.map((tool) => (tool.id === toolId ? { ...tool, ...patch } : tool)),
    )
  }, [])

  const pushLocalAssistantMessage = useCallback((
    content: string,
    draft?: AssistantGeneratedDraft,
    codeBlock?: AssistantCodeBlock,
  ) => {
    const id = uid('asst')
    setMessages((current) => [
      ...current,
      {
        id,
        role: 'assistant',
        content,
        draft,
        codeBlock,
        tools: codeBlock ? [codeBlock.tool] : draft ? ['text'] : ['document'],
      },
    ])
  }, [])

  const updateDraftText = useCallback((messageId: string, text: string) => {
    setMessages((current) =>
      current.map((item) =>
        item.id === messageId && item.draft
          ? { ...item, draft: { ...item.draft, text }, content: item.content }
          : item,
      ),
    )
  }, [])

  const sendMessage = useCallback(
    async (text: string, attachments: ChatAttachmentPayload[] = []) => {
      const trimmed = text.trim()
      const readyAttachments = attachments.filter(
        (item) => item.text?.trim() || item.ocr,
      )
      if ((!trimmed && !readyAttachments.length) || streaming) return

      const ocrResult = readyAttachments.map(toAssistantOcr).find(Boolean) || null
      const mediaOnly = readyAttachments.some((item) => item.media)
      const displayText =
        trimmed
        || (ocrResult
          ? `Распознай документ «${readyAttachments[0]?.name || 'файл'}» и покажи поля.`
          : readyAttachments.length === 1
            ? mediaOnly
              ? `Суммаризируй запись «${readyAttachments[0].name}».`
              : `Суммаризируй вложение «${readyAttachments[0].name}».`
            : 'Суммаризируй вложения.')
      const userId = uid('user')
      const assistantId = uid('asst')
      setError('')
      setMessages((current) => [
        ...current,
        {
          id: userId,
          role: 'user',
          content: displayText,
          skill: getSkillAlias?.()
            ? { alias: getSkillAlias() as string }
            : undefined,
          attachments: readyAttachments.map((item) => ({
            name: item.name,
            type: item.type,
            text: item.text,
            mediaKind: item.media?.kind,
          })),
        },
        {
          id: assistantId,
          role: 'assistant',
          content: ocrResult
            ? `Поля документа (${ocrResult.documentType}):\n`
              + ocrResult.fields
                .map((field) => {
                  const pct = field.confidence == null ? '—' : `${field.confidence}%`
                  return `• ${field.label}: ${field.value} — ${pct}`
                })
                .join('\n')
            : '',
          pending: !ocrResult,
          ocr: ocrResult || undefined,
          sources: demoMode
            ? [
                {
                  id: 'demo-src',
                  title: 'Регламент HR-12',
                  relevance_percent: 92,
                  permalink: 'https://suz.local/articles/hr-12',
                  snippet:
                    'Заявление на отпуск подаётся в HR-портале не позднее чем за 14 календарных дней.',
                },
              ]
            : [],
          feedback: null,
        },
      ])

      // OCR card already answers the document request; skip LLM unless user typed a question.
      if (ocrResult && !trimmed) {
        setMessages((current) =>
          current.map((item) =>
            item.id === assistantId ? { ...item, pending: false } : item,
          ),
        )
        return
      }

      if (trimmed && looksLikeContentPrompt(trimmed) && !readyAttachments.length) {
        try {
          const result = await generateFromPrompt(trimmed)
          const draft: AssistantGeneratedDraft = {
            kind: result.kind,
            templateId: result.template_id,
            templateName: result.template_name,
            filename: result.filename,
            outputFormat: result.output_format,
            formatLabel: result.format_label,
            text: result.text,
            fields: result.fields || {},
          }
          const lead =
            result.kind === 'text'
              ? `Черновик «${result.template_name}» — можно править в поле ниже.`
              : `Подготовлен файл «${result.template_name}». Скачайте или поправьте текст и скачайте снова.`
          setMessages((current) =>
            current.map((item) =>
              item.id === assistantId
                ? { ...item, content: lead, pending: false, draft, tools: ['text'] }
                : item,
            ),
          )
        } catch (err) {
          setMessages((current) =>
            current.map((item) =>
              item.id === assistantId
                ? {
                    ...item,
                    pending: false,
                    content:
                      err instanceof Error
                        ? err.message
                        : 'Не удалось сформировать черновик',
                  }
                : item,
            ),
          )
          setError(err instanceof Error ? err.message : 'Не удалось сформировать черновик')
        }
        return
      }

      setStreaming(true)

      const controller = new AbortController()
      abortRef.current = controller

      try {
        const stream = demoMode
          ? streamDemoChat(displayText, controller.signal)
          : streamAssistantChat({
              message: trimmed || displayText,
              sessionId,
              kbSlugs: getKbSlugs?.() ?? [],
              skillId: getSkillId?.() ?? undefined,
              attachments: readyAttachments.map((item) => ({
                name: item.name,
                type: item.type,
                text: item.text || '',
                content_type: item.content_type,
                size_bytes: item.size_bytes,
                media: item.media,
              })),
              signal: controller.signal,
            })

        for await (const chunk of stream) {
          if (Array.isArray(chunk.sources)) {
            setMessages((current) =>
              current.map((item) =>
                item.id === assistantId
                  ? {
                      ...item,
                      sources: chunk.sources!.map((source, index) => ({
                        id: source.id || `src-${index}`,
                        title: source.title || 'Источник',
                        relevance_percent: source.relevance_percent ?? 0,
                        permalink: source.permalink || '',
                        snippet: source.snippet || '',
                        kb_slug: source.kb_slug,
                        article_id: source.article_id,
                      })),
                    }
                  : item,
              ),
            )
          }
          if (chunk.content) {
            setMessages((current) =>
              current.map((item) =>
                item.id === assistantId
                  ? { ...item, content: item.content + chunk.content }
                  : item,
              ),
            )
          }
          if (chunk.done) break
        }

        setMessages((current) =>
          current.map((item) =>
            item.id === assistantId
              ? {
                  ...item,
                  pending: false,
                  content: compactChatText(
                    item.expanded
                      ? item.content
                      : finishLastSentence(item.content),
                  ),
                }
              : item,
          ),
        )
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          setMessages((current) =>
            current.map((item) =>
              item.id === assistantId
                ? {
                    ...item,
                    pending: false,
                    content: item.content
                      ? compactChatText(finishLastSentence(item.content))
                      : 'Генерация остановлена.',
                  }
                : item,
            ),
          )
        } else {
          const message = err instanceof Error ? err.message : 'Ошибка стриминга'
          setError(message)
          setMessages((current) =>
            current.filter((item) => item.id !== assistantId),
          )
        }
      } finally {
        abortRef.current = null
        setStreaming(false)
      }
    },
    [demoMode, getKbSlugs, getSkillAlias, getSkillId, sessionId, streaming],
  )

  const expandAnswer = useCallback(
    async (messageId: string) => {
      const current = messagesRef.current
      const target = current.find((item) => item.id === messageId)
      if (!target || target.role !== 'assistant' || streaming) return

      if (target.expanded) {
        setMessages((items) =>
          items.map((item) =>
            item.id === messageId
              ? {
                  ...item,
                  content: item.shortContent || item.content,
                  expanded: false,
                }
              : item,
          ),
        )
        return
      }

      if (target.detailContent) {
        setMessages((items) =>
          items.map((item) =>
            item.id === messageId
              ? { ...item, content: item.detailContent || item.content, expanded: true }
              : item,
          ),
        )
        return
      }

      const targetIndex = current.findIndex((item) => item.id === messageId)
      const question = [...current.slice(0, targetIndex)]
        .reverse()
        .find((item) => item.role === 'user')
      if (!question?.content.trim()) return

      const shortContent = target.content
      setError('')
      setMessages((items) =>
        items.map((item) =>
          item.id === messageId
            ? {
                ...item,
                shortContent,
                content: '',
                pending: true,
                expanded: true,
              }
            : item,
        ),
      )
      setStreaming(true)
      const controller = new AbortController()
      abortRef.current = controller

      try {
        const stream = demoMode
          ? streamDemoChat(question.content, controller.signal, true)
          : streamAssistantChat({
              message: question.content,
              sessionId,
              kbSlugs: getKbSlugs?.() ?? [],
              skillId: getSkillId?.() ?? undefined,
              expand: true,
              signal: controller.signal,
            })

        for await (const chunk of stream) {
          if (chunk.content) {
            setMessages((items) =>
              items.map((item) =>
                item.id === messageId
                  ? { ...item, content: item.content + chunk.content }
                  : item,
              ),
            )
          }
          if (chunk.done) break
        }

        setMessages((items) =>
          items.map((item) =>
            item.id === messageId
              ? {
                  ...item,
                  pending: false,
                  detailContent: item.content,
                  expanded: true,
                }
              : item,
          ),
        )
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          setMessages((items) =>
            items.map((item) =>
              item.id === messageId
                ? {
                    ...item,
                    pending: false,
                    content: item.content || shortContent,
                    detailContent: item.content || undefined,
                    expanded: Boolean(item.content),
                  }
                : item,
            ),
          )
        } else {
          const message = err instanceof Error ? err.message : 'Ошибка стриминга'
          setError(message)
          setMessages((items) =>
            items.map((item) =>
              item.id === messageId
                ? {
                    ...item,
                    pending: false,
                    content: shortContent,
                    expanded: false,
                  }
                : item,
            ),
          )
        }
      } finally {
        abortRef.current = null
        setStreaming(false)
      }
    },
    [demoMode, getKbSlugs, getSkillAlias, getSkillId, sessionId, streaming],
  )

  const newDialog = useCallback(() => {
    stopStreaming()
    setError('')
    setTools(DEFAULT_TOOLS)
    if (!persist || demoMode) {
      setMessages([])
      setSessionId(`sess-${Date.now()}`)
      return
    }
    const current = messagesRef.current
    if (!current.length) {
      setMessages([])
      refreshDialogs()
      return
    }
    savePersistedChat(sessionId, current)
    const created = createDialogInHistory([])
    setSessionId(created.id)
    setMessages([])
    refreshDialogs()
  }, [demoMode, persist, refreshDialogs, sessionId, stopStreaming])

  const openDialog = useCallback(
    (dialogId: string) => {
      if (dialogId === sessionId) return
      stopStreaming()
      setError('')
      setTools(DEFAULT_TOOLS)
      if (!persist || demoMode) return
      savePersistedChat(sessionId, messagesRef.current)
      const opened = openDialogInHistory(dialogId)
      if (!opened) return
      setSessionId(opened.id)
      setMessages(opened.messages)
      refreshDialogs()
    },
    [demoMode, persist, refreshDialogs, sessionId, stopStreaming],
  )

  const deleteDialog = useCallback(
    (dialogId: string) => {
      if (!persist || demoMode) return
      stopStreaming()
      if (dialogId === sessionId) {
        savePersistedChat(sessionId, messagesRef.current)
      }
      const next = deleteDialogFromHistory(dialogId)
      const active =
        next.dialogs.find((item) => item.id === next.activeId) || next.dialogs[0]
      if (!active) return
      setSessionId(active.id)
      setMessages(active.messages)
      setError('')
      setTools(DEFAULT_TOOLS)
      refreshDialogs()
    },
    [demoMode, persist, refreshDialogs, sessionId, stopStreaming],
  )

  return {
    messages,
    dialogs,
    tools,
    streaming,
    error,
    toolsOpen,
    setToolsOpen,
    sendMessage,
    expandAnswer,
    stopStreaming,
    setFeedback,
    runTool,
    setToolState,
    pushLocalAssistantMessage,
    updateDraftText,
    newDialog,
    openDialog,
    deleteDialog,
    sessionId,
  }
}
