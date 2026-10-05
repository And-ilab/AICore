import { useCallback, useEffect, useRef, useState } from 'react'
import {
  enterSuflerScenario,
  exitSuflerScenario,
  requestSuflerSuggest,
  clearSuflerScenario,
  resumeSuflerScenario,
  type SuflerHint,
  type SuggestResponse,
} from '../api/suggest'
import { emptySuflerHintMessage, NO_SUZ_HINT_MESSAGE } from '../emptyHintCopy'
import { ensureOktellListen } from '../api/oktellCalls'

export type SuflerScenarioProgress = NonNullable<SuggestResponse['scenario']>

export interface TranscriptLine {
  id: string
  speaker: 'client' | 'operator'
  text: string
  isFinal: boolean
  turnId: string
  hints?: SuflerHint[]
  hintStatus?: 'loading' | 'ready' | 'empty'
  hintMessage?: string
  requestId?: string
}

interface UseSuflerTranscriptOptions {
  enabled?: boolean
  callId?: string
  demoMode?: boolean
  demoLines?: TranscriptLine[]
  seedLines?: TranscriptLine[]
  getKbSlugs?: () => string[] | undefined
}

type WsInbound =
  | {
      type: 'status'
      status: string
      call_id?: string
      asr?: string
    }
  | {
      type: 'call_reset'
      call_id?: string
    }
  | {
      type: 'transcript'
      speaker: 'client' | 'operator'
      text: string
      is_final: boolean
      turn_id: string
    }
  | {
      type: 'hints'
      turn_id: string
      hints: SuflerHint[]
      latency_ms?: Record<string, number>
      request_id?: string
      blocked_reason?: string | null
      scenario?: SuflerScenarioProgress | null
      suggested_scenario?: SuggestResponse['suggested_scenario']
    }
  | { type: 'error'; message: string; turn_id?: string }
  | { type: 'pong' }

function wsUrl(callId: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  return `${protocol}//${host}/ws/sufler/${callId}/`
}

function hintMessageFor(blocked: string | null | undefined, hasHints: boolean): string {
  return emptySuflerHintMessage(blocked, hasHints)
}

function keepScenario(
  previous: SuflerScenarioProgress | null,
  next: SuflerScenarioProgress | null,
): SuflerScenarioProgress | null {
  if (next) return next
  if (previous?.completed || previous?.paused) return previous
  return null
}

function dialogContextFrom(lines: TranscriptLine[]): string {
  return lines
    .map((line) => `${line.speaker === 'client' ? 'Клиент' : 'Оператор'}: ${line.text}`)
    .join('\n')
}

