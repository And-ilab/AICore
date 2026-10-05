import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  requestSuflerSuggest,
  type SuflerHint,
  type SuggestResponse,
} from '../../sufler/api/suggest'

export interface ChatMessage {
  id: string
  speaker: 'client' | 'operator'
  text: string
  turnId: string
  hints?: SuflerHint[]
  pending?: boolean
}

interface UseChatSuflerOptions {
  demoMode?: boolean
  initialMessages?: ChatMessage[]
  autoSuggest?: boolean
  sessionId?: string
}

export function useChatSufler({
  demoMode = false,
  initialMessages = [],
  autoSuggest = true,
  sessionId,
}: UseChatSuflerOptions = {}) {
  const resolvedSessionId = useMemo(
    () =>
      sessionId?.trim()
      || `chat-dev-${
        globalThis.crypto?.randomUUID?.()
        || `${Date.now()}-${Math.random().toString(36).slice(2)}`
      }`,
    [sessionId],
  )
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages)
  const [hints, setHints] = useState<SuflerHint[]>(() => {
    const withHints = [...initialMessages]
      .reverse()
      .find((item) => item.speaker === 'client' && item.hints?.length)
    return withHints?.hints ?? []
  })
  const [activeTurnId, setActiveTurnId] = useState<string | null>(() => {
    const withHints = [...initialMessages]
      .reverse()
      .find((item) => item.speaker === 'client')
    return withHints?.turnId ?? null
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [latencyMs, setLatencyMs] = useState<number | null>(null)
  const [scenario, setScenario] = useState<SuggestResponse['scenario']>(null)
  const pendingSuggest = useRef<Set<string>>(new Set())

  const suggestForMessage = useCallback(
    async (message: ChatMessage) => {
      if (!autoSuggest || message.speaker !== 'client' || !message.text.trim()) {
        return
      }
      if (message.hints?.length) {
        setHints(message.hints.slice(0, 5))
        setActiveTurnId(message.turnId)
        return
      }
      if (pendingSuggest.current.has(message.turnId)) {
        return
      }
      if (demoMode) {
        // Storybook / offline demo: keep panel deterministic without orchestrator.
        setActiveTurnId(message.turnId)
        setHints([])
        return
      }
      pendingSuggest.current.add(message.turnId)
      setLoading(true)
      setError('')
      setActiveTurnId(message.turnId)
      try {
        const result = await requestSuflerSuggest(message.text, 5, {
          channel: 'online_chat',
          sessionId: resolvedSessionId,
        })
        const nextHints = result.hints.slice(0, 5)
        setHints(nextHints)
        setLatencyMs(result.latency_ms.total)
        setScenario(result.scenario ?? null)
        if (result.blocked_reason === 'no_hint_needed') {
          setError('')
        }
        setMessages((current) =>
          current.map((item) =>
            item.turnId === message.turnId && item.speaker === 'client'
              ? { ...item, hints: nextHints, pending: false }
              : item,
          ),
        )
      } catch (requestError) {
        setError(
          requestError instanceof Error
            ? requestError.message
            : 'Не удалось получить подсказки',
        )
      } finally {
        pendingSuggest.current.delete(message.turnId)
        setLoading(false)
      }
    },
    [autoSuggest, demoMode, resolvedSessionId],
  )

  useEffect(() => {
    const latestClient = [...messages]
      .reverse()
      .find((item) => item.speaker === 'client')
    if (latestClient) {
      void suggestForMessage(latestClient)
    }
  }, [messages, suggestForMessage])

  const pushClientMessage = useCallback(
    (text: string, turnId = `turn-${Date.now()}`) => {
      const message: ChatMessage = {
        id: `${turnId}-client`,
        speaker: 'client',
        text,
        turnId,
        pending: !demoMode,
      }
      setMessages((current) => [...current, message])
      setActiveTurnId(turnId)
      if (demoMode) {
        setHints([])
      }
    },
    [demoMode],
  )

  const pushOperatorMessage = useCallback((text: string) => {
    const turnId = `op-${Date.now()}`
    setMessages((current) => [
      ...current,
      {
        id: `${turnId}-operator`,
        speaker: 'operator',
        text,
        turnId,
      },
    ])
  }, [])

  const loadMessages = useCallback((next: ChatMessage[]) => {
    setError('')
    setLoading(false)
    setMessages(next)
    const withHints = [...next]
      .reverse()
      .find((item) => item.speaker === 'client' && item.hints?.length)
    const latestClient = [...next]
      .reverse()
      .find((item) => item.speaker === 'client')
    setHints(withHints?.hints?.slice(0, 5) ?? [])
    setActiveTurnId(latestClient?.turnId ?? null)
  }, [])

  return {
    messages,
    hints,
    activeTurnId,
    loading,
    error,
    latencyMs,
    scenario,
    pushClientMessage,
    pushOperatorMessage,
    loadMessages,
    setHints,
    setMessages,
  }
}
