import { useEffect, useMemo, useState } from 'react'
import {
  ensureOktellListen,
  fetchOktellCall,
  type OktellCallEvent,
  type OktellLiveCall,
} from './api/oktellCalls'
import { SuflerPhoneApp } from './SuflerPhoneApp'
import { useOktellActiveCall } from './hooks/useOktellActiveCall'
import type { TranscriptLine } from './hooks/useSuflerTranscript'
import type { SuflerHint } from './api/suggest'
import { emptySuflerHintMessage } from './emptyHintCopy'

function linesFromEvents(events: OktellCallEvent[] | undefined): TranscriptLine[] {
  const lines: TranscriptLine[] = []
  const indexByKey = new Map<string, number>()
  for (const event of events || []) {
    if (event.type === 'transcript' && event.speaker && event.text && event.turn_id) {
      const key = `${event.turn_id}:${event.speaker}`
      const isFinal = event.is_final !== false
      const existingIndex = indexByKey.get(key)
      if (existingIndex == null) {
        indexByKey.set(key, lines.length)
        lines.push({
          id: `${event.turn_id}-${event.speaker}`,
          speaker: event.speaker,
          text: event.text,
          isFinal,
          turnId: event.turn_id,
          ...(event.speaker === 'client' && isFinal
            ? { hintStatus: 'loading' as const, hintMessage: 'Подсказки загружаются…' }
            : {}),
        })
      } else {
        const target = lines[existingIndex]
        target.text = event.text
        target.isFinal = isFinal
        if (
          event.speaker === 'client'
          && isFinal
          && target.hintStatus !== 'ready'
          && target.hintStatus !== 'empty'
        ) {
          target.hintStatus = 'loading'
          target.hintMessage = 'Подсказки загружаются…'
        }
      }
    }
    if (event.type === 'error' && event.turn_id) {
      const target = lines.find(
        (line) => line.turnId === event.turn_id && line.speaker === 'client',
      )
      if (target && target.hintStatus === 'loading') {
        target.hintStatus = 'empty'
        target.hintMessage = emptySuflerHintMessage('no_relevant_knowledge', false)
      }
    }
    if (event.type === 'hints' && event.turn_id) {
      const hints = (Array.isArray(event.hints) ? event.hints : []) as SuflerHint[]
      const target = lines.find(
        (line) => line.turnId === event.turn_id && line.speaker === 'client',
      )
      if (target) {
        if (target.hintStatus === 'ready' && (target.hints?.length ?? 0) > 0 && hints.length === 0) {
          continue
        }
        target.hints = hints.slice(0, 5)
        target.hintStatus = hints.length ? 'ready' : 'empty'
        target.hintMessage = hints.length
          ? ''
          : emptySuflerHintMessage(event.blocked_reason, false)
      }
    }
  }
  return lines
}

export function LiveSuflerPhoneApp({
  operatorName,
  embedded = false,
}: {
  operatorName?: string
  embedded?: boolean
}) {
  const polled = useOktellActiveCall('live')
  const [started, setStarted] = useState<OktellLiveCall | null>(null)
  const live = polled || started
  const [detail, setDetail] = useState<OktellLiveCall | null>(null)
  const seedLines = useMemo(
    () => linesFromEvents(detail?.events || live?.events),
    [detail?.events, live?.events],
  )

  useEffect(() => {
    let cancelled = false
    void ensureOktellListen().then((call) => {
      if (!cancelled && call) setStarted(call)
    })
    const timer = window.setInterval(() => {
      void ensureOktellListen().then((call) => {
        if (!cancelled && call) setStarted(call)
      })
    }, 8000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const load = () => {
      void fetchOktellCall('live').then((call) => {
        if (!cancelled && call) setDetail(call)
      })
    }
    load()
    const timer = window.setInterval(load, 1000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  const source = detail || live
  return (
    <SuflerPhoneApp
      demoMode={false}
      callId="live"
      clientPhone={source?.CallerID || ''}
      callFacts={{
        callerId: source?.CallerID || '',
        calledId: source?.CalledID || '',
        callType: source?.call_type || '',
        operator: source?.op_name || '',
        idchain: source?.Idchain || '',
        previousQuestion: source?.previous_question || '',
        previousAskedAt: source?.previous_asked_at || '',
      }}
      seedLines={seedLines}
      operatorName={operatorName}
      embedded={embedded}
    />
  )
}