export function useSuflerTranscript({
  enabled = true,
  callId = 'live',
  demoMode = false,
  demoLines = [],
  seedLines = [],
  getKbSlugs,
}: UseSuflerTranscriptOptions) {
  const initialLines = demoMode ? demoLines : seedLines
  const [lines, setLines] = useState<TranscriptLine[]>(initialLines)
  const [connected, setConnected] = useState(demoMode)
  const [error, setError] = useState('')
  const [latencyMs, setLatencyMs] = useState<number | null>(null)
  const [scenario, setScenario] = useState<SuflerScenarioProgress | null>(null)
  const [suggestedScenario, setSuggestedScenario] = useState<
    NonNullable<SuggestResponse['suggested_scenario']> | null
  >(null)
  const socketRef = useRef<WebSocket | null>(null)
  const linesRef = useRef<TranscriptLine[]>(initialLines)
  const pausedRef = useRef(false)
  const resetGenRef = useRef(0)
  const inboundEnabledRef = useRef(true)
  const loadingSinceRef = useRef<Map<string, number>>(new Map())

  const upsertLine = useCallback((line: TranscriptLine) => {
    setLines((current) => {
      const index = current.findIndex(
        (item) => item.turnId === line.turnId && item.speaker === line.speaker,
      )
      if (index !== -1 && current[index].isFinal && !line.isFinal) {
        return current
      }
      const next =
        index === -1
          ? [...current, line]
          : current.map((item, itemIndex) => {
              if (itemIndex !== index) return item
              const incomingLoading = line.hintStatus === 'loading' && !(line.hints?.length)
              const keepStatus = incomingLoading && (
                item.hintStatus === 'ready' || item.hintStatus === 'empty'
              )
              return {
                ...item,
                ...line,
                hints: line.hints ?? item.hints,
                hintStatus: keepStatus ? item.hintStatus : (line.hintStatus ?? item.hintStatus),
                hintMessage: keepStatus ? item.hintMessage : (line.hintMessage ?? item.hintMessage),
              }
            })
      linesRef.current = next
      return next
    })
  }, [])

  const attachHints = useCallback(
    (
      turnId: string,
      hints: SuflerHint[],
      hintMessage = '',
      requestId = '',
      suppressEmptyMessage = false,
    ) => {
      setLines((current) => {
        const next = current.map((line) => {
          if (line.turnId !== turnId || line.speaker !== 'client') return line
          if (line.hintStatus === 'ready' && (line.hints?.length ?? 0) > 0 && hints.length === 0) {
            return line
          }
          return {
            ...line,
            hints,
            requestId: requestId || line.requestId,
            hintStatus: (hints.length ? 'ready' : 'empty') as TranscriptLine['hintStatus'],
            hintMessage: hints.length
              ? ''
              : suppressEmptyMessage
                ? ''
                : hintMessage || NO_SUZ_HINT_MESSAGE,
          }
        })
        linesRef.current = next
        return next
      })
    },
    [],
  )

  useEffect(() => {
    if (demoMode) {
      linesRef.current = demoLines
      setLines(demoLines)
      setError('')
      setConnected(true)
      return
    }
    setLines((current) => {
      if (!seedLines.length) {
        if (current.length && current === linesRef.current) return current
        linesRef.current = seedLines
        return seedLines
      }
      if (!current.length) {
        linesRef.current = seedLines
        return seedLines
      }
      const byKey = new Map<string, TranscriptLine>(
        current.map((line) => [`${line.turnId}:${line.speaker}`, line]),
      )
      let changed = false
      const next = [...current]
      for (const seed of seedLines) {
        const key = `${seed.turnId}:${seed.speaker}`
        const existing = byKey.get(key)
        if (!existing) {
          next.push(seed)
          byKey.set(key, seed)
          changed = true
          continue
        }
        const seedWouldWipeReady = existing.hintStatus === 'ready'
          && (existing.hints?.length ?? 0) > 0
          && seed.hintStatus === 'empty'
        const hintsReady = !seedWouldWipeReady && (
          (seed.hints?.length ?? 0) > 0 || seed.hintStatus === 'empty'
        )
        const keepExistingText = existing.isFinal && !seed.isFinal
        const textChanged = !keepExistingText && (
          existing.text !== seed.text || existing.isFinal !== seed.isFinal
        )
        const hintsChanged = hintsReady && (
          existing.hintStatus === 'loading'
          || existing.hintStatus !== seed.hintStatus
          || (seed.hints?.length ?? 0) !== (existing.hints?.length ?? 0)
        )
        if (textChanged || hintsChanged) {
          const index = next.findIndex(
            (line) => line.turnId === seed.turnId && line.speaker === seed.speaker,
          )
          next[index] = {
            ...existing,
            text: keepExistingText ? existing.text : seed.text,
            isFinal: keepExistingText ? existing.isFinal : seed.isFinal,
            ...(hintsChanged
              ? {
                  hints: seed.hints ?? existing.hints,
                  hintStatus: seed.hintStatus,
                  hintMessage: seed.hintMessage,
                }
              : {}),
          }
          changed = true
        }
      }
      if (!changed) return current
      linesRef.current = next
      return next
    })
  }, [callId, demoMode, demoLines, seedLines])

  useEffect(() => {
    const now = Date.now()
    for (const line of lines) {
      const key = `${line.turnId}:${line.speaker}`
      if (line.speaker === 'client' && line.hintStatus === 'loading') {
        if (!loadingSinceRef.current.has(key)) loadingSinceRef.current.set(key, now)
      } else {
        loadingSinceRef.current.delete(key)
      }
    }
  }, [lines])

  useEffect(() => {
    const timer = window.setInterval(() => {
      const now = Date.now()
      const expired = new Set<string>()
      for (const [key, started] of loadingSinceRef.current) {
        if (now - started >= 22000) expired.add(key)
      }
      if (!expired.size) return
      setLines((current) => {
        let changed = false
        const next = current.map((line) => {
          const key = `${line.turnId}:${line.speaker}`
          if (!expired.has(key) || line.hintStatus !== 'loading') return line
          changed = true
          loadingSinceRef.current.delete(key)
          return {
            ...line,
            hintStatus: 'empty' as const,
            hintMessage: NO_SUZ_HINT_MESSAGE,
          }
        })
        if (!changed) return current
        linesRef.current = next
        return next
      })
    }, 2000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    if (demoMode || callId !== 'live') return
    const send = () => {
      const slugs = getKbSlugs?.()
      if (slugs === undefined) return
      void ensureOktellListen(slugs)
    }
    send()
    const timer = window.setInterval(send, 3000)
    return () => window.clearInterval(timer)
  }, [callId, demoMode, getKbSlugs])

  useEffect(() => {
    if (!enabled || demoMode || callId.startsWith('dev-call-')) {
      setConnected(true)
      setError('')
      return
    }

    const socket = new WebSocket(wsUrl(callId))
    socketRef.current = socket

    socket.onopen = () => {
      setConnected(true)
      setError('')
    }
    socket.onclose = () => {
      setConnected(false)
    }
    socket.onerror = () => {
      setError('WebSocket соединение недоступно')
    }
    socket.onmessage = (event) => {
      let payload: WsInbound
      try {
        payload = JSON.parse(String(event.data)) as WsInbound
      } catch {
        setError('Некорректное WS-сообщение')
        return
      }
      if (payload.type === 'call_reset') {
        resetGenRef.current += 1
        linesRef.current = []
        setLines([])
        setScenario(null)
        setSuggestedScenario(null)
        return
      }
      if (payload.type === 'transcript') {
        if (pausedRef.current || !inboundEnabledRef.current) return
        upsertLine({
          id: `${payload.turn_id}-${payload.speaker}`,
          speaker: payload.speaker,
          text: payload.text,
          isFinal: payload.is_final,
          turnId: payload.turn_id,
          ...(payload.is_final && payload.speaker === 'client'
            ? {
                hintStatus: 'loading' as const,
                hintMessage: 'Подсказки загружаются…',
              }
            : {}),
        })
        return
      }
      if (payload.type === 'hints') {
        if (pausedRef.current || !inboundEnabledRef.current) return
        setScenario((current) => keepScenario(current, payload.scenario ?? null))
        setSuggestedScenario(payload.suggested_scenario ?? null)
        attachHints(
          payload.turn_id,
          payload.hints.slice(0, 5),
          hintMessageFor(payload.blocked_reason, payload.hints.length > 0),
          payload.request_id,
          payload.blocked_reason === 'no_hint_needed'
            || payload.blocked_reason === 'service_mode',
        )
        if (payload.latency_ms?.total != null) {
          setLatencyMs(payload.latency_ms.total)
        }
        return
      }
      if (payload.type === 'error') {
        if (payload.turn_id) {
          attachHints(payload.turn_id, [], NO_SUZ_HINT_MESSAGE)
        }
      }
    }

    return () => {
      socket.close()
      socketRef.current = null
    }
  }, [attachHints, callId, demoMode, enabled, upsertLine])

  const ingestLive = useCallback(
    (message: {
      type: 'asr.partial' | 'asr.final'
      speaker: 'client' | 'operator'
      text: string
      turn_id: string
    }) => {
      inboundEnabledRef.current = true
      const nextLine: TranscriptLine = {
        id: `${message.turn_id}-${message.speaker}`,
        speaker: message.speaker,
        text: message.text,
        isFinal: message.type === 'asr.final',
        turnId: message.turn_id,
      }
      if (message.type === 'asr.final' && message.speaker === 'client') {
        nextLine.hintStatus = 'loading'
        nextLine.hintMessage = 'Подсказки загружаются…'
      }
      upsertLine(nextLine)
      if (message.type !== 'asr.final' || message.speaker !== 'client') return
      if (pausedRef.current) return
      const requestGen = resetGenRef.current
      const dialogContext = linesRef.current
        .map((line) =>
          `${line.speaker === 'client' ? 'Клиент' : 'Оператор'}: ${line.text}`,
        )
        .join('\n')
      void requestSuflerSuggest(message.text, 5, {
        dialogContext,
        channel: 'telephony',
        sessionId: callId,
        ...(getKbSlugs && getKbSlugs() !== undefined
          ? { kbSlugs: getKbSlugs() }
          : {}),
      })
        .then((result) => {
          if (requestGen !== resetGenRef.current) return
          const hints = result.hints.slice(0, 5)
          setScenario((current) => keepScenario(current, result.scenario ?? null))
          setSuggestedScenario(result.suggested_scenario ?? null)
          attachHints(
            message.turn_id,
            hints,
            hintMessageFor(result.blocked_reason, hints.length > 0),
            result.request_id,
            result.blocked_reason === 'no_hint_needed'
              || result.blocked_reason === 'service_mode',
          )
          setLatencyMs(result.latency_ms.total)
        })
        .catch(() => {
          if (requestGen !== resetGenRef.current) return
          attachHints(message.turn_id, [], NO_SUZ_HINT_MESSAGE)
        })
    },
    [attachHints, callId, getKbSlugs, upsertLine],
  )

  const pushAsr = useCallback(
    (message: {
      type: 'asr.partial' | 'asr.final'
      speaker: 'client' | 'operator'
      text: string
      turn_id: string
    }) => {
      if (demoMode) {
        ingestLive(message)
        return
      }
      const slugs = getKbSlugs?.()
      socketRef.current?.send(
        JSON.stringify(
          slugs === undefined ? message : { ...message, kb_slugs: slugs },
        ),
      )
    },
    [demoMode, getKbSlugs, ingestLive],
  )

  const replaceLines = useCallback(
    (next: TranscriptLine[] | ((current: TranscriptLine[]) => TranscriptLine[])) => {
      setLines((current) => {
        const resolved = typeof next === 'function' ? next(current) : next
        linesRef.current = resolved
        return resolved
      })
    },
    [],
  )

  const applySuggestResult = useCallback(
    (result: SuggestResponse, turnId?: string) => {
      const hints = result.hints.slice(0, 5)
      setScenario((current) => keepScenario(current, result.scenario ?? null))
      setSuggestedScenario(result.suggested_scenario ?? null)
      if (turnId) {
        attachHints(
          turnId,
          hints,
          hintMessageFor(result.blocked_reason, hints.length > 0),
          result.request_id,
          result.blocked_reason === 'no_hint_needed'
            || result.blocked_reason === 'service_mode',
        )
      }
      if (result.latency_ms?.total != null) {
        setLatencyMs(result.latency_ms.total)
      }
    },
    [attachHints],
  )

  const enterSuggested = useCallback(
    async (code: string) => {
      const lastClient = [...linesRef.current]
        .reverse()
        .find((line) => line.speaker === 'client' && line.isFinal)
      const result = await enterSuflerScenario(code, {
        sessionId: callId,
        channel: 'telephony',
      })
      applySuggestResult(result, lastClient?.turnId)
    },
    [applySuggestResult, callId],
  )

  const exitActive = useCallback(async () => {
    const result = await exitSuflerScenario(callId)
    setScenario(result.scenario ?? null)
    setSuggestedScenario(result.suggested_scenario ?? null)
  }, [callId])

  const resumeActive = useCallback(
    async (mode: 'start' | 'checkpoint' | 'step', nodeId?: string) => {
      const lastClient = [...linesRef.current]
        .reverse()
        .find((line) => line.speaker === 'client' && line.isFinal)
      const result = await resumeSuflerScenario(callId, mode, {
        channel: 'telephony',
        nodeId,
        dialogContext: dialogContextFrom(linesRef.current),
      })
      applySuggestResult(result, lastClient?.turnId)
    },
    [applySuggestResult, callId],
  )

  const resetConversation = useCallback(() => {
    resetGenRef.current += 1
    inboundEnabledRef.current = false
    linesRef.current = []
    setLines([])
    setScenario(null)
    setSuggestedScenario(null)
    setError('')
    setLatencyMs(null)
    void clearSuflerScenario(callId)
  }, [callId])

  const setRecognitionPaused = useCallback((paused: boolean) => {
    pausedRef.current = paused
  }, [])

  return {
    lines,
    connected,
    error,
    latencyMs,
    scenario,
    suggestedScenario,
    ingestLive,
    pushAsr,
    setLines: replaceLines,
    enterSuggested,
    exitActive,
    resumeActive,
    resetConversation,
    setRecognitionPaused,
  }
}
