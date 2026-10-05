import { useEffect, useState } from 'react'
import {
  fetchClientHistory,
  type ClientHistorySummaryBlock,
} from '../../online-chat/api/onlineChatApi'

/** Demo history only. A live call never substitutes this number. */
export const DEMO_CALLER_PHONE = '+375291234567'

export function isRealCallerPhone(phone: string): boolean {
  const trimmed = phone.trim()
  if (!trimmed || trimmed.toLowerCase() === 'sufler') return false
  return trimmed.replace(/\D/g, '').length >= 6
}

export type SuflerClientSummary = {
  preview: string
  summary: string
  detailedSummary: string
  blocks: ClientHistorySummaryBlock[]
  isFirst: boolean
  previousCount: number
}

const EMPTY: SuflerClientSummary = {
  preview: 'История обращений загружается…',
  summary: 'История обращений загружается…',
  detailedSummary: '',
  blocks: [],
  isFirst: false,
  previousCount: 0,
}

function mapHistory(
  summary: string,
  detailed: string,
  blocks: ClientHistorySummaryBlock[],
  previousCount: number,
  isFirst: boolean,
): SuflerClientSummary {
  const reallyFirst = isFirst || (previousCount <= 0 && blocks.length === 0)
  let text = summary.trim()
  if (!text) {
    text = reallyFirst
      ? 'Первое обращение клиента.'
      : `Клиент обращался ранее (${Math.max(previousCount, blocks.length)}).`
  } else if (!reallyFirst && /^первое обращение клиента\.?$/i.test(text)) {
    text = `Клиент обращался ранее (${Math.max(previousCount, blocks.length)}).`
  }
  return {
    preview: text,
    summary: reallyFirst
      ? 'Первое обращение клиента — предыдущей истории нет.'
      : text,
    detailedSummary: detailed.trim() || text,
    blocks,
    isFirst: reallyFirst,
    previousCount,
  }
}

const NO_LOOKUP: SuflerClientSummary = {
  preview: '',
  summary: '',
  detailedSummary: '',
  blocks: [],
  isFirst: false,
  previousCount: 0,
}

export function useClientSummary(
  clientPhone = '',
  options?: { allowDemo?: boolean },
) {
  const raw = clientPhone.trim()
  const phone = isRealCallerPhone(raw)
    ? raw
    : options?.allowDemo
      ? DEMO_CALLER_PHONE
      : ''
  const [data, setData] = useState<SuflerClientSummary>(phone ? EMPTY : NO_LOOKUP)
  const [loading, setLoading] = useState(Boolean(phone))
  const [error, setError] = useState('')

  useEffect(() => {
    if (!phone) {
      setData(NO_LOOKUP)
      setLoading(false)
      setError('')
      return
    }
    let cancelled = false
    setLoading(true)
    setError('')
    void fetchClientHistory({ phone })
      .then((response) => {
        if (cancelled) return
        setData(
          mapHistory(
            response.summary ?? '',
            response.detailed_summary ?? '',
            response.detailed_blocks ?? [],
            response.previous_count ?? response.items?.length ?? 0,
            Boolean(response.is_first),
          ),
        )
      })
      .catch((requestError: unknown) => {
        if (cancelled) return
        setData({
          ...EMPTY,
          preview: 'Не удалось загрузить историю клиента.',
          summary: 'Не удалось загрузить историю клиента.',
        })
        setError(
          requestError instanceof Error
            ? requestError.message
            : 'Не удалось загрузить историю',
        )
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [phone])

  return { phone, data, loading, error }
}
